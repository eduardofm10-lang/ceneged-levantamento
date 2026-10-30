"""Banco ceneged_tabelas: as tabelas para ver (uma linha por registro), atualizadas a cada gravação.

Parte do programa Levantamento de Materiais (Ceneged)."""

import json
import re
import time
import threading as _threading

from ceneged.dados.caminhos import (_MONGO, modo_mongo)
from ceneged.dados.mongo import (AO_GRAVAR_NO_BANCO, SemBanco, _do_banco, _mongo, _mongo_db)
from ceneged.dados.equipes import (CAMPOS_OBRA, EQUIPES)
from ceneged.dados.constantes import CONSTANTES
from ceneged.dados.normativos import _COLS_TABELA

BANCO_TABELAS = "ceneged_tabelas"

DICIONARIO_TABELAS = [
    # tabela, o que tem, uma linha por, chave, liga com
    ("estruturas", "Estruturas dos normativos (DIS-NOR-013/014/016/018)", "estrutura",
     "ID estrutura", "estruturas_itens.ID estrutura · composicoes.Normativo ligado"),
    ("estruturas_itens", "Materiais de cada estrutura, como na planilha do normativo (FIXO / VARIÁVEL / "
     "A DEFINIR, quantidade no poste DT e no circular)", "material de uma estrutura",
     "ID estrutura + Item", "estruturas.ID estrutura · normativo_tabelas.ID tabela (coluna ID tabela de escolha)"),
    ("normativo_tabelas", "Tabelas de escolha dos normativos (cintas, parafusos, alças, conectores...)",
     "tabela", "ID tabela", "normativo_tabelas_linhas.ID tabela · estruturas_itens.ID tabela de escolha"),
    ("normativo_tabelas_linhas", "Opções de cada tabela de escolha (código e para que bitola/poste serve)",
     "opção de material", "ID tabela + Código Nordeste", "normativo_tabelas.ID tabela"),
    ("postes", "Postes da DIS-ETE-011 (dimensões usadas para cinta, parafuso e suporte)", "poste",
     "Tipo + Comprimento + Resistência", "—"),
    ("alturas_aplicacao", "Distância do topo do poste onde cada rede é fixada", "situação", "Normativo + Situação", "—"),
    ("composicoes", "Composições da empresa (materiais extras / kits)", "composição", "ID composição",
     "composicoes_itens.ID composição · estruturas.ID estrutura (coluna Normativo ligado)"),
    ("composicoes_itens", "Materiais de cada composição", "material de uma composição",
     "ID composição + Material", "composicoes.ID composição · materiais.Código"),
    ("materiais", "Cadastro de materiais (nome usado na empresa e código)", "material", "Material",
     "composicoes_itens.Código · constantes.Código"),
    ("materiais_de_para", "Nome que vem no projeto → nome do cadastro", "correção", "Nome no projeto", "materiais.Material"),
    ("materiais_apelidos", "Outros nomes de cada material", "apelido", "Material + Apelido", "materiais.Material"),
    ("materiais_extras", "Regra antiga de materiais extras (principal → itens)", "item", "Principal + Item", "materiais.Material"),
    ("configuracoes", "Configurações do programa (região, tensão, conectores...)", "configuração", "Chave", "—"),
    ("constantes", "Constantes metro → KG", "material", "Código", "materiais.Código"),
    ("usuarios", "Quem usa o programa (sem senha)", "pessoa", "Login", "acessos.Login"),
    ("acessos", "Último acesso de cada pessoa", "pessoa", "Login", "usuarios.Login"),
    ("equipes_pessoas", "Pessoas cadastradas (supervisores, encarregados...)", "pessoa", "Nome", "obras.Supervisor / Encarregado"),
    ("equipes", "Equipes", "equipe", "Nome", "obras.Equipe"),
    ("obras", "Carteira de obra", "obra", "ID obra", "equipes · equipes_pessoas"),
    ("projetos", "Projetos conferidos no programa (o que foi corrigido à mão)", "projeto (PDF)", "Arquivo", "—"),
]
# tabelas de cada conjunto de dados do programa
TABELAS_DO_CONJUNTO = {
    "estruturas_normativo": ["estruturas", "estruturas_itens"],
    "tabelas_normas": ["normativo_tabelas", "normativo_tabelas_linhas", "postes", "alturas_aplicacao"],
    "composicoes": ["composicoes", "composicoes_itens"],
    "cadastro": ["materiais", "materiais_de_para", "materiais_apelidos", "materiais_extras", "configuracoes"],
    "constantes": ["constantes"],
    "usuarios": ["usuarios"],
    "_acessos": ["acessos"],
    "equipes": ["equipes_pessoas", "equipes"],
    "carteira": ["obras"],
    "projetos": ["projetos"],
}


