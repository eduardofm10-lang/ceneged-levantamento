"""Escolha nas tabelas dos normativos e montagem das estruturas.

Parte do programa Levantamento de Materiais (Ceneged)."""

import re

from ceneged.comum.texto import (_sem_acento, chave_nome, fmt_num, normaliza_codigo)
from ceneged.dados.cadastro import CADASTRO
from ceneged.dados.composicoes import (COMPOSICOES, MOVIMENTOS, _num)
from ceneged.dados.normativos import (ESTRUTURAS_NORMA, TABELAS_NORMA)
from ceneged.dominio.tabelas import (_cabo_da_rede, _cod_regiao, _contem, _dist_faixa,
    _tabela_do_item)
from ceneged.dominio.postes import (_bitola_txt, _faixas_da_desc, _linhas_postes,
    _peca_do_item, _postes_fixos, descricao_do_codigo, escolher_pelo_poste, linha_pelo_poste,
    tipo_do_poste)

def uso_da_linha(chave, tab, l, cad=None):
    """Texto "Usado quando": em que situação o sistema escolhe esta linha."""
    cad = cad or CADASTRO
    modo = tab.get("modo")
    norma = chave.split("|")[0]
    if modo == "poste":
        peca = _peca_do_item(l.get("descricao"))
        if not peca:
            return "uso geral (sem medida)"
        linhas = tab.get("linhas", [])
        txt = []
        fx = [f"{p['altura']}/{p['esforco']}" for p in _postes_fixos(l)]
        if fx:
            txt.append("fixo: " + ", ".join(fx))
        grupos = {}
        for pl in _linhas_postes():
            if not pl.get("ne") or not pl.get("l") or not pl.get("rn"):
                continue
            p = {"altura": int(pl["l"]), "esforco": int(pl["rn"]), "tipo": pl["tipo"]}
            if any(f_["altura"] == p["altura"] and f_["esforco"] == p["esforco"] for f_ in _postes_fixos(l)):
                continue                       # já aparece em "fixo"
            for nc in ((0, 1, 2) if peca == "PARAFUSO" else (0,)):
                l2, _ = linha_pelo_poste(peca, linhas, p, pl["tipo"], norma, {}, cad, nc)
                if l2 is l:
                    rot = f"{p['altura']}/{p['esforco']} {'DT' if pl['tipo'] == 'dt' else 'C'}"
                    grupos.setdefault(nc, []).append(rot)
        for nc, ps in sorted(grupos.items()):
            pre = "" if peca != "PARAFUSO" else ("sem cruzeta: " if nc == 0 else f"{nc} cruzeta(s): ")
            txt.append(pre + ", ".join(ps))
        return "; ".join(txt) if txt else "nenhum poste da tabela cai aqui"
    if modo in ("bitola", "fase", "neutro", "mensageiro"):
        quem = {"bitola": "cabo", "fase": "fase", "neutro": "neutro", "mensageiro": "mensageiro"}[modo]
        t = f"{quem} {_bitola_txt(l.get('b'))}" if l.get("b") else ""
        if l.get("comp") and modo == "bitola":
            t += f" (alça {fmt_num(l['comp'])} mm: a menor para 15 kV, a maior para 36,2 kV)"
        return t
    if modo == "cabo":
        return f"cabo {_bitola_txt(l.get('b'))}" + (f", {fmt_num(l['kv'])} kV" if l.get("kv") else "")
    if modo == "multiplexado":
        return f"fase {_bitola_txt(l.get('f'))} + neutro {_bitola_txt(l.get('n'))}" + \
            (f", {fmt_num(l['kv'])} kV" if l.get("kv") else "")
    if modo in ("principal", "derivacao", "estribo", "terminacao"):
        t = []
        if l.get("kv"):
            t.append(f"{fmt_num(l['kv'])} kV")
        if l.get("p") is not None:
            t.append(f"principal {_bitola_txt(l['p'])}")
        if l.get("d") is not None:
            t.append(f"derivação {_bitola_txt(l['d'])}")
        if l.get("cunha") is True:
            t.append("cunha (rede compacta)")
        return ", ".join(t)
    if modo == "pares":
        return "principal/derivação: " + "; ".join(f"{fmt_num(a)}/{fmt_num(b)} mm²" for a, b in l.get("pares") or [])
    if modo == "nua":
        return f"principal {_bitola_txt(l.get('p'))} / derivação {_bitola_txt(l.get('d'))}, {l.get('mat', '')}"
    if modo == "nua_bitola":
        return f"cabo nu {_bitola_txt(l.get('b'))}, {l.get('mat', '')}"
    if modo == "laco":
        return f"laço {l.get('tipo', '')}, cabo {_bitola_txt(l.get('b'))}"
    if modo == "unico":
        return "sempre esta"
    if modo == "manual":
        if l.get("padrao"):
            return "sempre (marcado em \"Usar sempre\")"
        f = _faixas_da_desc(l.get("descricao"))
        if f and all(_faixas_da_desc(x.get("descricao")) for x in tab.get("linhas", [])):
            nomes = ("cabo principal", "derivação")
            return ", ".join(f"{nomes[min(i, 1)]} {fmt_num(a)} a {fmt_num(b)} mm²" for i, (a, b) in enumerate(f))
        return "sem regra no normativo: vem pendente e quem confere escolhe (ou marque \"Usar sempre\")"
    return ""


