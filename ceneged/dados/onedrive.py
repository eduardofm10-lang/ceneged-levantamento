"""Modo OneDrive: um arquivo por registro, junção de conflitos, cópia diária.

Parte do programa Levantamento de Materiais (Ceneged)."""

import json
import os
import re
import time
import sqlite3
import hashlib as _hashlib
import uuid as _uuid
import zipfile as _zipfile

from ceneged.dados.caminhos import (modo_onedrive, pasta_dados, pasta_programa)
from ceneged.dados.banco import (_nome_dados, _tabelas_de_consulta)

PARTICOES_OD = {"projetos": "projetos", "carteira": "obras"}   # conjunto -> um arquivo por registro
_od_cache = {}                   # nome -> {arquivo do registro: hash do conteúdo gravado/lido}
CONFLITOS_OD = []                # avisos de cópias em conflito juntadas nesta sessão


def _od_base():
    return os.path.join(pasta_dados(), "dados")


def _od_ler(caminho):
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)


def _od_gravar(caminho, dados):
    """Grava sem deixar arquivo pela metade. O temporário começa com "~$": o OneDrive não sobe."""
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    tmp = os.path.join(os.path.dirname(caminho), "~$" + os.path.basename(caminho) + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=1)
    os.replace(tmp, caminho)