def _vz(x):
    """'-', '' e None viram vazio (None) nas tabelas."""
    if x is None or (isinstance(x, str) and x.strip() in ("", "-")):
        return None
    if isinstance(x, float) and x == int(x):
        return int(x)
    return x


def _rot_coluna(r):
    """Nome de coluna sem ponto (o MongoDB não gosta): 'Cód. Nordeste' -> 'Código Nordeste'."""
    return r.replace("Cód.", "Código").replace("Nº", "Número").replace(".", "").replace("$", "").strip()


def _txt(x):
    if isinstance(x, (list, tuple)):
        if all(not isinstance(y, (list, tuple, dict)) for y in x):
            return ", ".join(str(y) for y in x)
        return json.dumps(x, ensure_ascii=False)
    if isinstance(x, dict):
        return json.dumps(x, ensure_ascii=False)
    return _vz(x)


def _id_tabela_da_ref(ref):
    """'Tabela 17 do DIS-NOR-013' -> 'DIS-NOR-013|Tabela 17'."""
    m = re.search(r"((?:Tabela|Quadro)\s*\d+[A-Z]?)\s*(?:do|da|de)?\s*(DIS-[A-Z]+-\d+)", ref or "", re.I)
    return f"{m.group(2).upper()}|{m.group(1).title()}" if m else None


_ROT_POSTES = {"tipo": "Tipo", "l": "Comprimento (m)", "rn": "Resistência (daN)",
               "rn_a": "Resistência face A (daN)", "ne": "Código Nordeste", "descricao": "Descrição",
               "uso": "Uso", "topo": "Topo (mm)", "base": "Base (mm)", "a": "Topo face A (mm)",
               "A": "Base face A (mm)", "b": "Topo face B (mm)", "B": "Base face B (mm)"}
_ROT_ALTURAS = {"norma": "Normativo", "situacao": "Situação", "d": "Distância do topo (m)", "obs": "Observação"}


