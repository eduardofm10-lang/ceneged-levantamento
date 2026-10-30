"""Montagem do relatório de materiais (conectores, agrupamento, ajustes).

Parte do programa Levantamento de Materiais (Ceneged)."""

import re

from ceneged.comum.texto import (_und, chave_nome, info_poste, normaliza_codigo)
from ceneged.dados.cadastro import CADASTRO
from ceneged.dominio.baloes import (RE_SEPARA, _limpa, materiais_do_balao, multiplicador)
from ceneged.dados.composicoes import (COMPOSICOES, MOVIMENTOS, _num, kit_por_metro)
from ceneged.dominio.materiais import (alcas_por_lado, codigo_do_item, converter_para_kg,
    itens_do_kit)
from ceneged.dominio.normativo import estrutura_do_normativo
from ceneged.dominio.cerca import itens_do_kit_cerca

def conector_perfurante(comp=None):
    """(nome, código, movimento) do conector perfurante, como está nos materiais extras
    (o do IT-R: CONETOR PERF 16,0-95,0/4,0-35,0)."""
    comp = comp or COMPOSICOES
    achado = None
    for k in comp.kits:
        for i in k["itens"]:
            n = chave_nome(i["nome"])
            if normaliza_codigo(i.get("codigo") or "") == "2412001" or n.startswith("CONETORPERF16"):
                achado = (i["nome"], i.get("codigo") or "2412001", i.get("mov", ""))
                if normaliza_codigo(i.get("codigo") or "") == "2412001":
                    return achado
    return achado or ("CONETOR PERF 16,0- 95,0/ 4,0- 35,0", "2412001", "")


# conectores perfurantes das tabelas 5 e 6 do DIS-NOR-014
_CODS_PERFURANTE = ("2412001", "2412002", "2412000", "2412026", "2412027")


def e_conector_perfurante(nome, codigo="", comp=None):
    _, cod, _ = conector_perfurante(comp)
    n = chave_nome(nome)
    return (normaliza_codigo(codigo or "") in (normaliza_codigo(cod),) + _CODS_PERFURANTE
            or n.startswith(("CONETORPERF", "CONECTORPERF", "CONETORDERIVPERF", "CONECTORDERIVPERF")))


def conectores_da_composicao(nome, kit_norma, comp=None, poste=None, padrao="circular"):
    """FLBIT/FLABIT montado pelo normativo: o normativo não traz conector perfurante, então
    valem os conectores perfurantes que a composição do usuário tinha (os de antes do
    normativo, ou os da composição sem ligação). Devolve a lista de itens (pode ser vazia)."""
    comp = comp or COMPOSICOES
    r = comp.achar(nome, poste, padrao)
    ks = [r[0]] if r else []
    ks += [k for k in comp.kits if chave_nome(k["nome"]) == chave_nome(kit_norma["nome"]) and k not in ks]
    for k in ks:
        src = k.get("itens_antes") if k.get("normativo") else k["itens"]
        con = [i for i in (src or []) if e_conector_perfurante(i["nome"], i.get("codigo"), comp)]
        if con:
            return con
    # composição sem conector: 4 conectores perfurantes (os dos materiais extras) por FLBIT/FLABIT
    q = _num((CADASTRO.config or {}).get("conectores_flbit", 4)) or 0
    if q <= 0:
        return []
    nome_c, cod_c, mov_c = conector_perfurante(comp)
    return [{"nome": nome_c, "codigo": cod_c, "und": "CDA", "qtd": float(q), "mov": mov_c or MOVIMENTOS[0]}]