EXPLICA_ESCOLHA = {
    "poste": "pelo poste do balão (altura/resistência) e a medida dele no ponto de fixação (abas Postes e "
             "Altura de aplicação)",
    "bitola": "pela bitola do cabo da rede", "cabo": "pelo cabo da rede (bitola e tensão)",
    "fase": "pela bitola do condutor fase", "neutro": "pela bitola do neutro",
    "mensageiro": "pela bitola do mensageiro/neutro", "multiplexado": "pelo cabo multiplexado (fase, neutro e tensão)",
    "principal": "pela faixa de bitola do cabo principal e do derivado",
    "derivacao": "pela faixa de bitola do cabo principal e do derivado",
    "estribo": "pela faixa de bitola do cabo", "terminacao": "pela tensão e faixa de bitola do cabo",
    "pares": "pelo par de bitolas principal/derivação (o derivado é considerado igual ao da rede)",
    "nua": "rede nua: cada linha é uma combinação cabo principal × cabo de derivação (bitola e material); "
           "entra o conector de compressão da linha (ou o de cunha, se não houver compressão)",
    "nua_bitola": "rede nua: bitola e material do cabo", "laco": "pelo tipo do laço e bitola do cabo",
    "unico": "sempre a mesma linha",
    "manual": "pela faixa de bitola escrita na descrição, quando houver; sem faixa, o normativo não dá regra: "
              "vem pendente com as opções para quem confere escolher (\"Trocar material\"), a não ser que uma "
              "linha esteja marcada em \"Usar sempre\"",
    "geometria": "dimensões dos postes (DIS-ETE-011)", "altura": "distância do topo onde a peça é fixada"}


def origem_no_normativo(kit, nome_item):
    """Item de uma composição -> (estrutura do normativo, item, chave da tabela) ou None."""
    if not kit:
        return None
    e = None
    lig = kit.get("normativo")
    if lig and "|" in lig:
        norma_, _, nome_ = lig.partition("|")
        e = next((x for x in ESTRUTURAS_NORMA.conteudo
                  if x["norma"] == norma_ and chave_nome(x["nome"]) == chave_nome(nome_)), None)
    if e is None:
        e = _indice_normas().get(chave_nome(kit.get("nome", "")))
    if not e:
        return None
    c = chave_nome(nome_item)
    it = next((i for i in e["itens"] if chave_nome(i.get("desc", "")) == c), None)
    if not it:
        return None
    return e, it, _tabela_do_item(it, e["norma"])


