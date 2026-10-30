"""Modo MongoDB (banco na nuvem): conjuntos, projetos e obras como documentos.

Parte do programa Levantamento de Materiais (Ceneged)."""

import json
import os
import re
import time
import hashlib as _hashlib
import uuid as _uuid
import zipfile as _zipfile

from ceneged.dados.caminhos import (_MONGO, config_mongo, modo_mongo, modo_onedrive,
    pasta_programa)
from ceneged.dados.banco import _nome_dados
from ceneged.dados.onedrive import (PARTICOES_OD, _od_base, _od_consulta, _od_hash, _od_ler,
    _od_migrar, od_ler_dados)

def ultimo_acesso(login, u):
    if modo_mongo():
        v = mongo_ultimo_acesso(login)
        if v:
            return v
    if modo_onedrive():
        try:
            return _od_ler(os.path.join(_od_base(), "acessos",
                                        re.sub(r"[^\w.]", "_", login) + ".json")).get("ultimo_acesso", "")
        except (OSError, ValueError):
            pass
    return (u or {}).get("ultimo_acesso", "")


# ---------------------------------------------------------------------------
#  MODO MONGODB (banco na nuvem, ex.: MongoDB Atlas): todos os computadores gravam direto
#  no mesmo banco, sem sincronização de arquivos. Liga quando existe o arquivo
#  "banco_mongo.txt" (com o endereço do banco: mongodb+srv://usuario:senha@...) na pasta do
#  programa ou na pasta de dados.
#    coleção "conjuntos": um documento por conjunto (cadastro, composições, usuários, ...)
#    coleção "projetos":  um documento por projeto conferido
#    coleção "obras":     um documento por obra da carteira
#    coleção "acessos":   último acesso de cada pessoa
#  Na primeira vez, cada conjunto vem dos dados antigos (pasta dados do OneDrive, ceneged.db
#  ou .json). Sem conexão: nada é gravado e o programa avisa.
# ---------------------------------------------------------------------------
class SemBanco(OSError):
    """Sem conexão com o banco de dados (MongoDB)."""
COLECOES_MONGO = {"projetos": "projetos", "carteira": "obras"}     # conjunto -> um documento por registro
_mongo_cache = {}            # conjunto -> {_id: hash do que foi lido/gravado}
_mongo_lidos = set()         # conjuntos lidos do banco nesta sessão (só esses podem ser gravados)
_mongo_ver = {}              # conjunto -> (hora, versão): não pergunta ao banco a cada instante
AO_GRAVAR_NO_BANCO = []      # funções chamadas depois de cada gravação: f(nome, ...)


def _uri_mongo(uri):
    """Senha com caracteres especiais (@ : / ...) precisa ir codificada no endereço."""
    from urllib.parse import quote_plus, unquote_plus
    m = re.match(r"^(mongodb(?:\+srv)?://)([^:/@]+):(.*)@([^@/]+(?:/.*)?)$", uri.strip())
    if not m:
        return uri.strip()
    return m.group(1) + m.group(2) + ":" + quote_plus(unquote_plus(m.group(3))) + "@" + m.group(4)


def _mongo_db():
    if time.time() < _MONGO["off_ate"]:
        raise SemBanco(_MONGO["erro"] or "Sem conexão com o banco de dados.")
    if _MONGO["db"] is None:
        uri = config_mongo()
        try:
            if uri.startswith("mongomock://"):                  # testes
                import mongomock
                cli = mongomock.MongoClient()
            else:
                import pymongo
                cli = pymongo.MongoClient(_uri_mongo(uri), serverSelectionTimeoutMS=8000,
                                          connectTimeoutMS=8000, socketTimeoutMS=30000,
                                          appname="CenegedLevantamento")
        except ImportError:
            raise SemBanco("Falta a biblioteca do MongoDB (pymongo) no programa. "
                           "Gere o instalador de novo.")
        except Exception as ex:
            if type(ex).__name__ == "InvalidURI":
                msg = f"Endereço do banco inválido (banco_mongo.txt): {ex}"
            else:                       # mongodb+srv: sem internet o endereço nem é encontrado
                msg = ("Sem conexão com o banco de dados (não encontrei o servidor). "
                       "Confira a internet.")
            _MONGO["erro"], _MONGO["off_ate"] = msg, time.time() + 20
            raise SemBanco(msg) from ex
        try:
            db = cli.get_default_database("ceneged")
        except Exception:
            db = cli["ceneged"]
        _MONGO["cli"], _MONGO["db"] = cli, db
    return _MONGO["db"]