def materiais_resolvidos(grupo, cad=None, ctx=None, comp=None):
    """
    Materiais de um balão (ou de uma pilha de caixas):
      - o que for material principal na planilha de materiais extras (FLBIT, IT-R,
        9600FV, CE3…) vira os materiais da composição dele (qtd por unidade lançada);
      - os outros itens viram o material do cadastro (com código);
      - o que já veio no balão não é repetido (só entra a diferença).
    grupo: [(ref, balão)] -> [{"nome", "original", "un", "qtd", "ref", "origem", "de",
                               "codigo", "pendente", ...}]
    origem: projeto | cabo (metros do caminho) | estrutura (da composição) | est (o próprio principal)
    """
    cad = cad or CADASTRO
    comp = comp or COMPOSICOES
    itens, pos_rede, pb_de, lados_de, cerca_de = [], {}, {}, {}, {}
    for ref, b in grupo:
        if b.get("cerca"):
            lista = [(b["texto"], "UN", 1)]
        elif b.get("tipo") == "material":
            lista = [(_limpa(i), "UN", 1) for i in RE_SEPARA.split(b["texto"]) if re.search(r"[A-Za-z0-9]", i)]
        else:
            lista = materiais_do_balao(b)
        for nome, un, q in lista:
            itens.append((ref, nome, un, q, b.get("tipo")))
        pos_rede[ref] = b.get("rede_pos")
        pb_de[ref] = b.get("cabo_pb")
        cerca_de[ref] = b.get("cerca")
        lados_de[ref] = b.get("rede_cabos")
    poste = None
    for ref, nome, un, q, tb in itens:
        poste = info_poste(nome)
        if poste:
            break
    if not poste:                        # estrutura em poste existente: etiqueta do poste no desenho
        for ref, b in grupo:
            if b.get("poste_existente"):
                poste = info_poste(b["poste_existente"])
                if poste:
                    break
    padrao = cad.config.get("poste_padrao", "circular")
    tem_codigos = bool(cad.codigos)
    saida, requeridos = [], []
    # estrutura do normativo (substitui a composição de mesmo nome), montada para este poste
    ctx_n = dict(ctx or {}, poste=poste, padrao=padrao,
                 pb=next((g for r_ in pb_de for g in ([pb_de[r_]] + list(lados_de.get(r_) or [])) if g), None))

    def achar(nome_):
        # composição ligada ao normativo (pelo nome ou por um apelido): monta pelo normativo;
        # senão, estrutura do normativo com o mesmo nome; senão, a composição como está
        k_ = comp.achar(nome_, poste, padrao)
        r_ = None
        try:
            if k_ and k_[0].get("normativo"):
                r_ = estrutura_do_normativo(k_[0]["normativo"], ctx_n, cad)
                if r_:
                    r_ = (dict(r_[0], nome=k_[0]["nome"]), r_[1] * k_[1])
            if not r_:
                r_ = estrutura_do_normativo(nome_, ctx_n, cad)
        except Exception:
            r_ = None
        return r_ or k_
    # "FLABIT+FLBIM" = duas estruturas (quando não há uma composição com o nome junto);
    # "IT-R (2xIN-40W)": a estrutura é o que vem antes dos parênteses
    abertos = []
    for ref, nome, un, q, tb in itens:
        if tb != "cabo" and not achar(nome):
            base = re.sub(r"\s*\(.*$", "", nome).strip()
            partes_ = [x.strip() for x in base.split("+") if x.strip()]
            if base and (len(partes_) > 1 or base != nome) and all(achar(x) for x in partes_):
                abertos += [(ref, x, un, q, tb) for x in partes_]
                continue
        abertos.append((ref, nome, un, q, tb))
    itens = abertos
    achados = [achar(nome) if tb != "cabo" else None for ref, nome, un, q, tb in itens]
    # balões (ou pilhas) com IT-R / ITF-R: decidem o conector do FLBIT/FLABIT no fim da rede
    com_itr = {it[0] for it, a in zip(itens, achados)
               if a and re.search(r"\bITF?-R\b", a[0]["nome"].upper())}
    # o que os principais do balão já trazem (para não repetir: "3F-75kVA, PARA-RAIO")
    trazidos = [(chave_nome(i["nome"]), codigo_do_item(i["nome"], i["codigo"], cad), k)
                for a in achados if a for k in [a[0]] for i in k["itens"]]
    for (ref, nome, un, q, tb), achado in zip(itens, achados):
        if not achado and tb != "cabo" and trazidos:
            c = chave_nome(nome)
            # pelo código só quando o nome foi ligado à mão ou é igual ao do cadastro
            # (nome só "parecido" pode ser outra estrutura: o B1 não vem no FLABIT)
            real, como, _ = cad.resolver(nome)
            cod_cad = cad.codigo_de(real) if como in ("manual", "igual") else ""
            cobre = next((k for n_, cod_, k in trazidos
                          if (len(c) >= 4 and c in n_) or (cod_cad and cod_ == cod_cad)), None)
            if cobre:
                saida.append({"nome": nome, "original": nome, "un": un, "qtd": 0, "ref": ref, "origem": "coberto",
                              "de": cobre["nome"], "codigo": "", "pendente": None})
                continue
        if achado:
            kit, mult = achado
            n = (q if (un != "M" or kit_por_metro(kit)) else 1) * mult
            saida.append({"nome": kit["nome"], "original": nome, "un": "", "qtd": n, "ref": ref, "origem": "est",
                          "de": kit["id"] or kit["categoria"], "codigo": "", "pendente": None})
            if cerca_de.get(ref):
                requeridos += itens_do_kit_cerca(kit, cerca_de[ref], ref)
                continue
            do_kit = alcas_por_lado(itens_do_kit(kit, n, ref, nome), kit, lados_de.get(ref),
                                    pb_de.get(ref), cad)
            if re.fullmatch(r"FLA?BIT", kit["nome"].strip().upper()) and kit.get("normativo") and \
                    not any(e_conector_perfurante(m["nome"], m["codigo"], comp) for m in do_kit):
                con_u = conectores_da_composicao(nome, kit, comp, poste, padrao)
                if con_u:
                    do_kit += itens_do_kit(dict(kit, itens=[dict(i) for i in con_u]), n, ref, nome)
            if re.fullmatch(r"FLA?BIT", kit["nome"].strip().upper()) and ref in com_itr:
                # conector perfurante do FLBIT/FLABIT junto com IT-R/ITF-R no mesmo poste:
                # no meio da rede soma os dois; no fim da rede ficam só os do IT-R/ITF-R.
                # (FLBIT/FLABIT sozinho: os conectores dele entram sempre)
                con = [m for m in do_kit if e_conector_perfurante(m["nome"], m["codigo"], comp)]
                do_kit = [m for m in do_kit if m not in con]
                if pos_rede.get(ref) != "fim":
                    rot = f"{kit['nome']} (meio de rede)"
                    for m in con:
                        m.update(de=rot, partes={rot: m["qtd"]})
                    do_kit += con
            requeridos += do_kit
            continue
        real = cad.nome_real(nome)
        cod = cad.codigo_de(real)
        pend = None if (cod or not tem_codigos) else "sem código no cadastro"
        saida.append({"nome": real, "original": nome, "un": un, "qtd": q, "ref": ref,
                      "origem": "cabo" if tb == "cabo" else "projeto", "de": None, "codigo": cod,
                      "pendente": pend})
    # composições: soma por código; o que já veio no balão é descontado
    ja = {}
    for o in saida:
        if o["codigo"] and o["origem"] in ("projeto", "cabo"):
            ja[o["codigo"]] = ja.get(o["codigo"], 0) + o["qtd"]
    junto = {}
    for m in requeridos:
        k = ("c", m["codigo"], m["un"]) if m["codigo"] else ("n", chave_nome(m["nome"]), m["un"])
        if k in junto:
            junto[k]["qtd"] += m["qtd"]
            for d_, q_ in m.get("partes", {}).items():
                junto[k]["partes"][d_] = junto[k]["partes"].get(d_, 0) + q_
            if m["de"] not in junto[k]["de"].split(", "):
                junto[k]["de"] += ", " + m["de"]
        else:
            junto[k] = dict(m, partes=dict(m.get("partes", {})))
    for k, m in junto.items():
        if m["codigo"] and ja.get(m["codigo"]):
            falta = m["qtd"] - ja[m["codigo"]]
            if falta <= 0:
                continue
            m["qtd"] = falta
            m["partes"]["(menos o que já veio no balão)"] = -ja[m["codigo"]]
        saida.append(m)
    return saida