def escolher_na_tabela(it, norma, ctx, cad=None):
    """Item "A DEFINIR" -> (código, descrição, pendência). A pendência diz a tabela e a
    informação que falta quando a escolha não sai do desenho."""
    cad = cad or CADASTRO
    chave = _tabela_do_item(it, norma)
    tabs = TABELAS_NORMA.conteudo
    tab = tabs.get(chave) if chave else None
    falta = it.get("info") or "informação do projeto"
    rot = (it.get("ref") or chave or "normativo").replace("Ref.: ", "")
    if tab is None:
        return "", it["desc"], f"{rot}: {falta}"
    modo = tab.get("modo")
    linhas = tab.get("linhas", [])
    bt = norma == "DIS-NOR-014"
    cabo = _cabo_da_rede(norma, ctx)
    kv = ctx.get("kv") or (cabo or {}).get("kv") or 15.0
    escolha = cad.escolhas.get(f"{chave}|{(cabo or {}).get('fase', '')}")

    def ok(l, motivo):
        cod = _cod_regiao(l, cad)
        if not cod:
            return "", l.get("descricao") or it["desc"], f"{rot}: {motivo} - sem código da região nessa tabela"
        return cod, l.get("descricao") or it["desc"], None

    if escolha:
        l = next((l for l in linhas if escolha in (l.get("ne"), l.get("se"), l.get("br"))), None)
        if l:
            return ok(l, "escolhido à mão")
    if modo == "manual":
        pad = [l for l in linhas if l.get("padrao") and _cod_regiao(l, cad)]
        if len(pad) == 1:                       # "Usar sempre" marcado na tabela
            return ok(pad[0], "padrão da tabela")
        cab_ = _cabo_da_rede(norma, ctx)
        fx = [(_faixas_da_desc(l.get("descricao")), l) for l in linhas]
        if cab_ and fx and all(f for f, _ in fx):
            v = cab_["fase"]
            cand = [l for f, l in fx if all(_contem(x, v) for x in f) and _cod_regiao(l, cad)]
            if len(cand) > 1:                   # faixas que se sobrepõem: vale a mais justa
                larg = {id(l): sum(b - a for a, b in _faixas_da_desc(l.get("descricao"))) for l in cand}
                menor = min(larg.values())
                cand = [l for l in cand if larg[id(l)] == menor]
            if len(cand) == 1:
                return ok(cand[0], "")
            if cand:
                ops = "; ".join(f"{_cod_regiao(l, cad)} {l.get('descricao', '')}" for l in cand)
                return "", it["desc"], f"{rot}: mais de uma opção para {cab_['texto']} ({ops})"
    if modo == "poste" and ctx.get("poste"):
        r_ = escolher_pelo_poste(it, norma, linhas, ctx, cad, rot)
        if r_:
            return r_
    if modo == "poste" and not ctx.get("poste") and _linhas_postes():
        return "", it["desc"], f"{rot}: o balão não tem o poste (ex.: 400/12) para achar o tamanho pelo diâmetro"
    if modo in ("poste", "manual"):
        p = ctx.get("poste")
        extra = f" (poste {p['altura']}/{p['esforco']})" if p else ""
        return "", it["desc"], f"{rot}: {tab.get('info') or falta}{extra}"
    if modo == "unico":
        return ok(linhas[0], "")
    if not cabo:
        tipo_r = {"DIS-NOR-013": "coberto (rede compacta)", "DIS-NOR-014": "multiplexado de BT",
                  "DIS-NOR-016": "multiplexado de MT", "DIS-NOR-018": "nu"}.get(norma, "")
        return "", it["desc"], f"{rot}: {falta} (não achei cabo {tipo_r} nos balões da folha)"
    f_, n_ = cabo["fase"], cabo.get("neutro")
    cand = []
    if modo in ("bitola", "cabo", "fase"):
        cand = [l for l in linhas if l.get("b") and abs(l["b"] - f_) <= 0.06 * f_ and
                (modo != "cabo" or abs(l.get("kv", kv) - kv) < 1)]
    elif modo == "neutro":
        cand = [l for l in linhas if n_ and l.get("b") and abs(l["b"] - n_) <= 0.06 * n_]
    elif modo == "mensageiro":
        cand = [l for l in linhas if n_ and l.get("b") and abs(l["b"] - n_) <= 0.1 * n_]
    elif modo == "multiplexado":
        cand = [l for l in linhas if l.get("f") == f_ and (not n_ or l.get("n") == n_) and abs(l.get("kv", kv) - kv) < 1]
    elif modo in ("principal", "derivacao", "estribo", "terminacao"):
        dv = f_                                           # derivação: o mesmo cabo, se não houver outro
        pool = linhas
        if modo == "terminacao":
            pool = [l for l in linhas if abs(l.get("kv", kv) - kv) < 1]
        if modo == "estribo":
            cunha = [l for l in linhas if l.get("cunha")]
            pool = cunha if (norma == "DIS-NOR-013" and cabo["tipo"] == "coberto" and cunha) else \
                [l for l in linhas if not l.get("cunha")]
        dentro = [l for l in pool if l.get("p") and _contem(l["p"], f_) and
                  (modo != "derivacao" or not l.get("d") or _contem(l["d"], dv))]
        if dentro:
            cand = [min(dentro, key=lambda l: l["p"][1] - l["p"][0])]
        else:
            perto = sorted((l for l in pool if l.get("p")),
                           key=lambda l: _dist_faixa(l["p"], f_) + (0 if modo != "derivacao" or not l.get("d")
                                                                   else _dist_faixa(l["d"], dv)))
            if perto and _dist_faixa(perto[0]["p"], f_) <= 0.3:
                cand = [perto[0]]
    elif modo == "pares":
        cand = [l for l in linhas if any(abs(a - f_) < 1 and abs(b - f_) < 1 for a, b in l.get("pares", []))] or \
            [l for l in linhas if any(abs(a - f_) < 1 for a, b in l.get("pares", []))][:1]
    elif modo == "nua":
        pref = cad.config.get("conector_nua", "compressao")
        achou = [l for l in linhas if abs(l["p"] - f_) < 1 and abs(l["d"] - f_) < 1 and
                 (l["mat"] == cabo["mat"] or l["mat"].startswith(cabo["mat"]))]
        if achou:
            l = achou[0]
            cod = l["comp"] if pref == "compressao" and l.get("comp") else (l.get("cunha") or l.get("comp"))
            desc = descricao_do_codigo(cod) or (("CONECTOR COMP " if cod == l.get("comp") else
                                                 "CONECTOR CUNHA/IMPACT ") + f"{cabo['texto']} (Tabela 1 DIS-NOR-018)")
            return (cod, desc, None) if cod else ("", it["desc"], f"{rot}: sem código para esse cabo")
    elif modo == "nua_bitola":
        cand = [l for l in linhas if abs(l["b"] - f_) <= 0.06 * f_ and
                (l["mat"] == cabo["mat"] or (cabo["mat"] == "aluminio" and l["mat"] == "aluminio"))]
    elif modo == "laco":
        d = _sem_acento(it["desc"]).upper()
        tipo = "LAT DUP" if "DUPLO" in d else "ROLDANA" if "ROLDANA" in d else "TOPO" if "TOPO" in d else \
            "LAT" if "LATERAL" in d else None
        cand = [l for l in linhas if l.get("b") and abs(l["b"] - f_) <= 0.06 * f_ and _cod_regiao(l, cad) and
                (tipo is None or l.get("tipo") == tipo)]
    if len(cand) > 1 and modo == "bitola" and all(_num(l.get("comp")) for l in cand):
        # alça de cabo coberto (Tabela 19 do DIS-NOR-013): mesma bitola em dois comprimentos;
        # o item "15 kV" leva a mais curta e o "36,2 kV" a mais comprida (cabo mais grosso)
        d36 = "36,2" in it.get("desc", "") or (kv or 15) > 30
        cand = [sorted(cand, key=lambda l: _num(l["comp"]))[-1 if d36 else 0]]
    if len(cand) == 1:
        return ok(cand[0], "")
    if len(cand) > 1:
        ops = "; ".join(f"{_cod_regiao(l, cad) or '-'} {l.get('descricao', '')}" for l in cand)
        return "", it["desc"], f"{rot}: mais de uma opção para {cabo['texto']} ({ops})"
    return "", it["desc"], f"{rot}: nenhuma linha da tabela serve para {cabo['texto']} - {falta}"


