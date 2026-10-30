"""Banco SQLite (ceneged.db) e tabelas de consulta.

Parte do programa Levantamento de Materiais (Ceneged)."""

import json
import os
import time
import sqlite3

from ceneged.dados.caminhos import (modo_mongo, modo_onedrive, pasta_dados)

ARQ_BANCO = os.path.join(pasta_dados(), "ceneged.db")


def _banco():
    """Conexão com o banco (cria a tabela na primeira vez). Sem WAL: a pasta pode ser
    compartilhada na rede, e o modo padrão de diário é o que funciona nela."""
    con = sqlite3.connect(ARQ_BANCO, timeout=20)
    con.execute("CREATE TABLE IF NOT EXISTS dados (nome TEXT PRIMARY KEY, conteudo TEXT NOT NULL, "
                "versao INTEGER NOT NULL DEFAULT 1, alterado TEXT)")
    return con


def _nome_dados(caminho):
    """'.../ceneged_cadastro.json' -> 'cadastro'"""
    n = os.path.splitext(os.path.basename(caminho))[0]
    return n[len("ceneged_"):] if n.startswith("ceneged_") else n


def _gravar_banco(nome, dados):
    con = _banco()
    try:
        with con:
            con.execute("INSERT INTO dados (nome, conteudo, versao, alterado) VALUES (?, ?, 1, ?) "
                        "ON CONFLICT(nome) DO UPDATE SET conteudo = excluded.conteudo, "
                        "versao = dados.versao + 1, alterado = excluded.alterado",
                        (nome, json.dumps(dados, ensure_ascii=False), time.strftime("%Y-%m-%d %H:%M:%S")))
        try:
            with con:
                _tabelas_de_consulta(con, nome, dados)
        except Exception:
            pass                       # as tabelas de consulta são só para ver; o dado já está salvo
    finally:
        con.close()


# Tabelas de consulta: o mesmo conteúdo da tabela "dados", aberto em linhas e colunas
# (uma coluna por campo) para ver e filtrar num visualizador de SQLite. São refeitas a
# cada gravação; o programa não lê delas (mudar algo nelas não muda o programa).
def _tab_consulta(con, tabela, linhas):
    con.execute(f'DROP TABLE IF EXISTS "{tabela}"')
    cols = []
    for l_ in linhas:
        for k in l_:
            if k not in cols:
                cols.append(k)
    if not cols:
        cols = ["vazio"]

    def val(v):
        if isinstance(v, bool):
            return "sim" if v else "não"
        if isinstance(v, (dict, list, tuple)):
            if isinstance(v, (list, tuple)) and all(not isinstance(x, (dict, list, tuple)) for x in v):
                return ", ".join(str(x) for x in v)
            return json.dumps(v, ensure_ascii=False)
        return v
    con.execute(f'CREATE TABLE "{tabela}" (' + ", ".join(f'"{c}"' for c in cols) + ")")
    if linhas:
        con.executemany(f'INSERT INTO "{tabela}" VALUES (' + ", ".join("?" * len(cols)) + ")",
                        [[val(l_.get(c)) for c in cols] for l_ in linhas])


def _linhas_de_lista(lista):
    return [dict(x) if isinstance(x, dict) else {"valor": x} for x in lista]