def agrupar_baloes(baloes_com_ref):
    """Caixas da mesma pilha (projeto empilhado) contam como um balão só."""
    grupos = {}
    for ref, b in baloes_com_ref:
        k = ("pilha", ref[0], b["pilha"]) if b.get("pilha") is not None else ref
        grupos.setdefault(k, []).append((ref, b))
    return list(grupos.values())


def montar_relatorio(baloes_com_ref, extras=(), cadastro=None, contextos=None):
    """
    baloes_com_ref: [(ref, balão)]; extras: [(material, unidade, qtd, ref)] (metros dos cabos)
    contextos: {página: contexto_pagina(...)}
    ->  [{"material", "codigo", "unidade", "qtd", "refs", "origens", "cadastrado", "pendente", ...}]
    Materiais com o mesmo código (ou o mesmo nome) são somados.
    """
    cad = cadastro or CADASTRO
    contextos = contextos or {}
    tem_codigos = bool(cad.codigos)
    tabela = {}

    def soma(o, ref, origem):
        cod = o.get("codigo") or ""
        un = o["un"]
        if cod:
            chave = ("c", cod, un)
        else:
            chave = ("n", chave_nome(o["nome"]) or o["nome"].upper(), un)
        lin = tabela.setdefault(chave, {"material": o["nome"], "codigo": cod, "unidade": un, "qtd": 0,
                                        "refs": [], "origens": set(), "pendente": o.get("pendente"),
                                        "mov": o.get("mov") or MOVIMENTOS[0], "de": set(), "partes": {},
                                        "originais": set()})
        lin["qtd"] += o["qtd"]
        if origem in ("projeto", "cabo") and (o.get("original") or o.get("nome")):
            lin["originais"].add(o.get("original") or o["nome"])
        partes = o.get("partes") or {("metros do cabo" if origem == "cabo" else
                                      f"balão ({o.get('original') or o['nome']})"): o["qtd"]}
        for d_, q_ in partes.items():
            lin["partes"][d_] = lin["partes"].get(d_, 0) + q_
        lin["refs"].append(ref)
        lin["origens"].add(origem)
        if o.get("de") and origem == "estrutura":
            lin["de"].update(str(o["de"]).split(", "))
    for nome, un, q, ref in extras:
        n_, nome = multiplicador(nome)
        q = q * n_
        if nome.startswith("("):
            soma({"nome": nome, "un": un, "qtd": q, "codigo": "", "pendente": None}, ref, "cabo")
            continue
        achado = COMPOSICOES.achar(nome)
        if achado and un == "M":                      # cabo com composição (ex.: PB35 -> 35 MULT)
            kit, mult = achado
            for o in itens_do_kit(kit, q * mult if kit_por_metro(kit) else mult, ref, nome):
                soma(o, ref, "estrutura")
            continue
        real = cad.nome_real(nome)
        cod = cad.codigo_de(real)
        soma({"nome": real, "original": nome, "un": un, "qtd": q, "codigo": cod,
              "pendente": None if (cod or not tem_codigos) else "sem código no cadastro"}, ref, "cabo")
    for grupo in agrupar_baloes(baloes_com_ref):
        ctx = contextos.get(grupo[0][0][0], {})
        for o in materiais_resolvidos(grupo, cad, ctx):
            if o["origem"] in ("cabo", "est", "coberto"):   # cabo: pelos metros; principal: vira materiais
                continue
            soma(o, o["ref"], o["origem"])
    # material que tem metros: fica só a soma dos metros (sem a contagem)
    for k in list(tabela):
        if k[2] == "UN" and (k[0], k[1], "M") in tabela:
            lin = tabela.pop(k)
            tabela[(k[0], k[1], "M")]["refs"] += lin["refs"]
            tabela[(k[0], k[1], "M")]["origens"] |= lin["origens"]
            for d_, q_ in lin["partes"].items():
                tabela[(k[0], k[1], "M")]["partes"][d_ + " (contado em unidade)"] = q_
    converter_para_kg(tabela)
    for lin in tabela.values():
        lin["qtd"] = round(lin["qtd"], 3)
        lin["cadastrado"] = bool(lin["codigo"]) or (not cad.materiais) or cad.cadastrado(lin["material"]) or \
            lin["material"].startswith("(")
        lin["de"] = ", ".join(sorted(lin["de"]))
    return sorted(tabela.values(), key=lambda l: (bool(l["pendente"]), l["material"].upper(), l["unidade"]))