def _mongo(fn):
    """Roda fn(db). Falha de conexão vira SemBanco e, por 20 s, nem tenta de novo (o programa
    não fica travando a cada clique quando a internet caiu)."""
    db = _mongo_db()
    try:
        return fn(db)
    except SemBanco:
        raise
    except Exception as ex:
        nome = type(ex).__name__
        if nome in ("DuplicateKeyError",):
            raise
        if nome in ("OperationFailure",) and "auth" in str(ex).lower():
            msg = "O banco recusou o usuário ou a senha (banco_mongo.txt)."
        elif nome in ("ServerSelectionTimeoutError", "AutoReconnect", "NetworkTimeout",
                      "ConnectionFailure", "ConfigurationError"):
            msg = ("Sem conexão com o banco de dados. Confira a internet. Se a internet estiver "
                   "funcionando, no MongoDB Atlas confira em Network Access se o acesso está liberado.")
        else:
            msg = f"Erro no banco de dados: {ex}"
        _MONGO["erro"], _MONGO["off_ate"] = msg, time.time() + 20
        raise SemBanco(msg) from ex


def mongo_conectado(forcar=False):
    if forcar:
        _MONGO["off_ate"] = 0.0
    try:
        _mongo(lambda db: db.command("ping"))
        return True
    except SemBanco:
        return False


def _chaves_ok(x):
    """O MongoDB não gosta de nomes de campo com "." ou começando com "$"."""
    if isinstance(x, dict):
        return all(isinstance(k, str) and "." not in k and not k.startswith("$") and "\0" not in k
                   and _chaves_ok(v) for k, v in x.items())
    if isinstance(x, list):
        return all(_chaves_ok(v) for v in x)
    return True


def _para_banco(x):
    """Guarda como documento (dá para consultar no Atlas/Power BI); se tiver nome de campo que
    o MongoDB não aceita, guarda como texto JSON em {"_json": ...}."""
    return x if _chaves_ok(x) else {"_json": json.dumps(x, ensure_ascii=False)}


def _do_banco(x):
    if isinstance(x, dict) and "_json" in x and len(x) == 1:
        return json.loads(x["_json"])
    return x


def _id_projeto(chave):
    return _hashlib.sha1(chave.encode("utf-8")).hexdigest()[:20]


def _fonte_antiga(nome, caminho):
    """Primeira vez no banco: os dados vêm da pasta dados do OneDrive (se houver), senão do
    ceneged.db ou do .json antigo. Sem nenhum: OSError (conjunto novo, vazio)."""
    base = _od_base()
    if (nome in PARTICOES_OD and os.path.isdir(os.path.join(base, nome))) or \
            os.path.isfile(os.path.join(base, nome + ".json")):
        return od_ler_dados(caminho)
    return _od_migrar(nome, caminho)


def mongo_ler_dados(caminho):
    nome = _nome_dados(caminho)

    def ler(db):
        doc = db.conjuntos.find_one({"_id": nome})
        if doc is None:
            return None
        regs = list(db[COLECOES_MONGO[nome]].find({})) if nome in COLECOES_MONGO else None
        return doc, regs
    r = _mongo(ler)
    _mongo_lidos.add(nome)                # o banco respondeu: daqui para frente pode gravar
    if r is None:                         # ainda não está no banco: traz dos dados antigos
        d = _fonte_antiga(nome, caminho)   # (OSError se não houver nada: conjunto novo)
        mongo_salvar(caminho, d, primeira=True)
        return d
    doc, regs = r
    _mongo_ver[nome] = (time.time(), f"m{doc.get('versao', 0)}")
    meta = _do_banco(doc.get("conteudo")) or {}
    if nome not in COLECOES_MONGO:
        return meta
    cache = {}
    if nome == "projetos":
        projetos = {}
        for x in regs:
            valor = _do_banco(x.get("valor"))
            cache[x["_id"]] = _od_hash({"chave": x.get("chave"), "valor": valor})
            if "chave" in x:
                projetos[x["chave"]] = valor
        _mongo_cache[nome] = cache
        return dict(meta, projetos=projetos)
    obras = []
    for x in regs:
        o = {k: v for k, v in x.items() if k not in ("_id", "_gravado_em", "_gravado_por")}
        if set(o) == {"_json"}:
            o = json.loads(o["_json"])
        o["_uid"] = x["_id"]
        cache[x["_id"]] = _od_hash(o)
        obras.append(o)
    _mongo_cache[nome] = cache
    # id repetido (duas pessoas criaram obra ao mesmo tempo): a segunda ganha outro número
    obras.sort(key=lambda o: (o.get("id") or 0, o.get("criado_em", "")))
    vistos, maior = set(), max([int(o.get("id") or 0) for o in obras] + [0])
    for o in obras:
        if o.get("id") in vistos:
            maior += 1
            o["id"] = maior
        vistos.add(o.get("id"))
    meta = dict(meta)
    meta["proximo"] = max(int(meta.get("proximo", 1) or 1), maior + 1)
    return dict(meta, obras=obras)