def _tabelas_de_consulta(con, nome, d):
    if not isinstance(d, dict):
        return
    if nome == "cadastro":
        cod = d.get("codigos", {}) or {}
        mats = list(d.get("materiais", []) or [])
        _tab_consulta(con, "cadastro_materiais",
                      [{"material": m, "codigo": cod.get(m, "")} for m in mats] +
                      [{"material": k, "codigo": v} for k, v in cod.items() if k not in set(mats)])
        _tab_consulta(con, "cadastro_de_para", [{"nome_no_projeto": k, "nome_no_cadastro": v}
                                                for k, v in (d.get("de_para", {}) or {}).items()])
        _tab_consulta(con, "cadastro_extras", [{"principal": r.get("principal"), "item": it[0],
                                                "qtd": it[1] if len(it) > 1 else None}
                                               for r in d.get("extras", []) or [] for it in r.get("itens", [])])
        _tab_consulta(con, "cadastro_apelidos", [{"material": k, "apelido": a}
                                                 for k, v in (d.get("apelidos", {}) or {}).items() for a in v])
        _tab_consulta(con, "cadastro_escolhas", [{"chave": k, "codigo": v}
                                                 for k, v in (d.get("escolhas", {}) or {}).items()])
        _tab_consulta(con, "cadastro_config", [{"chave": k, "valor": v}
                                               for k, v in (d.get("config", {}) or {}).items()])
    elif nome == "usuarios":
        _tab_consulta(con, "usuarios", [dict({"login": k}, **{c: v for c, v in (u or {}).items()
                                                               if c not in ("sal", "hash", "senha")})
                                        for k, u in (d.get("usuarios", {}) or {}).items()])
    elif nome == "composicoes":
        kits = d.get("kits", []) or []
        _tab_consulta(con, "composicoes", [{"id": k.get("id"), "categoria": k.get("categoria"),
                                            "nome": k.get("nome"), "apelidos": k.get("apelidos", []),
                                            "automatica": k.get("auto"), "qtd_itens": len(k.get("itens", []))}
                                           for k in kits])
        _tab_consulta(con, "composicoes_itens", [dict({"composicao_id": k.get("id"), "composicao": k.get("nome")}, **i)
                                                 for k in kits for i in k.get("itens", [])])
    elif nome == "projetos":
        linhas = []
        for k, p in (d.get("projetos", {}) or {}).items():
            pags = (p or {}).get("paginas", {}) or {}
            aj = (p or {}).get("ajustes", {}) or {}
            arq, _, tam = k.rpartition("|")
            linhas.append({"arquivo": arq or k, "tamanho_bytes": int(tam) if tam.isdigit() else None,
                           "alterado": (p or {}).get("alterado"),
                           "baloes_excluidos": sum(len(c.get("excluir", [])) for c in pags.values()),
                           "textos_corrigidos": sum(len(c.get("texto", {})) for c in pags.values()),
                           "baloes_marcados": sum(len(c.get("novos", [])) for c in pags.values()),
                           "fim_meio_a_mao": sum(len(c.get("rede", {})) for c in pags.values()),
                           "cerca_conferida": any(c.get("cerca") for c in pags.values()),
                           "materiais_adicionados": len(aj.get("add", [])),
                           "materiais_tirados": len(aj.get("remover", [])),
                           "quantidades_alteradas": len(aj.get("qtd", [])),
                           "materiais_trocados": len(aj.get("trocar", []))})
        _tab_consulta(con, "projetos", linhas)
    elif nome == "tabelas_normas":
        linhas = []
        for k, t in (d.get("tabelas", {}) or {}).items():
            norma, _, tab = k.partition("|")
            for l in t.get("linhas", []):
                linhas.append(dict({"normativo": norma, "tabela": tab, "titulo": t.get("titulo"),
                                    "escolha_por": t.get("modo")}, **l))
        _tab_consulta(con, "normativo_tabelas", linhas)
    else:
        # equipes, carteira, constantes e o que vier: cada lista vira uma tabela
        for k, v in d.items():
            if isinstance(v, list):
                tab = nome if (k == "itens" or len([x for x in d.values() if isinstance(x, list)]) == 1) \
                    else f"{nome}_{k}"
                linhas = _linhas_de_lista(v)
                _tab_consulta(con, tab, linhas)
                # lista de registros dentro de cada registro (ex.: itens de cada obra da
                # carteira): tabela à parte, com os primeiros campos do registro de cima
                subs = {c for l_ in linhas for c, x in l_.items()
                        if isinstance(x, list) and x and all(isinstance(y, dict) for y in x)}
                for c in sorted(subs):
                    sub = []
                    for l_ in linhas:
                        pai = {f"{tab}_{c2}": x2 for c2, x2 in list(l_.items())
                               if not isinstance(x2, (list, dict))}
                        pai = dict(list(pai.items())[:3])
                        for y in l_.get(c) or []:
                            if isinstance(y, dict):
                                sub.append(dict(pai, **y))
                    _tab_consulta(con, f"{tab}_{c}", sub)


def montar_tabelas_de_consulta():
    """Refaz todas as tabelas de consulta a partir da tabela "dados" (ao abrir o programa)."""
    if modo_onedrive() or modo_mongo():
        return                       # no modo OneDrive/MongoDB elas são feitas a cada gravação (banco local)
    try:
        con = _banco()
    except sqlite3.Error:
        return
    try:
        rows = con.execute("SELECT nome, conteudo FROM dados").fetchall()
        with con:
            for nome, conteudo in rows:
                try:
                    _tabelas_de_consulta(con, nome, json.loads(conteudo))
                except Exception:
                    pass
    except sqlite3.Error:
        pass
    finally:
        con.close()