def _indice_normas():
    ind = {}
    for e in ESTRUTURAS_NORMA.conteudo:
        for n in {e["nome"], e["nome"].replace("–", "-")}:
            c = chave_nome(n)
            if c and c not in ind:
                ind[c] = e
    return ind


def estrutura_do_normativo(nome, ctx, cad=None, forcar=False):
    """Nome do balão (ou "DIS-NOR-018|N1") -> (composição montada pelo normativo para este
    poste/rede, mult) ou None."""
    cad = cad or CADASTRO
    if not forcar and not cad.config.get("estruturas_normativo", True):
        return None
    if "|" in nome:
        norma_, _, nome_ = nome.partition("|")
        e = next((x for x in ESTRUTURAS_NORMA.conteudo
                  if x["norma"] == norma_ and chave_nome(x["nome"]) == chave_nome(nome_)), None)
        if not e:
            return None
        nome = nome_
        return _montar_do_normativo(e, 1, ctx, cad)
    m = re.match(r"^\s*(\d{1,2})\s*[xX]\s+(\S.*)$", nome)          # "2x U3"
    mult = 1
    if m:
        mult, nome = int(m.group(1)), m.group(2)
    e = _indice_normas().get(chave_nome(nome))
    if not e:
        return None
    return _montar_do_normativo(e, mult, ctx, cad)


