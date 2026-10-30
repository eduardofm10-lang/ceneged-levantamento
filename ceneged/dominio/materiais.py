"""Materiais: constantes, parecidos, itens dos kits, alças.

Parte do programa Levantamento de Materiais (Ceneged)."""

import re

from ceneged.comum.texto import (_sem_acento, _und, chave_nome, formata_num, normaliza_codigo)
from ceneged.leitura_pdf.rede import _familia
from ceneged.dados.cadastro import (CADASTRO, bitolas_do_cabo)
from ceneged.dominio.baloes import materiais_do_balao
from ceneged.dados.composicoes import COMPOSICOES
from ceneged.dados.constantes import (CONSTANTES, _num_br)

def converter_para_kg(tabela):
    """Linhas do relatório em metros que têm constante viram KG (metros × constante)."""
    for chave in list(tabela):
        lin = tabela.get(chave)
        if lin is None or lin["unidade"] != "M":
            continue
        k = CONSTANTES.para(lin.get("codigo"), lin["material"])
        if not k:
            continue
        metros = lin["qtd"]
        tabela.pop(chave)
        lin["qtd"] = metros * k
        lin["unidade"] = "KG"
        lin["partes"] = {f"{d_} ({formata_num(q_)} m × {_num_br(k)})": q_ * k
                         for d_, q_ in lin.get("partes", {}).items()}
        nova = (chave[0], chave[1], "KG")
        if nova in tabela:                        # já havia o mesmo material em KG: soma
            t = tabela[nova]
            t["qtd"] += lin["qtd"]
            t["refs"] += lin["refs"]
            t["origens"] |= lin["origens"]
            for d_, q_ in lin["partes"].items():
                t["partes"][d_] = t["partes"].get(d_, 0) + q_
        else:
            tabela[nova] = lin


def _nums_material(t):
    """'CABO NU CAA 1/0 RAVEN' -> {'1/0'}; '35,00MM2' -> {'35'}; '4 AWG' -> {'4'}."""
    t = _sem_acento(t).upper()
    out = set(re.findall(r"\d+/\d+", t))
    t = re.sub(r"\d+/\d+", " ", t)
    for n in re.findall(r"\d+(?:[.,]\d+)?", t):
        v = float(n.replace(",", "."))
        out.add(str(int(v)) if v == int(v) else f"{v:g}")
    return out


def _palavras_material(t):
    return [w for w in re.findall(r"[A-Z]{2,}", _sem_acento(t).upper()) if w not in ("MM", "DE", "DA", "DO", "AWG")]


def achar_material_parecido(descricao):
    """Material do sistema (cadastro + materiais extras) com o mesmo significado:
    'CABO NU COBRE 35,00MM2' -> 'CABO COBRE NU C2A MD 35 MM2'. -> (código, nome) ou None."""
    nums, pals = _nums_material(descricao), _palavras_material(descricao)
    if not pals:
        return None
    k = chave_nome(descricao)
    notas = []
    for cod, nome, _ in materiais_conhecidos().values():
        if chave_nome(nome) == k:
            return cod, nome
        if not nums <= _nums_material(nome):
            continue
        ps = _palavras_material(nome)
        achou = sum(1 for w in pals if any(p == w or (len(w) >= 4 and p.startswith(w)) for p in ps))
        cob = achou / len(pals)
        if cob >= 1.0:                       # todas as palavras (CA não é CAA; SWAN não é RAVEN)
            notas.append((cob, CADASTRO.cadastrado(nome), -abs(len(ps) - len(pals)), bool(cod), cod, nome))
    if not notas:
        return None
    notas.sort(reverse=True)
    if len(notas) > 1 and notas[0][:4] == notas[1][:4] and notas[0][5] != notas[1][5]:
        return None                                   # empate: não adivinha
    return notas[0][4], notas[0][5]


def ligar_constantes(itens):
    """Troca a descrição (e o código vazio) pelo nome do material do sistema. -> nº de ligados."""
    n = 0
    for i in itens:
        r = achar_material_parecido(i["descricao"])
        if r:
            cod, nome = r
            if chave_nome(nome) != chave_nome(i["descricao"]):
                i.setdefault("planilha", i["descricao"])
            i["descricao"] = nome
            if cod:
                i["codigo"] = normaliza_codigo(cod)
            n += 1
    return n


def materiais_conhecidos():
    """{chave: (código, nome, und)} de tudo que o programa conhece (cadastro + composições)."""
    vistos = {}
    for k in COMPOSICOES.kits:
        for i in k["itens"]:
            ch = i["codigo"] or "n:" + chave_nome(i["nome"])
            vistos.setdefault(ch, (i["codigo"], i["nome"], i["und"]))
    for n in CADASTRO.materiais:
        cod = CADASTRO.codigo_de(n)
        ch = cod or "n:" + chave_nome(n)
        if ch not in vistos:
            vistos[ch] = (cod, n, "CDA")
        elif cod:
            vistos[ch] = (cod, n, vistos[ch][2])           # nome do cadastro tem preferência
    return vistos


