"""Planilha dos normativos: leitura, carga e atualização das composições.

Parte do programa Levantamento de Materiais (Ceneged)."""

import os
import re

from ceneged.comum.texto import (_sem_acento, chave_nome)
from ceneged.dados.caminhos import pasta_dados
from ceneged.dados.equipes import ArquivoDados

# ---------------------------------------------------------------------------
#  Estruturas dos normativos (DIS-NOR-013, 014, 016 e 018) e tabelas de escolha
#  dos anexos. A estrutura do normativo substitui a composição de mesmo nome.
#  Os itens "A DEFINIR" são escolhidos na tabela do normativo pelo que o projeto
#  informa: poste (altura/esforço e DT/circular, do balão), tensão (do cabo) e
#  bitola do cabo (dos balões de cabo). O que não dá para saber pelo desenho fica
#  como pendência no relatório, dizendo a tabela e a informação que falta.
# ---------------------------------------------------------------------------
ARQ_ESTRUTURAS_NORMA = os.path.join(pasta_dados(), "ceneged_estruturas_normativo.json")
ARQ_TABELAS_NORMA = os.path.join(pasta_dados(), "ceneged_tabelas_normas.json")

# bitola equivalente em mm² (AWG/MCM -> mm²)
MM2_AWG = {"6": 13.3, "4": 21.2, "2": 33.6, "1/0": 53.5, "2/0": 67.4, "3/0": 85.0, "4/0": 107.2,
           "336,4": 170.5, "477": 241.7}


class DadosNorma(ArquivoDados):
    """Estruturas ou tabelas dos normativos, guardadas no banco. Vêm da planilha que o
    usuário carrega (botão "Carregar planilha dos normativos" na tela de composições)."""

    def __init__(self, caminho, chave, vazio):
        self._chave = chave
        super().__init__(caminho, {chave: vazio})

    @property
    def conteudo(self):
        self.recarregar_se_mudou()
        return self.dados.get(self._chave) or type(self.padrao[self._chave])()

    def trocar(self, novo):
        self.dados[self._chave] = novo
        self.salvar()


ESTRUTURAS_NORMA = DadosNorma(ARQ_ESTRUTURAS_NORMA, "estruturas", [])
TABELAS_NORMA = DadosNorma(ARQ_TABELAS_NORMA, "tabelas", {})

# planilha dos normativos: colunas da aba "Tabelas" -> chave usada na escolha
_COLS_TABELA = [("Normativo", None), ("Tabela", None), ("Título", None), ("Escolha por", None),
                ("Informação necessária", None), ("Cód. Nordeste", "ne"), ("Cód. Elektro", "se"),
                ("Cód. Brasília", "br"), ("Descrição", "descricao"),
                ("Bitola (mm²)", "b"), ("Bitola principal (mm²)", "p"), ("Bitola derivação (mm²)", "d"),
                ("Fase (mm²)", "f"), ("Neutro (mm²)", "n"), ("Pares principal/derivação (mm²)", "pares"),
                ("Material", "mat"), ("Tipo", "tipo"), ("Tensão (kV)", "kv"), ("Comprimento (mm)", "comp"),
                ("Cód. conector cunha", "cunha"), ("Cód. conector compressão", "comp_cod"),
                ("Postes fixos", "postes"), ("Usar sempre", "padrao")]
_COLS_POSTES = ["Tipo", "Comprimento (m)", "Resistência (daN)", "Resistência face A (daN)", "Cód. Nordeste",
                "Descrição", "Topo (mm)", "Base (mm)", "Topo face B (mm)", "Base face B (mm)", "Uso"]
_COLS_ALTURAS = ["Normativo", "Situação", "Distância do topo (m)", "Observação"]
_COLS_ESTRUT = ["Normativo", "Nº", "Estrutura", "Pág.", "Seção / Tensão", "Item", "Cód. Nordeste",
                "Cód. Elektro", "Cód. Brasília", "Descrição", "Und", "Qtd DT", "Qtd DT 36,2 kV",
                "Qtd Circular", "Qtd (única)", "Variável", "A definir?",
                "Informação necessária para definir o material", "Referência no normativo", "Observação"]


def _num_planilha(v):
    if v is None or str(v).strip() == "":
        return None
    try:
        x = float(str(v).strip().replace(",", "."))
    except ValueError:
        return None
    return x


def _faixa_planilha(v):
    """'35 a 50' -> [35, 50]; '21,2' -> 21.2"""
    t = str(v or "").strip()
    if not t:
        return None
    m = re.match(r"^\s*([\d.,]+)\s*(?:a|até|-|–)\s*([\d.,]+)\s*$", t, re.I)
    if m:
        return [_num_planilha(m.group(1)), _num_planilha(m.group(2))]
    return _num_planilha(t)