_PALAVRAS_SEPARAM = ("ESTAI", "ROLDANA", "TOPO", "LATERAL", "DUPLO", "PILAR", "PINO", "SUSP", "ABAU")


def material_da_composicao(nome_estr, desc_item, comp=None):
    """Item "A DEFINIR" que o normativo não resolveu (ex.: cruzeta, alça da B3): procura o mesmo
    tipo de material na composição do usuário dessa estrutura ("B3 - CCL", "N1 - CCR"... ou com
    esse nome nos apelidos). Usa os itens de antes do normativo quando a composição foi atualizada.
    -> (código, descrição) se todas as composições concordam; ("", "opções") se divergem; None."""
    comp = comp or COMPOSICOES
    d = _sem_acento(desc_item).upper()
    pal = re.findall(r"[A-Z]{3,}", d)
    if not pal:
        return None
    tipo = pal[0]
    alvo = chave_nome(nome_estr)
    achados = {}
    for k in comp.kits:
        base = re.split(r"\s+-\s+", k["nome"].strip())[0]
        if alvo not in {chave_nome(base), chave_nome(k["nome"])} | {chave_nome(a) for a in k["apelidos"]}:
            continue
        src = k.get("itens_antes") if k.get("normativo") else k["itens"]
        for it in src or []:
            n = _sem_acento(it.get("nome", "")).upper()
            cod = normaliza_codigo(it.get("codigo") or "")
            if not cod or not re.match(rf"{tipo}\b", n):
                continue
            if any((w in n) != (w in d) for w in _PALAVRAS_SEPARAM):
                continue
            # bitola/diâmetro escritos no item do normativo têm que bater (parafuso M16 x M12)
            if any(not re.search(rf"(?<!\d){x}(?!\d)", n) for x in re.findall(r"(?<![\d,])(\d{2,3})(?=\s*X|\b)", d)):
                continue
            achados.setdefault(cod, (it["nome"], []))[1].append(k["nome"])
    if not achados:
        return None
    if len(achados) == 1:
        cod, (nm, _) = next(iter(achados.items()))
        return cod, nm
    return "", "; ".join(f"{c} {nm} ({', '.join(ks)})" for c, (nm, ks) in achados.items())