def tabelas_visao(nome, d):
    """Linhas de cada tabela de um conjunto de dados: {tabela: [linhas]}."""
    t = {}
    if not isinstance(d, dict):
        return t
    if nome == "estruturas_normativo":
        est, itens, num = [], [], {}
        for e in d.get("estruturas") or []:
            norma, nm = e.get("norma", ""), e.get("nome", "")
            num[norma] = num.get(norma, 0) + 1
            eid = f"{norma}|{nm}"
            its = e.get("itens") or []
            est.append({"ID estrutura": eid, "Normativo": norma, "Número": num[norma], "Estrutura": nm,
                        "Página": _vz(e.get("pag")), "Itens": len(its),
                        "Itens a definir": sum(1 for i in its if i.get("adef"))})
            for n, i in enumerate(its, 1):
                varia = _vz(i.get("variavel"))
                definicao = "A DEFINIR" if i.get("adef") else ("VARIÁVEL" if varia else "FIXO")
                itens.append({
                    "ID estrutura": eid, "Normativo": norma, "Número": num[norma], "Estrutura": nm,
                    "Ordem": n, "Item": _vz(i.get("item")),
                    "Código Nordeste": _vz(i.get("ne")) or ("A DEFINIR" if i.get("adef") else None),
                    "Código Elektro": _vz(i.get("se")), "Código Brasília": _vz(i.get("br")),
                    "Descrição": _vz(i.get("desc")), "Und": _vz(i.get("und")),
                    "Definição": definicao, "Varia com": varia,
                    "Qtd poste DT": _vz(i.get("qdt")), "Qtd DT 36,2 kV": _vz(i.get("qdt36")),
                    "Qtd poste circular": _vz(i.get("qcirc")), "Qtd única": _vz(i.get("qunica")),
                    "Seção / Tensão": _vz(i.get("secao")),
                    "Tabela de escolha": _vz(i.get("ref")), "ID tabela de escolha": _id_tabela_da_ref(i.get("ref")),
                    "Informação necessária": _vz(i.get("info")), "Observação": _vz(i.get("obs"))})
        t["estruturas"], t["estruturas_itens"] = est, itens
    elif nome == "tabelas_normas":
        rot = {k: _rot_coluna(r) for r, k in _COLS_TABELA if k}
        tabs, linhas, postes, alturas = [], [], [], []
        for k, tb in (d.get("tabelas") or {}).items():
            norma, _, tab = k.partition("|")
            if tb.get("modo") == "geometria":
                postes += [{_ROT_POSTES.get(c, c): _txt(v) for c, v in l.items()} for l in tb.get("linhas") or []]
                continue
            if tb.get("modo") == "altura":
                alturas += [{_ROT_ALTURAS.get(c, c): _txt(v) for c, v in l.items()} for l in tb.get("linhas") or []]
                continue
            tabs.append({"ID tabela": k, "Normativo": norma, "Tabela": tab, "Título": tb.get("titulo"),
                         "Escolha por": tb.get("modo"), "Informação necessária": tb.get("info"),
                         "Opções": len(tb.get("linhas") or [])})
            for n, l in enumerate(tb.get("linhas") or [], 1):
                lin = {"ID tabela": k, "Normativo": norma, "Tabela": tab, "Ordem": n}
                for c, v in l.items():
                    lin[rot.get(c, c)] = _txt(v)
                linhas.append(lin)
        t["normativo_tabelas"], t["normativo_tabelas_linhas"] = tabs, linhas
        t["postes"], t["alturas_aplicacao"] = postes, alturas
    elif nome == "composicoes":
        kits = d.get("kits") or []
        t["composicoes"] = [{"ID composição": k.get("id"), "Categoria": k.get("categoria"), "Nome": k.get("nome"),
                             "Apelidos": _txt(k.get("apelidos") or []) or None, "Automática": bool(k.get("auto")),
                             "Normativo ligado": k.get("normativo"), "Itens": len(k.get("itens") or []),
                             "Atualizada pelo normativo": bool(k.get("itens_antes"))} for k in kits]
        t["composicoes_itens"] = [{"ID composição": k.get("id"), "Composição": k.get("nome"), "Ordem": n,
                                   "Material": i.get("nome"), "Código": _vz(i.get("codigo")),
                                   "Und": _vz(i.get("und")), "Quantidade": _vz(i.get("qtd")),
                                   "Movimento": _vz(i.get("mov")),
                                   **{c: _txt(v) for c, v in i.items()
                                      if c not in ("nome", "codigo", "und", "qtd", "mov")}}
                                  for k in kits for n, i in enumerate(k.get("itens") or [], 1)]
    elif nome == "cadastro":
        cod = d.get("codigos") or {}
        mats = [str(m) for m in d.get("materiais") or []]
        t["materiais"] = [{"Material": m, "Código": cod.get(m) or None} for m in mats] + \
                         [{"Material": k, "Código": v} for k, v in cod.items() if k not in set(mats)]
        t["materiais_de_para"] = [{"Nome no projeto": k, "Nome no cadastro": v}
                                  for k, v in (d.get("de_para") or {}).items()]
        t["materiais_apelidos"] = [{"Material": k, "Apelido": a} for k, v in (d.get("apelidos") or {}).items()
                                   for a in v]
        t["materiais_extras"] = [{"Principal": r.get("principal"), "Item": it[0],
                                  "Quantidade": it[1] if len(it) > 1 else None}
                                 for r in d.get("extras") or [] for it in r.get("itens", [])]
        t["configuracoes"] = [{"Chave": k, "Valor": _txt(v)} for k, v in (d.get("config") or {}).items()]
    elif nome == "constantes":
        t["constantes"] = [{"Código": _vz(i.get("codigo")), "Descrição": i.get("descricao"),
                            "Constante (KG por metro)": i.get("constante"),
                            **{c: _txt(v) for c, v in i.items() if c not in ("codigo", "descricao", "constante")}}
                           for i in d.get("itens") or []]
    elif nome == "usuarios":
        acessos = d.get("_acessos") or {}
        t["usuarios"] = [{"Login": k, "Nome": u.get("nome"),
                          "Perfil": "Administrador" if u.get("admin") else "Usuário",
                          "Pode alterar cadastro": bool(u.get("editar")), "Ativo": bool(u.get("ativo", True)),
                          "Criado em": _vz(u.get("criado")),
                          "Último acesso": acessos.get(k) or _vz(u.get("ultimo_acesso"))}
                         for k, u in (d.get("usuarios") or {}).items()]
    elif nome == "_acessos":
        t["acessos"] = [{"Login": k, "Último acesso": v} for k, v in (d.get("acessos") or {}).items()]
    elif nome == "equipes":
        t["equipes_pessoas"] = [{c.capitalize(): _txt(v) for c, v in p.items()} if isinstance(p, dict)
                                else {"Nome": p} for p in d.get("pessoas") or []]
        t["equipes"] = [{c.capitalize(): _txt(v) for c, v in e.items()} if isinstance(e, dict)
                        else {"Nome": e} for e in d.get("equipes") or []]
    elif nome == "carteira":
        rot = {k: r.capitalize() for k, r, _ in CAMPOS_OBRA}
        obras = []
        for o in d.get("obras") or []:
            lin = {"ID obra": o.get("id")}
            for k, r in rot.items():
                lin[_rot_coluna(r)] = _vz(o.get(k))
            for c, r in (("criado_por", "Criado por"), ("criado_em", "Criado em"),
                         ("alterado_por", "Alterado por"), ("alterado_em", "Alterado em")):
                lin[r] = _vz(o.get(c))
            for c, v in o.items():
                if c not in rot and c not in ("id", "_uid", "criado_por", "criado_em", "alterado_por", "alterado_em"):
                    lin[_rot_coluna(c)] = _txt(v)
            obras.append(lin)
        t["obras"] = obras
    elif nome == "projetos":
        linhas = []
        for k, p in (d.get("projetos") or {}).items():
            p = p or {}
            pags = p.get("paginas") or {}
            aj = p.get("ajustes") or {}
            arq, _, tam = k.rpartition("|")
            linhas.append({"Arquivo": arq or k, "Tamanho (bytes)": int(tam) if tam.isdigit() else None,
                           "Alterado em": p.get("alterado"),
                           "Balões excluídos": sum(len(c.get("excluir", [])) for c in pags.values()),
                           "Textos corrigidos": sum(len(c.get("texto", {})) for c in pags.values()),
                           "Balões marcados à mão": sum(len(c.get("novos", [])) for c in pags.values()),
                           "Fim/meio de rede à mão": sum(len(c.get("rede", {})) for c in pags.values()),
                           "Cerca conferida": any(c.get("cerca") for c in pags.values()),
                           "Materiais adicionados": len(aj.get("add", [])),
                           "Materiais tirados": len(aj.get("remover", [])),
                           "Quantidades alteradas": len(aj.get("qtd", [])),
                           "Materiais trocados": len(aj.get("trocar", []))})
        t["projetos"] = linhas
    return t


