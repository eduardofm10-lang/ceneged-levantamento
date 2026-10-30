"""Carregar a planilha dos normativos e atualizar as composições existentes.

Parte do programa Levantamento de Materiais (Ceneged)."""

from ceneged.comum.texto import (chave_nome, normaliza_codigo)
from ceneged.dados.cadastro import CADASTRO
from ceneged.dados.composicoes import (COMPOSICOES, MOVIMENTOS, kit_limpo)
from ceneged.dados.normativos import (ESTRUTURAS_NORMA, TABELAS_NORMA, ler_planilha_normativos)
from ceneged.dominio.normativo import _montar_do_normativo

def atualizar_composicoes_do_normativo(comp=None, cad=None):
    """Cada estrutura do normativo atualiza a composição que já existe com o mesmo nome (ou
    com esse nome nos apelidos): troca só os itens e liga a composição ao normativo. Nome,
    apelidos, categoria e 'usar automaticamente' ficam como estavam; os itens de antes ficam
    guardados em 'itens_antes'. Estrutura que não existe vira composição nova.
    Devolve (atualizadas, novas)."""
    comp = comp or COMPOSICOES
    cad = cad or CADASTRO
    comp.recarregar_se_mudou()
    por_nome = {}
    for k in comp.kits:
        for n in [k["nome"]] + k["apelidos"]:
            c = chave_nome(n)
            if c:
                por_nome.setdefault(c, []).append(k)
    atual, novas, vistos = set(), 0, set()
    for e in ESTRUTURAS_NORMA.conteudo:
        chaves = {chave_nome(e["nome"]), chave_nome(e["nome"].replace("–", "-"))} - {""}
        if not chaves or chaves & vistos:
            continue                      # mesmo nome em outro normativo: vale o primeiro
        vistos |= chaves
        lig = f"{e['norma']}|{e['nome']}"
        r = _montar_do_normativo(e, 1, {}, cad)
        itens = [{"nome": i["nome"], "codigo": normaliza_codigo(i.get("codigo") or ""), "und": i["und"],
                  "qtd": i["qtd"], "mov": i.get("mov") or MOVIMENTOS[0]} for i in r[0]["itens"]] if r else []
        ks = []
        for c in chaves:
            ks += [k for k in por_nome.get(c, []) if k not in ks]
        if ks:
            for k in ks:
                if not k.get("normativo") and k["itens"]:
                    k["itens_antes"] = k["itens"]
                k["itens"], k["normativo"] = itens, lig
                atual.add(id(k))
        else:
            comp.kits.append(kit_limpo({"categoria": e["norma"], "nome": e["nome"], "auto": True,
                                        "itens": itens, "normativo": lig}))
            novas += 1
    comp.salvar()
    return len(atual), novas


def carregar_planilha_normativos(caminho):
    """Grava no banco o que veio da planilha. Cada aba encontrada substitui o que havia.
    As estruturas atualizam as composições (ver atualizar_composicoes_do_normativo)."""
    estruturas, tabelas, avisos, ete = ler_planilha_normativos(caminho)
    if estruturas is not None:
        ESTRUTURAS_NORMA.trocar(estruturas)
    if tabelas is not None or ete:
        # aba Tabelas troca as tabelas dos normativos; abas Postes / Altura de aplicação trocam só as delas
        atual = dict(TABELAS_NORMA.conteudo)
        novo = {k: v for k, v in atual.items() if k.startswith("DIS-ETE-011|")} if tabelas is not None \
            else atual
        novo.update(tabelas or {})
        novo.update(ete)
        TABELAS_NORMA.trocar(novo)
    if ete:
        avisos.append("Postes (DIS-ETE-011): " + "; ".join(
            f"{v['titulo'].split(' (')[0]}: {len(v['linhas'])} linhas" for v in ete.values()))
    comps = atualizar_composicoes_do_normativo() if estruturas is not None else None
    return estruturas, tabelas, avisos, comps
