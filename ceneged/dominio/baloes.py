"""Regras do texto do balão: separar materiais, multiplicador, cabos.

Parte do programa Levantamento de Materiais (Ceneged)."""

import re

from ceneged.comum.texto import _sem_acento
from ceneged.leitura_pdf.deteccao import (RE_METROS, _num_metros)
from ceneged.dados.cadastro import CADASTRO

# ---------------------------------------------------------------------------
#  Relatório de materiais
# ---------------------------------------------------------------------------
# separa materiais: vírgula (menos a vírgula decimal, ex.: 13,8kV), "|", ";",
# " + " e quebra de linha dentro do balão
# o "+" não separa: "ATRINT MT + BT" vem do jeito que está no balão (quem confere escolhe)
RE_SEPARA = re.compile(r"\n|\||;|(?<!\d),|,(?!\d)")


def _limpa(item):
    return re.sub(r"\s+", " ", item).strip(" ,;")


def _itens_do_texto(t):
    t = RE_METROS.sub(" ", t or "")
    # "CM\n100A": a quebra de linha antes da corrente/potência não separa materiais
    t = re.sub(r"\n(?=\s*\d+(?:[.,]\d+)?\s*(?:A|KVA|KV)\b)", " ", t, flags=re.I)
    t = re.sub(r"\s*\((?:V|P)\d+(?:-\d+)?\)", " ", t)          # (V5-6), (P7): vão/poste do desenho
    itens = [_limpa(i) for i in RE_SEPARA.split(t)]
    return [i for i in itens if i and re.search(r"[A-Za-z0-9]", i)]


def multiplicador(item):
    """'2x ESTAI DE SOLO' -> (2, 'ESTAI DE SOLO'); '3xS04-13,8kV' -> (3, '3xS04-13,8kV')
    (no código do cabo o '3x' fica no nome, para continuar ligado ao cadastro); sem 'Nx' -> (1, item)."""
    m = re.match(r"^\s*(\d{1,2})\s*[xX](\s*)(\S.*)$", item)
    if not m or int(m.group(1)) == 0:
        return 1, item
    n = int(m.group(1))
    return n, (m.group(3).strip() if m.group(2) else item)


def _e_cabo(nome):
    t = _sem_acento(nome).upper().strip()
    return bool(re.search(r"KV(?!A)", t) or re.search(r"\d\s*X\s*[A-Z0-9]", t) or
                re.fullmatch(r"(PB|RAMA?)\d{2,3}", t))


def materiais_do_balao(b):
    """
    Lista [(material, unidade, quantidade)] de um balão.
    - cada item separado por vírgula é um material;
    - se houver comprimento (até 4 números + M, dentro do balão, no balão de
      baixo ou do lado de fora), cada material recebe esses metros;
    - sem comprimento, cada material conta 1 unidade.
    """
    from ceneged.dados.composicoes import COMPOSICOES  # import tardio: camada de cima
    principal = b.get("principal", b["texto"])
    metros = None
    for fonte in [principal] + b.get("complementos", []) + [b.get("comprimento", "")]:
        m = RE_METROS.search(fonte or "")
        if m:
            metros = _num_metros(m.group(1))
            break
    # só a parte de cima do balão vira material; da parte de baixo (caixa empilhada)
    # vale só a metragem ("PB35" em cima e "3xS1/0-13,8kV (V5-6) 55M" embaixo = PB35, 55 m)
    itens = _itens_do_texto(principal)          # parte de cima só com metragem ("45M"): nada
    if b.get("quadrado"):
        # balão quadrado de poste (pilha "400/12" | "N1"): a caixa de baixo também é material
        for c_ in b.get("complementos", []):
            itens += _itens_do_texto(c_)
    if metros is not None and any(_e_cabo(i) for i in itens):
        # balão de cabo: palavra solta sem número ("RIACHO") é observação do vão, não material
        itens = [i for i in itens if re.search(r"\d", i) or
                 COMPOSICOES.achar(i) or
                 CADASTRO.resolver(i)[1] in ("igual", "manual")]
    saida = []
    for i in itens:
        n, nome = multiplicador(i)                  # "3x" na frente: 3 vezes (metros ou unidades)
        saida.append((nome, "M", metros * n) if metros is not None else (nome, "UN", n))
    return saida