def _od_hash(d):
    return _hashlib.sha1(json.dumps(d, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _juntar(a, b):
    """Junta duas versões (b é a mais nova): dicionários campo a campo, listas sem repetir
    (registros com id/login/nome iguais viram um só, valendo o mais novo)."""
    if isinstance(a, dict) and isinstance(b, dict):
        out = dict(a)
        for k, v in b.items():
            out[k] = _juntar(a[k], v) if k in a else v
        return out
    if isinstance(a, list) and isinstance(b, list):
        for ch in ("_uid", "id", "login", "nome", "chave"):
            if a + b and all(isinstance(x, dict) and ch in x for x in a + b):
                ordem, por = [], {}
                for x in a + b:
                    k = json.dumps(x[ch], ensure_ascii=False)
                    if k not in por:
                        ordem.append(k)
                        por[k] = x
                    else:
                        por[k] = _juntar(por[k], x)
                return [por[k] for k in ordem]
        vistos, out = set(), []
        for x in a + b:
            k = json.dumps(x, ensure_ascii=False, sort_keys=True)
            if k not in vistos:
                vistos.add(k)
                out.append(x)
        return out
    return b


def _od_resolver_conflitos(pasta):
    """Cópias em conflito do OneDrive ("x-PC.json", "x-PC-2.json") são juntadas no "x.json";
    a cópia vai para dados/_conflitos (nada se perde)."""
    try:
        nomes = [n for n in os.listdir(pasta) if n.endswith(".json") and "-" in n[:-5]
                 and not n.startswith("~$")]
    except OSError:
        return
    for n in nomes:
        base = n[:-5].split("-")[0] + ".json"
        a_cam, c_cam = os.path.join(pasta, base), os.path.join(pasta, n)
        try:
            c = _od_ler(c_cam)
            if os.path.exists(a_cam):
                a = _od_ler(a_cam)
                velho, novo = (c, a) if os.path.getmtime(a_cam) >= os.path.getmtime(c_cam) else (a, c)
                junto = _juntar(velho, novo)
            else:
                junto = c
            _od_gravar(a_cam, junto)
            guarda = os.path.join(_od_base(), "_conflitos")
            os.makedirs(guarda, exist_ok=True)
            os.replace(c_cam, os.path.join(guarda, time.strftime("%Y%m%d-%H%M%S_") + n))
            CONFLITOS_OD.append(f"{os.path.relpath(c_cam, _od_base())} → juntado em {base}")
        except (OSError, ValueError):
            pass


def _od_migrar(nome, caminho):
    """Primeira vez no modo OneDrive: traz o conjunto do ceneged.db (ou do .json antigo)."""
    banco = os.path.join(pasta_dados(), "ceneged.db")
    if os.path.exists(banco):
        try:
            con = sqlite3.connect(banco, timeout=20)
            try:
                row = con.execute("SELECT conteudo FROM dados WHERE nome = ?", (nome,)).fetchone()
            finally:
                con.close()
            if row is not None:
                return json.loads(row[0])
        except sqlite3.Error:
            pass
    with open(caminho, encoding="utf-8") as f:            # sem nada: OSError (igual antes)
        return json.load(f)


def od_ler_dados(caminho):
    nome = _nome_dados(caminho)
    base = _od_base()
    if nome in PARTICOES_OD:
        pasta = os.path.join(base, nome)
        if not os.path.isdir(pasta):
            d = _od_migrar(nome, caminho)
            od_salvar(caminho, d, primeira=True)
            return d
        _od_resolver_conflitos(pasta)
        cache, meta = {}, {}
        regs = []
        for n in sorted(os.listdir(pasta)):
            if not n.endswith(".json") or n.startswith("~$") or "-" in n[:-5]:
                continue
            try:
                r = _od_ler(os.path.join(pasta, n))
            except (OSError, ValueError):
                continue
            if n == "_meta.json":
                meta = r
            else:
                regs.append(r)
            cache[n] = _od_hash(r)
        _od_cache[nome] = cache
        if nome == "projetos":
            return dict(meta, projetos={r["chave"]: r["valor"] for r in regs if "chave" in r})
        # carteira: um arquivo por obra; id repetido (duas pessoas criaram ao mesmo tempo) ganha outro
        obras = sorted(regs, key=lambda o: (o.get("id") or 0, o.get("criado_em", "")))
        vistos, maior = set(), max([int(o.get("id") or 0) for o in obras] + [0])
        for o in obras:
            if o.get("id") in vistos:
                maior += 1
                o["id"] = maior
            vistos.add(o.get("id"))
        meta["proximo"] = max(int(meta.get("proximo", 1) or 1), maior + 1)
        return dict(meta, obras=obras)
    arq = os.path.join(base, nome + ".json")
    if not os.path.exists(arq):
        d = _od_migrar(nome, caminho)
        _od_gravar(arq, d)
        return d
    _od_resolver_conflitos(base)
    return _od_ler(arq)


def od_versao(caminho):
    nome = _nome_dados(caminho)
    base = _od_base()
    try:
        if nome in PARTICOES_OD:
            n, m = 0, 0.0
            for e in os.scandir(os.path.join(base, nome)):
                if e.name.endswith(".json") and not e.name.startswith("~$"):
                    n += 1
                    m = max(m, e.stat().st_mtime)
            return f"{n}|{m}"
        nomes = os.listdir(base)
        conf = sum(1 for x in nomes if x.startswith(nome + "-"))       # cópia em conflito chegou
        return f"{os.path.getmtime(os.path.join(base, nome + '.json'))}|{conf}"
    except OSError:
        return None


def od_salvar(caminho, dados, primeira=False):
    nome = _nome_dados(caminho)
    base = _od_base()
    if nome not in PARTICOES_OD:
        _od_gravar(os.path.join(base, nome + ".json"), dados)
        _od_consulta(nome, dados)
        return
    pasta = os.path.join(base, nome)
    os.makedirs(pasta, exist_ok=True)
    cache = {} if primeira else _od_cache.setdefault(nome, {})
    regs = {}
    if nome == "projetos":
        for k, v in (dados.get("projetos") or {}).items():
            regs[_hashlib.sha1(k.encode("utf-8")).hexdigest()[:20] + ".json"] = {"chave": k, "valor": v}
        meta = {k: v for k, v in dados.items() if k != "projetos"}
    else:
        for o in dados.get("obras") or []:
            if not o.get("_uid"):
                o["_uid"] = _uuid.uuid4().hex          # nome do arquivo da obra (não muda mais)
            regs[o["_uid"] + ".json"] = o
        meta = {k: v for k, v in dados.items() if k != "obras"}
    regs["_meta.json"] = meta
    for n, r in regs.items():
        h = _od_hash(r)
        if cache.get(n) != h:                          # só regrava o que esta pessoa mudou
            _od_gravar(os.path.join(pasta, n), r)
            cache[n] = h
    for n in [n for n in cache if n not in regs]:      # o que esta pessoa apagou
        try:
            os.remove(os.path.join(pasta, n))
        except OSError:
            pass
        cache.pop(n, None)
    _od_cache[nome] = cache
    _od_consulta(nome, dados)


def _od_consulta(nome, dados):
    """Tabelas de consulta num banco LOCAL (fora do OneDrive), só para ver/filtrar."""
    try:
        con = sqlite3.connect(os.path.join(pasta_programa(), "ceneged_consulta.db"), timeout=5)
        try:
            with con:
                _tabelas_de_consulta(con, nome, dados)
        finally:
            con.close()
    except Exception:
        pass


def od_copia_do_dia(dias=30):
    """Uma cópia por dia de todos os dados (dados/_backup/AAAA-MM-DD.zip), guarda 30 dias."""
    if not modo_onedrive():
        return
    base = _od_base()
    destino = os.path.join(base, "_backup")
    arq = os.path.join(destino, time.strftime("%Y-%m-%d") + ".zip")
    if os.path.exists(arq) or not os.path.isdir(base):
        return
    try:
        os.makedirs(destino, exist_ok=True)
        tmp = os.path.join(destino, "~$" + os.path.basename(arq))
        with _zipfile.ZipFile(tmp, "w", _zipfile.ZIP_DEFLATED) as z:
            for raiz, pastas, arqs in os.walk(base):
                pastas[:] = [p for p in pastas if not p.startswith("_")]
                for a in arqs:
                    if a.endswith(".json") and not a.startswith("~$"):
                        cam = os.path.join(raiz, a)
                        z.write(cam, os.path.relpath(cam, base))
        os.replace(tmp, arq)
        velhos = sorted(x for x in os.listdir(destino) if x.endswith(".zip"))[:-dias]
        for x in velhos:
            os.remove(os.path.join(destino, x))
    except OSError:
        pass


def od_registrar_acesso(login):
    """Último acesso num arquivo por pessoa (não regrava a lista de usuários a cada entrada)."""
    try:
        _od_gravar(os.path.join(_od_base(), "acessos", re.sub(r"[^\w.]", "_", login) + ".json"),
                   {"login": login, "ultimo_acesso": time.strftime("%d/%m/%Y %H:%M")})
    except OSError:
        pass
