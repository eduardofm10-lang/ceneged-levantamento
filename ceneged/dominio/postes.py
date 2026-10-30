"""Postes (DIS-ETE-011): tipo, geometria e altura de aplicação.

Parte do programa Levantamento de Materiais (Ceneged)."""

import re

from ceneged.comum.texto import (_sem_acento, fmt_num, info_poste, normaliza_codigo)
from ceneged.dados.cadastro import CADASTRO
from ceneged.dados.normativos import (CHAVE_ALTURAS, CHAVE_POSTES, MM2_AWG, TABELAS_NORMA)
from ceneged.dominio.tabelas import _cod_regiao
from ceneged.dominio.materiais import materiais_conhecidos

def _linhas_postes():
    return (TABELAS_NORMA.conteudo.get(CHAVE_POSTES) or {}).get("linhas", [])


def _postes_de(poste, tipo=None):
    ls = [l for l in _linhas_postes() if l.get("l") and abs(l["l"] - poste["altura"]) < 0.01 and
          (tipo is None or l.get("tipo") == tipo)]
    ex = [l for l in ls if poste.get("esforco") in (l.get("rn"), l.get("rn_a"))]
    return ex, ls


def tipo_do_poste(poste, ctx=None, cad=None):
    """'dt' ou 'circular'. Escrito no balão (400/12DT, 1000/12C) vale; senão, pela DIS-ETE-011:
    o tipo que existe na região com essa altura e esforço (no Nordeste 400/12 só existe DT e
    1000/12 só circular); senão, a configuração."""
    cad = cad or CADASTRO
    ctx = ctx or {}
    if poste and poste.get("tipo"):
        return poste["tipo"]
    if poste:
        ex, _ = _postes_de(poste)
        tipos = {l["tipo"] for l in ex if l.get("ne")} or {l["tipo"] for l in ex}
        if len(tipos) == 1:
            return tipos.pop()
    elif _linhas_postes():
        # estrutura sem poste no balão nem etiqueta legível: no Nordeste os postes de rede
        # (400/600 daN) são DT
        return cad.config.get("poste_sem_info", "dt")
    return ctx.get("padrao") or cad.config.get("poste_padrao", "circular")


def geometria_do_poste(poste, tipo):
    ex, ls = _postes_de(poste, tipo)
    if ex:
        return ex[0]
    if ls:                                      # mesma altura, esforço mais perto
        return min(ls, key=lambda l: abs((l.get("rn") or 0) - (poste.get("esforco") or 0)))
    return None


def altura_de_aplicacao(norma, ctx, equipamento=False):
    """Distância do topo (m) onde a peça é fixada (aba "Altura de aplicação")."""
    alt = {}
    for l in (TABELAS_NORMA.conteudo.get(CHAVE_ALTURAS) or {}).get("linhas", []):
        alt[(l.get("norma", "").upper(), _sem_acento(l.get("situacao", "")).upper())] = l.get("d")
    if equipamento:
        d = alt.get(("EQUIPAMENTO", "SUPORTE DE EQUIPAMENTO"))
        if d is not None:
            return d, "suporte de equipamento"
    if norma == "DIS-NOR-014":
        com_mt = bool(ctx.get("cabo_mt")) or (ctx.get("poste") or {}).get("altura", 0) >= 11
        sit = "BT COM MT NO POSTE" if com_mt else "BT SOZINHA NO POSTE"
        d = alt.get((norma, sit))
        return (d if d is not None else (1.5 if com_mt else 0.5)), sit.lower()
    d = alt.get((norma, "MT"))
    return (d if d is not None else 0.5), "MT"


def _dim_no_ponto(g, tipo, d):
    """Diâmetro (circular) ou face A (DT) em mm a d metros do topo."""
    L = g["l"]
    if tipo == "dt":
        return g["a"] + (g["A"] - g["a"]) * d / L
    return g["topo"] + (g["base"] - g["topo"]) * d / L


def _mm_da_desc(desc, padrao):
    m = re.search(padrao, _sem_acento(desc).upper())
    return float(m.group(1).replace(",", ".")) if m else None


def _peca_do_item(desc):
    d = _sem_acento(desc or "").upper()
    for w in ("CINTA", "PARAFUSO", "SUPORTE"):
        if w in d:
            return w
    return None


def _postes_fixos(l):
    """Coluna "Postes fixos" de uma linha: ['9/600', '11/400 DT'] -> [info_poste...]"""
    out = []
    for t in l.get("postes") or []:
        t2 = re.sub(r"\s+", "", str(t)).upper()
        m = re.fullmatch(r"(\d{1,2})/(\d{3,4})(DT|D|C|CIRC|CIRCULAR)?", t2)
        p = None
        if m:                                   # "9/600" (altura/resistência) como no relatório
            tp = m.group(3)
            p = {"altura": int(m.group(1)), "esforco": int(m.group(2)),
                 "tipo": None if not tp else ("dt" if tp.startswith("D") else "circular")}
        else:
            p = info_poste(t2)
        if p:
            out.append(p)
    return out