def mongo_salvar(caminho, dados, primeira=False):
    nome = _nome_dados(caminho)
    if nome not in _mongo_lidos and not primeira:
        # o programa abriu sem conexão: gravar agora apagaria o que está no banco
        raise SemBanco("Os dados não foram carregados do banco quando o programa abriu "
                       "(estava sem conexão). Feche e abra o programa de novo.")
    agora = time.strftime("%d/%m/%Y %H:%M:%S")
    quem = os.environ.get("USERNAME") or os.environ.get("USER") or ""
    if nome not in COLECOES_MONGO:
        conteudo, ops, apagar = dados, [], []
    else:
        cache = {} if primeira else dict(_mongo_cache.get(nome, {}))
        regs = {}
        if nome == "projetos":
            for k, v in (dados.get("projetos") or {}).items():
                regs[_id_projeto(k)] = {"chave": k, "valor": v}
            conteudo = {k: v for k, v in dados.items() if k != "projetos"}
        else:
            for o in dados.get("obras") or []:
                if not o.get("_uid"):
                    o["_uid"] = _uuid.uuid4().hex
                regs[o["_uid"]] = o
            conteudo = {k: v for k, v in dados.items() if k != "obras"}
        ops, novos = [], {}
        for i, r in regs.items():
            h = _od_hash(r)
            novos[i] = h
            if cache.get(i) != h:                       # só grava o que esta pessoa mudou
                if nome == "projetos":
                    doc = {"chave": r["chave"], "valor": _para_banco(r["valor"])}
                else:
                    doc = {k: v for k, v in r.items() if k != "_uid"}
                    if not _chaves_ok(doc):
                        doc = {"_json": json.dumps(r, ensure_ascii=False)}
                doc.update(_id=i, _gravado_em=agora, _gravado_por=quem)
                ops.append(doc)
        apagar = [i for i in cache if i not in regs]    # o que esta pessoa apagou

    def gravar(db):
        if nome in COLECOES_MONGO:
            col = db[COLECOES_MONGO[nome]]
            for doc in ops:
                col.replace_one({"_id": doc["_id"]}, doc, upsert=True)
            if apagar:
                col.delete_many({"_id": {"$in": apagar}})
        return db.conjuntos.find_one_and_update(
            {"_id": nome},
            {"$set": {"conteudo": _para_banco(conteudo), "_gravado_em": agora, "_gravado_por": quem},
             "$inc": {"versao": 1}},
            upsert=True, return_document=True)
    doc = _mongo(gravar)
    if nome in COLECOES_MONGO:
        _mongo_cache[nome] = novos
    _mongo_lidos.add(nome)
    try:
        _mongo_ver[nome] = (time.time(), f"m{doc.get('versao', 0)}")
    except AttributeError:
        _mongo_ver.pop(nome, None)
    _od_consulta(nome, dados)
    for f in AO_GRAVAR_NO_BANCO:          # ex.: tabelas para ver (ceneged_tabelas), em segundo plano
        try:
            f(nome)
        except Exception:
            pass


def mongo_versao(caminho):
    """Versão do conjunto no banco (muda a cada gravação de qualquer pessoa). Pergunta ao
    banco no máximo a cada 5 s."""
    nome = _nome_dados(caminho)
    t, v = _mongo_ver.get(nome, (0.0, None))
    if time.time() - t < 5:
        return v
    try:
        doc = _mongo(lambda db: db.conjuntos.find_one({"_id": nome}, {"versao": 1}))
    except SemBanco:
        return v                          # sem conexão: fica com o que tem
    v = f"m{doc.get('versao', 0)}" if doc else None
    _mongo_ver[nome] = (time.time(), v)
    return v