_visao_fila = {}
_visao_trava = _threading.Lock()
_visao_rodando = [False]


def _banco_tabelas():
    _mongo_db()
    return _MONGO["cli"][BANCO_TABELAS]


def _gravar_visao(nome, d, versao=None):
    tabelas = tabelas_visao(nome, d)

    def gravar(db):
        vt = _MONGO["cli"][BANCO_TABELAS]
        for col in TABELAS_DO_CONJUNTO.get(nome, list(tabelas)):
            linhas = tabelas.get(col, [])
            vt[col].delete_many({})
            if linhas:
                vt[col].insert_many([dict(l) for l in linhas])
        vt["_controle"].replace_one({"_id": nome}, {"_id": nome, "versao": versao,
                                                    "atualizado": time.strftime("%d/%m/%Y %H:%M:%S")}, upsert=True)
        vt["_dicionario"].delete_many({})
        vt["_dicionario"].insert_many([{"Tabela": a, "O que tem": b, "Uma linha por": c, "Chave": k,
                                        "Liga com": lg} for a, b, c, k, lg in DICIONARIO_TABELAS])
    _mongo(gravar)


def _dados_do_banco(db, nome):
    """Conjunto completo direto do banco "ceneged" (sem mexer no que o programa tem em memória)."""
    if nome == "_acessos":
        return {"acessos": {x["_id"]: x.get("ultimo_acesso") for x in db.acessos.find({})}}, None
    doc = db.conjuntos.find_one({"_id": nome})
    if doc is None:
        return None, None
    d = dict(_do_banco(doc.get("conteudo")) or {})
    if nome == "projetos":
        d["projetos"] = {x["chave"]: _do_banco(x.get("valor")) for x in db.projetos.find({}) if "chave" in x}
    elif nome == "carteira":
        obras = []
        for x in db.obras.find({}):
            o = {k: v for k, v in x.items() if k not in ("_id", "_gravado_em", "_gravado_por")}
            obras.append(json.loads(o["_json"]) if set(o) == {"_json"} else o)
        d["obras"] = sorted(obras, key=lambda o: o.get("id") or 0)
    elif nome == "usuarios":
        d["_acessos"] = {x["_id"]: x.get("ultimo_acesso") for x in db.acessos.find({})}
    return d, doc.get("versao")