def chave_linha(lin):
    """Identifica uma linha do relatório (para os ajustes manuais)."""
    return (lin.get("codigo") or "n:" + (chave_nome(lin["material"]) or lin["material"]), lin["unidade"])


def aplicar_ajustes(linhas, aj):
    """Ajustes da Página inicial: materiais tirados, quantidades trocadas e materiais acrescentados."""
    if not aj or not (aj["remover"] or aj["qtd"] or aj["add"] or aj.get("trocar")):
        return linhas
    saida, por = [], {}
    for lin in linhas:
        k = chave_linha(lin)
        if k in aj["remover"]:
            continue
        t = aj.get("trocar", {}).get(k)
        if t:
            # material trocado à mão: mesma quantidade, outro material
            antes = lin["material"]
            lin = dict(lin, material=t["nome"], codigo=t.get("codigo", ""), pendente=None, cadastrado=True,
                       origens=set(lin.get("origens", set())) | {"manual"},
                       partes={f"trocado à mão (era {antes})": lin["qtd"]})
            if t.get("und"):
                lin["unidade"] = _und(t["und"])
            k = chave_linha(lin)
            if k in aj["remover"]:
                continue
            if k in por:                     # já tinha esse material: soma
                por[k]["qtd"] = round(por[k]["qtd"] + lin["qtd"], 3)
                por[k]["origens"] = set(por[k].get("origens", set())) | {"manual"}
                for d_, q_ in lin["partes"].items():
                    por[k].setdefault("partes", {})[d_] = por[k]["partes"].get(d_, 0) + q_
                continue
        por[k] = lin
        saida.append(lin)
    for a in aj["add"]:
        un = _und(a["und"])
        lin = {"material": a["nome"], "codigo": a["codigo"], "unidade": un, "qtd": a["qtd"]}
        k = chave_linha(lin)
        if k in por:
            por[k]["qtd"] = round(por[k]["qtd"] + a["qtd"], 3)
            por[k]["origens"].add("manual")
            p_ = por[k].setdefault("partes", {})
            p_["adicionado à mão"] = p_.get("adicionado à mão", 0) + a["qtd"]
            continue
        lin.update({"refs": [], "origens": {"manual"}, "partes": {"adicionado à mão": a["qtd"]}, "pendente": None,
                    "mov": a.get("mov") or MOVIMENTOS[0],
                    "de": "", "cadastrado": True})
        por[k] = lin
        saida.append(lin)
    for k, q in aj["qtd"].items():
        if k in por:
            por[k]["qtd"] = q
            por[k]["origens"].add("manual")
            por[k]["partes"] = dict(por[k].get("partes", {}), **{"quantidade trocada à mão para": q})
    return sorted(saida, key=lambda l: (bool(l["pendente"]), l["material"].upper(), l["unidade"]))