def _cod_planilha(v):
    v = str(v if v is not None else "").strip()
    if isinstance(v, str) and re.fullmatch(r"\d+\.0", v):
        v = v[:-2]
    return "" if (not v or "DEFINIR" in v.upper() or v == "-") else v


def _cabecalho(linhas, nomes, minimo=4):
    """Acha a linha de títulos (nas 15 primeiras) e devolve (linha, {título: coluna})."""
    alvo = {chave_nome(n): n for n in nomes}
    for r, lin in enumerate(linhas[:15]):
        cols = {}
        for c, v in enumerate(lin):
            k = chave_nome(str(v)) if v is not None else ""
            if k in alvo and alvo[k] not in cols:
                cols[alvo[k]] = c
        if len(cols) >= minimo:
            return r, cols
    return None, {}


def _e_exemplo(v):
    return _sem_acento(str(v or "")).strip().upper().startswith("EXEMPLO")


def ler_planilha_normativos(caminho):
    """Lê a planilha dos normativos. Aba de estruturas (colunas como a "Lista corrida") e/ou
    aba "Tabelas". Devolve (estruturas ou None, tabelas ou None, avisos)."""
    from openpyxl import load_workbook
    wb = load_workbook(caminho, read_only=True, data_only=True)
    estruturas = tabelas = None
    avisos = []
    ete = {}
    try:
        for ws in wb.worksheets:
            linhas = [list(r) for r in ws.iter_rows(values_only=True)]
            r0, cols = _cabecalho(linhas, _COLS_POSTES, 6)
            if r0 is not None and {"Tipo", "Comprimento (m)", "Topo (mm)", "Base (mm)"} <= set(cols):
                ls = []
                for lin in linhas[r0 + 1:]:
                    def g(nome):
                        c = cols.get(nome)
                        return lin[c] if c is not None and c < len(lin) else None
                    tp = _sem_acento(str(g("Tipo") or "")).strip().upper()
                    L, topo, base = _num_planilha(g("Comprimento (m)")), _num_planilha(g("Topo (mm)")), \
                        _num_planilha(g("Base (mm)"))
                    if not tp or not L or not topo or not base or _e_exemplo(g("Descrição")):
                        continue
                    l = {"tipo": "dt" if tp.startswith(("DT", "DUPLO", "D")) else "circular", "l": L,
                         "rn": _num_planilha(g("Resistência (daN)")), "rn_a": _num_planilha(g("Resistência face A (daN)")),
                         "ne": _cod_planilha(g("Cód. Nordeste")), "descricao": str(g("Descrição") or "").strip(),
                         "uso": str(g("Uso") or "").strip()}
                    if l["tipo"] == "dt":
                        l.update(a=topo, A=base, b=_num_planilha(g("Topo face B (mm)")),
                                 B=_num_planilha(g("Base face B (mm)")))
                    else:
                        l.update(topo=topo, base=base)
                    ls.append(l)
                ete[CHAVE_POSTES] = {"titulo": "Postes de concreto (DIS-ETE-011 Anexo I)", "modo": "geometria",
                                     "info": "dimensões do poste para cinta, parafuso e suporte", "linhas": ls}
                continue
            r0, cols = _cabecalho(linhas, _COLS_ALTURAS, 3)
            if r0 is not None and {"Normativo", "Distância do topo (m)"} <= set(cols):
                ls = []
                for lin in linhas[r0 + 1:]:
                    def g(nome):
                        c = cols.get(nome)
                        return lin[c] if c is not None and c < len(lin) else None
                    d = _num_planilha(g("Distância do topo (m)"))
                    if d is None or not g("Normativo") or _e_exemplo(g("Normativo")):
                        continue
                    ls.append({"norma": str(g("Normativo")).strip(), "situacao": str(g("Situação") or "").strip(),
                               "d": d, "obs": str(g("Observação") or "").strip()})
                ete[CHAVE_ALTURAS] = {"titulo": "Altura de aplicação (distância do topo)", "modo": "altura",
                                      "info": "onde a peça é fixada no poste", "linhas": ls}
                continue
            r0, cols = _cabecalho(linhas, _COLS_ESTRUT, 8)
            if r0 is not None and {"Estrutura", "Descrição"} <= set(cols) and estruturas is None:
                estruturas, idx = [], {}

                def g(lin, nome):
                    c = cols.get(nome)
                    return lin[c] if c is not None and c < len(lin) else None

                def q(v):
                    if v is None or str(v).strip() == "":
                        return None
                    if str(v).strip() == "-":
                        return "-"
                    return _num_planilha(v) if _num_planilha(v) is not None else None

                for lin in linhas[r0 + 1:]:
                    nome = str(g(lin, "Estrutura") or "").strip()
                    desc = str(g(lin, "Descrição") or "").strip()
                    if not nome or not desc or _e_exemplo(g(lin, "Normativo")):
                        continue
                    norma = str(g(lin, "Normativo") or "").strip()
                    k = (norma, nome)
                    if k not in idx:
                        pag = _num_planilha(g(lin, "Pág."))
                        pag = int(pag) if pag is not None else None
                        idx[k] = len(estruturas)
                        estruturas.append({"norma": norma, "nome": nome, "pag": pag, "itens": []})
                    estruturas[idx[k]]["itens"].append({
                        "item": str(g(lin, "Item") or "").strip(),
                        "ne": _cod_planilha(g(lin, "Cód. Nordeste")), "se": _cod_planilha(g(lin, "Cód. Elektro")),
                        "br": _cod_planilha(g(lin, "Cód. Brasília")), "desc": desc,
                        "und": str(g(lin, "Und") or "un").strip(),
                        "qdt": q(g(lin, "Qtd DT")), "qdt36": q(g(lin, "Qtd DT 36,2 kV")),
                        "qcirc": q(g(lin, "Qtd Circular")), "qunica": q(g(lin, "Qtd (única)")),
                        "secao": str(g(lin, "Seção / Tensão") or "").strip(),
                        "variavel": str(g(lin, "Variável") or "").strip(),
                        "adef": str(g(lin, "A definir?") or "").strip().upper() == "SIM",
                        "info": str(g(lin, "Informação necessária para definir o material") or "").strip(),
                        "ref": str(g(lin, "Referência no normativo") or "").strip(),
                        "obs": str(g(lin, "Observação") or "").strip()})
                continue
            r0, cols = _cabecalho(linhas, [n for n, _ in _COLS_TABELA], 6)
            if r0 is not None and {"Normativo", "Tabela", "Escolha por"} <= set(cols) and tabelas is None:
                tabelas = {}
                for n_lin, lin in enumerate(linhas[r0 + 1:], start=r0 + 2):
                    def g(nome):
                        c = cols.get(nome)
                        return lin[c] if c is not None and c < len(lin) else None
                    norma, tab = str(g("Normativo") or "").strip(), str(g("Tabela") or "").strip()
                    if not norma or not tab or _e_exemplo(norma):
                        continue
                    t = tabelas.setdefault(f"{norma}|{tab}", {"titulo": str(g("Título") or "").strip(),
                                                             "modo": str(g("Escolha por") or "").strip().lower(),
                                                             "info": str(g("Informação necessária") or "").strip(),
                                                             "linhas": []})
                    l = {}
                    for nome, ch in _COLS_TABELA:
                        v = g(nome)
                        if ch is None or v is None or str(v).strip() == "":
                            continue
                        if ch in ("ne", "se", "br", "cunha", "comp_cod"):
                            v = _cod_planilha(v)
                        elif ch in ("p", "d"):
                            v = _faixa_planilha(v)
                        elif ch == "pares":
                            v = [[_num_planilha(a) for a in par.split("/")] for par in re.split(r"[;|]", str(v))
                                 if "/" in par]
                        elif ch in ("mat", "tipo", "descricao"):
                            v = str(v).strip()
                        elif ch == "postes":
                            v = [x.strip() for x in re.split(r"[;,]", str(v)) if x.strip()]
                        elif ch == "padrao":
                            v = True if _sem_acento(str(v)).strip().upper() in ("S", "SIM", "X", "1") else None
                        else:
                            v = _num_planilha(v)
                        if v in (None, "", []):
                            continue
                        l["comp" if ch == "comp_cod" else ch] = v
                    if t["modo"] != "nua" and str(l.get("tipo", "")).lower() == "cunha":
                        l.pop("tipo")
                        l["cunha"] = True  # conector tipo cunha (preferido na rede protegida)
                    if t["modo"] != "nua":
                        for c in ("ne", "se", "br", "descricao"):
                            l.setdefault(c, "")
                    t["linhas"].append(l)
    finally:
        wb.close()
    # aba sem nenhuma linha válida (ex.: o modelo só com exemplos) não troca nada no sistema
    if not estruturas:
        estruturas = None
    if not tabelas:
        tabelas = None
    ete = {k: v for k, v in ete.items() if v["linhas"]}
    if estruturas is None and tabelas is None and not ete:
        avisos.append("Nenhuma aba reconhecida. A planilha precisa da aba de estruturas (colunas Normativo, "
                      "Estrutura, Item, Cód. Nordeste, Descrição...) e/ou da aba Tabelas.")
    return estruturas, tabelas, avisos, ete


# ---------------------------------------------------------------------------
#  Postes (DIS-ETE-011): dimensões e diâmetro no ponto de fixação
#  (aba "Postes" e aba "Altura de aplicação" da planilha dos normativos)
# ---------------------------------------------------------------------------
CHAVE_POSTES = "DIS-ETE-011|Postes"
CHAVE_ALTURAS = "DIS-ETE-011|Altura de aplicação"