def _trabalhar_visao():
    while True:
        with _visao_trava:
            if not _visao_fila:
                _visao_rodando[0] = False
                return
            nome = next(iter(_visao_fila))
            _visao_fila.pop(nome)
        try:
            d, versao = _mongo(lambda db: _dados_do_banco(db, nome))
            if d is not None:
                _gravar_visao(nome, d, versao)
        except Exception:
            pass                        # tabelas de ver: se falhar, refaz na próxima gravação


def atualizar_tabelas_visao(*nomes):
    """Atualiza (em segundo plano) as tabelas para ver dos conjuntos indicados."""
    if not modo_mongo():
        return
    with _visao_trava:
        for n in nomes:
            if n in TABELAS_DO_CONJUNTO:
                _visao_fila[n] = True
        if _visao_rodando[0] or not _visao_fila:
            return
        _visao_rodando[0] = True
    _threading.Thread(target=_trabalhar_visao, daemon=True).start()


AO_GRAVAR_NO_BANCO.append(atualizar_tabelas_visao)


def conferir_tabelas_visao():
    """Ao abrir o programa: refaz as tabelas que estão atrasadas em relação ao banco."""
    if not modo_mongo():
        return
    try:
        def atrasadas(db):
            vt = _MONGO["cli"][BANCO_TABELAS]
            feitas = {x["_id"]: x.get("versao") for x in vt["_controle"].find({})}
            atuais = {x["_id"]: x.get("versao") for x in db.conjuntos.find({}, {"versao": 1})}
            out = [n for n in TABELAS_DO_CONJUNTO if n != "_acessos" and n in atuais
                   and feitas.get(n) != atuais[n]]
            if "_acessos" not in feitas or "usuarios" in out:
                out.append("_acessos")
            return out
        nomes = _mongo(atrasadas)
        presentes = set(_mongo(lambda db: [x["_id"] for x in db.conjuntos.find({}, {"_id": 1})]))
    except SemBanco:
        return
    atualizar_tabelas_visao(*nomes)
    # conjuntos que ainda não foram gravados no banco (ex.: constantes com os valores padrão):
    # as tabelas saem do que o programa tem em memória
    for nome, obj in (("constantes", CONSTANTES), ("equipes", EQUIPES)):
        if nome not in presentes:
            dados = json.loads(json.dumps(obj.dados))
            _threading.Thread(target=lambda n=nome, d=dados: _gravar_visao_seguro(n, d), daemon=True).start()


def _gravar_visao_seguro(nome, d):
    try:
        _gravar_visao(nome, d)
    except Exception:
        pass