def contexto_pagina(pg):
    """Cabos (BT e MT) mais usados na página e tensão da rede MT."""
    if pg is None:
        return {}
    metros = dict(getattr(pg, "cabos", {}) or {})
    for b in pg.baloes or []:
        if b.get("tipo") == "cabo":
            metros.setdefault(b["texto"].strip(), 0.0)
        elif b.get("tipo") != "material":
            for nome, un, q in materiais_do_balao(b):
                if un == "M":
                    metros[nome] = metros.get(nome, 0.0) + q
    bt = sorted((m, c) for c, m in metros.items() if _familia(c) != "MT" and bitolas_do_cabo(c))
    mt = sorted((m, c) for c, m in metros.items() if _familia(c) == "MT")
    texto = "".join(c["c"] for c in (pg.chars or []))
    cfg = CADASTRO.config.get("kv", "auto")
    if cfg in ("15", "36.2"):
        kv = float(cfg)
    else:
        kv = 36.2 if re.search(r"34[,.]5\s*KV|36[,.]2\s*KV", texto.upper()) else 15.0
    return {"cabo_bt": bt[-1][1] if bt else None, "cabo_mt": mt[-1][1] if mt else None, "kv": kv,
            "cabos": [c for m, c in sorted(((m, c) for c, m in metros.items()), reverse=True)]}


def codigo_do_item(nome, codigo, cad=None):
    """Código de um material da planilha de materiais extras: vale o do Cadastro de
    materiais (mesmo nome, ou nome ligado à mão); se lá não tiver, o da planilha."""
    cad = cad or CADASTRO
    real, como, _ = cad.resolver(nome)
    if como in ("igual", "manual"):
        c = cad.codigo_de(real)
        if c:
            return c
    return normaliza_codigo(codigo or "")


def itens_do_kit(kit, qtd, ref, nome_balao=""):
    """Materiais de uma composição para `qtd` unidades (ou metros) do principal."""
    saida = []
    for i in kit["itens"]:
        cod = codigo_do_item(i["nome"], i["codigo"]) if i["codigo"] or not i.get("pendente") else ""
        saida.append({"nome": i["nome"], "original": i["nome"], "un": _und(i["und"]), "qtd": i["qtd"] * qtd, "codigo": cod,
                      "pendente": (i.get("pendente") or (None if cod else "sem código (nem no cadastro nem nos materiais extras)")),
                      "origem": "estrutura", "de": kit["nome"], "ref": ref, "mov": i["mov"],
                      "partes": {kit["nome"]: i["qtd"] * qtd}})
    return saida
ALCA_DIST_POR_PB = {  # PB -> (código, nome se não estiver no cadastro)
    50: ("3430550", "ALCA PREF DIST GALV 35,00MM2."),
    70: ("3430545", "ALCA PREF DIST GALV 50,00MM2 N. ISOL."),
    120: ("3430549", "ALCA PREF DIST GALV 70,00MM2 N. ISOL."),
}
CODIGOS_ALCA_DIST = {"3430550", "3430545", "3430549", "3430553"}


def e_alca_dist(nome, codigo=""):
    return (normaliza_codigo(codigo or "") in CODIGOS_ALCA_DIST
            or chave_nome(nome).startswith("ALCAPREFDISTGALV"))


def _alca_do_pb(pb, cad):
    cod, nome_pad = ALCA_DIST_POR_PB[pb]
    return cod, (cad.nome_do_codigo(cod) or nome_pad)


def alcas_por_lado(itens, kit, lados, pb_perto, cad=None):
    """Alça preformada de distribuição (qualquer composição): cada alça vai para um lado
    da rede, com a bitola do cabo daquele lado (ex.: 2 alças, PB70 de um lado e PB35 do
    outro = uma alça de cada). Um cabo só passando = todas pelo cabo que passa. Lado com
    PB fora da tabela (ex.: PB35) fica com a alça da planilha."""
    cad = cad or CADASTRO
    # lado sem balão de cabo PB apontando: vale o cabo PB mais perto do poste
    lados = [g or pb_perto for g in (lados or [])] or ([pb_perto] if pb_perto else [])
    if not any(lados):
        lados = [pb_perto] if pb_perto else []
    if not lados:
        return itens
    saida = []
    for m in itens:
        if not e_alca_dist(m["nome"], m.get("codigo")):
            saida.append(m)
            continue
        q_lado = m["qtd"] / len(lados)
        if len(lados) == 1 or len(set(lados)) == 1 or abs(q_lado - round(q_lado)) > 1e-9 or q_lado < 1:
            # um cabo só (o que passa), ou a quantidade não divide pelos lados:
            # vale o cabo mais grosso
            parcelas = [(max(g for g in lados if g), m["qtd"])]
        else:
            parcelas = [(g, q_lado) for g in lados]
        for g, q in parcelas:
            n = dict(m, qtd=q)
            rot = f"{kit['nome']} (PB{g})" if g else f"{kit['nome']} (sem cabo PB)"
            if g in ALCA_DIST_POR_PB:
                cod, nome = _alca_do_pb(g, cad)
                n.update(nome=nome, original=nome, codigo=cod, pendente=None)
            n["partes"] = {rot: q}
            saida.append(n)
    return saida