def mongo_registrar_acesso(login):
    try:
        _mongo(lambda db: db.acessos.update_one(
            {"_id": login}, {"$set": {"ultimo_acesso": time.strftime("%d/%m/%Y %H:%M")}}, upsert=True))
    except SemBanco:
        return
    for f in AO_GRAVAR_NO_BANCO:
        try:
            f("_acessos", "usuarios")
        except Exception:
            pass


def mongo_ultimo_acesso(login):
    try:
        doc = _mongo(lambda db: db.acessos.find_one({"_id": login}))
    except SemBanco:
        return None
    return (doc or {}).get("ultimo_acesso")


def pasta_backup_banco():
    """Documentos\\Ceneged Levantamento - Backup (de quem é administrador)."""
    docs = os.path.join(os.path.expanduser("~"), "Documents")
    if not os.path.isdir(docs):
        docs = os.path.join(os.path.expanduser("~"), "Documentos")
    if not os.path.isdir(docs):
        docs = os.path.expanduser("~")
    return os.path.join(docs, "Ceneged Levantamento - Backup")


def mongo_copia_do_dia(dias=30):
    """O banco gratuito do Atlas não faz cópia de segurança: uma vez por dia, quando um
    administrador entra no programa, tudo é salvo num .zip na pasta Documentos dele
    (Ceneged Levantamento - Backup\\AAAA-MM-DD.zip), guardando os últimos 30 dias."""
    if not modo_mongo():
        return
    hoje = time.strftime("%Y-%m-%d")
    try:
        marca = _mongo(lambda db: db.conjuntos.find_one({"_id": "_copia_do_dia"}))
        if marca and marca.get("dia") == hoje:
            return
        def tudo(db):
            return {c: list(db[c].find({})) for c in ("conjuntos", "projetos", "obras", "acessos")}
        colecoes = _mongo(tudo)
    except SemBanco:
        return
    for destino in (pasta_backup_banco(), os.path.join(pasta_programa(), "backup_banco")):
        try:
            os.makedirs(destino, exist_ok=True)
            arq = os.path.join(destino, hoje + ".zip")
            tmp = os.path.join(destino, "~$" + hoje + ".zip")
            with _zipfile.ZipFile(tmp, "w", _zipfile.ZIP_DEFLATED) as z:
                for c, docs in colecoes.items():
                    z.writestr(c + ".json", json.dumps(docs, ensure_ascii=False, indent=1, default=str))
            os.replace(tmp, arq)
            for x in sorted(x for x in os.listdir(destino) if x.endswith(".zip"))[:-dias]:
                os.remove(os.path.join(destino, x))
            break
        except OSError:
            continue
    else:
        return
    try:
        _mongo(lambda db: db.conjuntos.update_one({"_id": "_copia_do_dia"},
                                                   {"$set": {"dia": hoje, "arquivo": arq}}, upsert=True))
    except SemBanco:
        pass


def mongo_programa_publicado():
    """Versão do programa publicada no banco pelo GERAR_INSTALADOR.bat:
    {"versao", "partes", "tamanho", "sha256"} ou None."""
    try:
        return _mongo(lambda db: db.conjuntos.find_one({"_id": "_programa"}))
    except SemBanco:
        return None


def mongo_baixar_instalador(info, destino):
    """Baixa o instalador guardado no banco (coleção "instalador", em partes) e confere."""
    versao, partes = info["versao"], int(info["partes"])
    h = _hashlib.sha256()
    tmp = destino + ".parte"
    with open(tmp, "wb") as f:
        for n in range(partes):
            doc = _mongo(lambda db: db.instalador.find_one({"_id": f"{versao}|{n}"}))
            if not doc:
                raise SemBanco("O instalador no banco está incompleto. Gere o instalador de novo.")
            dados = bytes(doc["dados"])
            h.update(dados)
            f.write(dados)
    if info.get("sha256") and h.hexdigest() != info["sha256"]:
        os.remove(tmp)
        raise SemBanco("O instalador baixado veio com defeito. Tente de novo.")
    os.replace(tmp, destino)
    return destino