def linha_pelo_poste(peca, linhas, p, tipo, norma, ctx, cad, ncruz=0):
    """Linha da tabela para a peça (CINTA/PARAFUSO/SUPORTE) neste poste.
    -> (linha ou None, texto de onde veio). A coluna "Postes fixos" manda mais que o cálculo."""
    for l in linhas:
        if _peca_do_item(l.get("descricao")) != peca:
            continue
        for fx in _postes_fixos(l):
            if fx["altura"] == p["altura"] and fx["esforco"] == p["esforco"] and fx["tipo"] in (None, tipo):
                return l, f"fixado na tabela para o poste {p['altura']}/{p['esforco']}"
    g = geometria_do_poste(p, tipo)
    if not g:
        return None, f"poste {p['altura']}/{p['esforco']} não está na tabela de postes (DIS-ETE-011)"
    d, sit = altura_de_aplicacao(norma, dict(ctx or {}, poste=p), peca == "SUPORTE")
    dim = _dim_no_ponto(g, tipo, d)
    onde = f"{'face A' if tipo == 'dt' else 'Ø'} {dim:.0f} mm a {fmt_num(d)} m do topo"

    def melhor(cands, alvo):
        ok_ = sorted([(v, l) for v, l in cands if v is not None and v >= alvo - 2], key=lambda x: x[0])
        return ok_[0][1] if ok_ else None

    if peca == "CINTA":
        if tipo == "dt":
            return None, "cinta em poste DT"
        l = melhor([(_mm_da_desc(l.get("descricao", ""), r"CINTA.*?(\d+)\s*MM"), l) for l in linhas
                    if "CINTA" in _sem_acento(l.get("descricao", "")).upper() and _cod_regiao(l, cad)], dim)
    elif peca == "PARAFUSO":
        ncruz = min(int(ncruz or 0), 2)
        alvo = dim + 35 + 90 * ncruz            # poste + cruzeta(s) 90 mm + arruela/porca/sobra
        onde += f" + {90 * ncruz + 35} mm"
        l = melhor([(_mm_da_desc(l.get("descricao", ""), r"M16\s*X\s*(\d+)"), l) for l in linhas
                    if _cod_regiao(l, cad)], alvo)
    elif peca == "SUPORTE":
        if tipo == "dt":
            cs = [l for l in linhas if "DUPLO T" in _sem_acento(l.get("descricao", "")).upper()]
            l = cs[0] if cs else None
        else:
            l = melhor([(_mm_da_desc(l.get("descricao", ""), r"POSTE CIRCULAR\s*(\d+)\s*MM"), l)
                        for l in linhas if "TRAFO" not in _sem_acento(l.get("descricao", "")).upper()], dim)
    else:
        return None, ""
    return l, onde


def escolher_pelo_poste(it, norma, linhas, ctx, cad, rot):
    """Cinta, parafuso ou suporte pelo poste do balão + DIS-ETE-011. None = não deu."""
    p = ctx["poste"]
    tipo = ctx.get("_tipo_poste") or tipo_do_poste(p, ctx, cad)
    nome_p = f"{p['altura']}/{p['esforco']} {'DT' if tipo == 'dt' else 'circular'}"
    peca = _peca_do_item(it.get("desc"))
    if not peca:
        return None
    l, onde = linha_pelo_poste(peca, linhas, p, tipo, norma, ctx, cad, ctx.get("_cruzetas") or 0)
    if l is None:
        if "não está na tabela" in onde:
            return "", it["desc"], f"{rot}: {onde}"
        if onde == "cinta em poste DT":
            return "", it["desc"], f"{rot}: cinta em poste DT ({nome_p}) - confira"
        return "", it["desc"], f"{rot}: nenhum tamanho serve (poste {nome_p}: {onde})"
    if peca == "SUPORTE" and not _cod_regiao(l, cad):
        ger = next((x for x in linhas if _cod_regiao(x, cad) and
                    not re.search(r"\d+\s*MM|TRAFO", _sem_acento(x.get("descricao", "")).upper())), None)
        if ger:
            return _cod_regiao(ger, cad), f"{ger['descricao']} ({l['descricao']})", None
    return _cod_regiao(l, cad), l.get("descricao") or it["desc"], None


def _bitola_txt(v):
    if v is None or v == "":
        return ""
    if isinstance(v, list):
        return f"{_bitola_txt(v[0])} a {_bitola_txt(v[1])}" if len(v) == 2 else ", ".join(map(_bitola_txt, v))
    awg = next((k for k, mm in MM2_AWG.items() if abs(mm - float(v)) < 0.15), None)
    return f"{awg} {'MCM' if awg in ('336,4', '477') else 'AWG'} ({fmt_num(v)} mm²)" if awg else f"{fmt_num(v)} mm²"


def _faixas_da_desc(desc):
    """'CONEC PERF RD COMPACTA 35-70 MM/35-70 MM' -> [[35, 70], [35, 70]] (faixas de bitola em mm²)"""
    return [[float(a), float(b)] for a, b in re.findall(r"(\d+(?:,\d+)?)\s*-\s*(\d+(?:,\d+)?)\s*MM(?!\s*X)",
                                                       _sem_acento(desc or "").upper().replace(",", "."))
            if float(a) < float(b)]


def descricao_do_codigo(cod):
    """Nome de um código: das tabelas dos normativos, do cadastro ou das composições."""
    cod = normaliza_codigo(cod or "")
    if not cod:
        return ""
    for t in TABELAS_NORMA.conteudo.values():
        for l in t.get("linhas", []):
            if normaliza_codigo(l.get("ne") or "") == cod and l.get("descricao"):
                return l["descricao"]
    try:
        for c, nome, und in materiais_conhecidos().values():
            if normaliza_codigo(c or "") == cod:
                return nome
    except Exception:
        pass
    return ""


def codigo_nua(l, cad=None):
    """Rede nua (DIS-NOR-018 Tabela 1): código usado (compressão ou cunha, pela configuração)."""
    pref = (cad or CADASTRO).config.get("conector_nua", "compressao")
    if pref == "compressao" and l.get("comp"):
        return str(l["comp"])
    return str(l.get("cunha") or l.get("comp") or "")
