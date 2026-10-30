"""Informações dos cabos e das tabelas: região do código, faixas, cabo da rede.

Parte do programa Levantamento de Materiais (Ceneged)."""

import re

from ceneged.comum.texto import _sem_acento
from ceneged.leitura_pdf.rede import _familia
from ceneged.dados.cadastro import (CADASTRO, bitolas_do_cabo)
from ceneged.dados.normativos import MM2_AWG

def cabo_info(txt):
    """Bitola (mm², AWG/MCM convertido) e tipo de um cabo escrito no projeto.
    '3#185mm²2-XLPE' -> 185 coberto; '3xA35P(7,94)-13,8kV' -> 35 coberto; '3xS4/0-13,8kV' -> 4/0 AWG;
    '3#4CAA' -> 4 AWG nu; 'PB70' / '3x70+1x50' -> multiplexado (fase 70, neutro 50)."""
    if not txt:
        return None
    t = _sem_acento(str(txt)).upper()
    kv = None
    m = re.search(r"(\d+[,.]\d+|\d+)\s*KV", t)
    if m:
        v = float(m.group(1).replace(",", "."))
        kv = 36.2 if v > 25 else 15.0
    s = re.sub(r"\(.*?\)", " ", re.sub(r"\d+[,.]?\d*\s*KV", " ", t))
    mat = "cobre" if ("COBRE" in s or re.search(r"\bCU\b", s)) else ("cal" if "CAL" in s else "aluminio")
    if RE_CABO_PB.search(s) or re.search(r"\d\s*X\s*\d+\s*\+\s*\d\s*X\s*\d+", s):
        b = bitolas_do_cabo(s)
        if b:
            return {"fase": float(b[0]), "neutro": float(b[1]), "tipo": "multiplexado", "mat": mat, "kv": kv,
                    "texto": str(txt)}
    fase = None
    m = re.search(r"(\d)/0", s)
    if m:
        fase = MM2_AWG[m.group(1) + "/0"]
    elif re.search(r"336[,.]4", s):
        fase = MM2_AWG["336,4"]
    elif re.search(r"\b477\b", s):
        fase = MM2_AWG["477"]
    else:
        m = re.search(r"[#X]\s*[A-Z]?\s*(\d{1,3})(?:[,.]\d+)?", s)
        if m:
            n = int(m.group(1))
            fase = MM2_AWG[str(n)] if (n <= 6 and str(n) in MM2_AWG) else float(n)
    if fase is None:
        return None
    coberto = bool(re.search(r"XLPE|PROT|COMPACT", s) or re.search(r"\d\s*X\s*A\s*\d+\s*P", s))
    return {"fase": fase, "neutro": None, "tipo": "coberto" if coberto else "nu", "mat": mat, "kv": kv,
            "texto": str(txt)}


def _cod_regiao(l, cad=None):
    reg = _sem_acento((cad or CADASTRO).config.get("regiao", "Nordeste")).upper()
    if reg.startswith(("ELEKTRO", "SUDESTE")):
        return l.get("se") or ""
    if reg.startswith("BRASILIA"):
        return l.get("br") or ""
    return l.get("ne") or ""


def _tabela_do_item(it, norma):
    """'Tabela 17 do DIS-NOR-013' -> 'DIS-NOR-013|Tabela 17' (com os acertos de referência
    trocada no normativo: conector citado na tabela de laços, cinta citada na de parafusos)."""
    ref = it.get("ref") or ""
    m = re.search(r"(Tabela|TABELA|Quadro)\s+(\d+)\s+do\s+(DIS-NOR-\d+)", ref)
    desc = _sem_acento(it.get("desc", "")).upper()
    if not m:
        if re.search(r"Nota 5", ref) and "PARAFUSO" in desc:
            return f"{norma}|Tabela 4"
        return None
    tipo = "Quadro" if m.group(1) == "Quadro" else "Tabela"
    n, nm = int(m.group(2)), m.group(3)
    if nm == "DIS-NOR-018" and n == 11 and "CONECTOR" in desc:
        n = 1
    if nm == "DIS-NOR-014" and n == 4 and "PERFURANTE" in desc:
        n = 5
    if nm == "DIS-NOR-016" and n == 6 and "PARAFUSO" in desc:
        n = 5
    if nm == "DIS-NOR-016" and n == 5 and "CINTA" in desc:
        n = 4
    return f"{nm}|{tipo} {n}"


def _contem(faixa, v, folga=0.06):
    return faixa[0] * (1 - folga) <= v <= faixa[1] * (1 + folga)


def _dist_faixa(faixa, v):
    return 0.0 if _contem(faixa, v) else min(abs(v - faixa[0]), abs(v - faixa[1])) / max(v, 1.0)


def _cabo_da_rede(norma, ctx):
    """O cabo da folha que é do tipo de rede do normativo: 013 = coberto (compacta),
    014 = multiplexado BT, 016 = multiplexado MT, 018 = nu. O de mais metros."""
    if norma == "DIS-NOR-014" and ctx.get("pb"):
        c = cabo_info(f"PB{ctx['pb']}")
        if c:
            return c
    quer = {"DIS-NOR-013": "coberto", "DIS-NOR-014": "multiplexado", "DIS-NOR-016": "multiplexado",
            "DIS-NOR-018": "nu"}.get(norma)
    for t in ctx.get("cabos") or []:
        c = cabo_info(t)
        if not c or c["tipo"] != quer:
            continue
        if norma == "DIS-NOR-016" and not c.get("kv") and _familia(t) != "MT":
            continue                                   # 016: multiplexado da média tensão
        if norma == "DIS-NOR-014" and _familia(t) == "MT":
            continue
        return c
    if quer and (ctx.get("cabos") is not None):
        return None
    return cabo_info(ctx.get("cabo_bt") if norma == "DIS-NOR-014" else ctx.get("cabo_mt"))


# Alça preformada de distribuição (galvanizada): a bitola depende do cabo PB do vão.
RE_CABO_PB = re.compile(r"\bPB\s*-?\s*(\d{2,3})\b")