def _montar_do_normativo(e, mult, ctx, cad):
    norma = e["norma"]
    poste = ctx.get("poste")
    tipo = tipo_do_poste(poste, ctx, cad)
    kv = ctx.get("kv") or 15.0
    itens_e = e["itens"]
    tem_dt = any(isinstance(i.get("qdt"), float) for i in itens_e)
    tem_circ = any(isinstance(i.get("qcirc"), float) for i in itens_e)
    mt, bt = bool(ctx.get("cabo_mt")), bool(ctx.get("cabo_bt") or ctx.get("pb"))
    sec_rede = "secundaria" if (bt and not mt) else ("primaria" if (mt and not bt) else "ambas")
    itens, sel = [], []
    for i in itens_e:
        s = _sem_acento(i.get("secao", "")).lower()
        if "36,2" in s and kv < 30:
            continue
        if re.search(r"\b15 kv", s) and kv > 30:
            continue
        if s.startswith("rede"):
            ambas = "+" in s or " e " in s
            if (sec_rede == "ambas") != ambas:
                continue
            if not ambas and sec_rede not in s.replace("á", "a"):
                continue
        if tipo == "dt" or not tem_circ:
            q = i.get("qdt36") if (kv > 30 and isinstance(i.get("qdt36"), float)) else i.get("qdt")
        else:
            q = i.get("qcirc")
        if not isinstance(q, float):
            q = i.get("qunica") if isinstance(i.get("qunica"), float) else None
        if not tem_dt and not isinstance(q, float):
            q = i.get("qcirc")
        if not isinstance(q, float) or q <= 0:
            continue
        if re.match(r"POSTE\s+DE\s+CONCRETO|TRAFO\s+DE\s+DISTRIBUI", _sem_acento(i.get("desc", "")).upper()):
            continue                      # poste e transformador vêm do balão (400/12, 3F-75kVA), não da estrutura
        sel.append((i, q))
    # cruzetas atravessadas pelo parafuso (comprimento do parafuso)
    ctx = dict(ctx, _cruzetas=sum(q for i, q in sel if "CRUZETA" in _sem_acento(i.get("desc", "")).upper()),
               _tipo_poste=tipo)
    # mesmo item (mesmo número no desenho) mais de uma vez: pode ser material alternativo
    # (aço ou PRFV; versão de outra região sem código; parafuso "(POSTE 9 M)") ou duas peças
    # diferentes que vão juntas (parafuso 150 mm e 45 mm)
    grupos = {}
    for i, q in sel:
        grupos.setdefault(i.get("item") or id(i), []).append((i, q))
    MATS = ("ACO", "PRFV", "MADEIRA", "CONCRETO", "FIBRA", "POLIMER", "PORCELANA")
    fica = set()
    for g in grupos.values():
        if len(g) > 1:
            alt_poste = [(i, q) for i, q in g if re.search(r"\(POSTE[^)]*\d+\s*M\)", i["desc"].upper())]
            if alt_poste and poste:
                g2 = [(i, q) for i, q in alt_poste
                      if str(poste["altura"]) in re.findall(r"\d+", re.search(r"\(POSTE([^)]*)\)", i["desc"].upper()).group(1))]
                g = g2[:1] or alt_poste[:1]
            elif alt_poste:
                g = alt_poste[:1]
            com_cod = [(i, q) for i, q in g if _cod_regiao(i, cad) or i.get("adef")]
            if com_cod and len(com_cod) < len(g):
                g = com_cod
            if len(g) > 1:
                mats = [frozenset(m for m in MATS if m in _sem_acento(i["desc"]).upper().split() or
                                  m in _sem_acento(i["desc"]).upper()) for i, _ in g]
                if len(set(mats)) > 1:
                    g = g[:1]                 # material alternativo: vale o primeiro
        fica.update(id(i) for i, _ in g)
    for i, q in sel:
        if id(i) not in fica:
            continue
        cod = _cod_regiao(i, cad)
        desc, pend = i["desc"], None
        if i.get("adef") or not cod:
            if i.get("adef") or i.get("ref"):
                cod, desc, pend = escolher_na_tabela(i, norma, ctx, cad)
            else:
                pend = f"{norma} - {e['nome']}: sem código da região para este item"
            if pend and not cod:
                # o normativo não decidiu: vale o material da sua composição dessa estrutura
                r_ = material_da_composicao(e["nome"], i.get("desc", ""))
                if r_ and r_[0]:
                    cod, desc, pend = r_[0], r_[1], None
                elif r_:
                    pend = f"{pend} | Nas suas composições: {r_[1]}"
        und = (i.get("und") or "un").strip().upper()
        itens.append({"nome": desc, "codigo": cod, "und": "CDA" if und == "UN" else und, "qtd": q,
                      "mov": MOVIMENTOS[0], "pendente": pend})
    kit = {"id": f"{norma}", "categoria": norma, "nome": e["nome"], "apelidos": [], "auto": True,
           "itens": itens, "normativo": True}
    return kit, mult
