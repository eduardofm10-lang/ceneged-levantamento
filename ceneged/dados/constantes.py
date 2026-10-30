"""Constantes (metro -> KG).

Parte do programa Levantamento de Materiais (Ceneged)."""

import os
import re

from ceneged.comum.texto import (chave_nome, normaliza_codigo)
from ceneged.dados.caminhos import pasta_dados
from ceneged.dados.banco import montar_tabelas_de_consulta
from ceneged.dados.composicoes import _num
from ceneged.dados.equipes import ArquivoDados

# ---------------------------------------------------------------------------
#  Constantes: materiais lançados em metros que vão para o relatório em KG
#  (metros × constante = kg)
# ---------------------------------------------------------------------------
ARQ_CONSTANTES = os.path.join(pasta_dados(), "ceneged_constantes.json")
CONSTANTES_PADRAO = [  # planilha "CONSTANTES X CELPE (SEM 10%)"
    ("", "CABO NU CAA 4 SWAN", 0.085), ("", "CABO NU CAA 1/0 RAVEN", 0.216),
    ("", "CABO NU CAA 4/0 PENGUIN", 0.4335), ("", "CABO NU CA 4 ROSE", 0.0585),
    ("", "CABO NU CA 1/0 RAVEN", 0.1461), ("", "CABO NU COBRE 16,00MM2", 0.14106),
    ("", "CABO NU COBRE 25,00MM2", 0.2231), ("", "CABO NU COBRE 35,00MM2", 0.3052)]


def _num_br(v):
    """0.14106 -> '0,14106' (sem arredondar a constante)."""
    return f"{float(v):.6g}".replace(".", ",")


class Constantes(ArquivoDados):
    def __init__(self, caminho):
        super().__init__(caminho, {"itens": None})
        if self.dados.get("itens") is None:            # primeira vez: valores da planilha da Celpe
            self.dados["itens"] = [{"codigo": c, "descricao": d, "constante": k} for c, d, k in CONSTANTES_PADRAO]

    @property
    def itens(self):
        return self.dados["itens"]

    def para(self, codigo, nome):
        """Constante (kg/m) do material, pelo código ou pelo nome; None se não tiver."""
        cod = normaliza_codigo(codigo or "")
        k = chave_nome(nome)
        for i in self.itens:
            if cod and normaliza_codigo(i.get("codigo", "")) == cod:
                return float(i["constante"])
        for i in self.itens:
            if k and chave_nome(i.get("descricao", "")) == k:
                return float(i["constante"])
        return None

    def salvar_item(self, indice, codigo, descricao, constante):
        self.recarregar_se_mudou()
        descricao = re.sub(r"\s+", " ", descricao).strip()
        if not descricao:
            raise ValueError("Informe a descrição do material.")
        k = _num(constante)
        if k is None or k <= 0:
            raise ValueError("Constante inválida (ex.: 0,085).")
        novo = {"codigo": normaliza_codigo(codigo or ""), "descricao": descricao, "constante": k}
        if indice is not None and self.itens[indice].get("planilha"):
            novo["planilha"] = self.itens[indice]["planilha"]
        for j, i in enumerate(self.itens):
            if j != indice and (chave_nome(i["descricao"]) == chave_nome(descricao) or
                                (novo["codigo"] and normaliza_codigo(i.get("codigo", "")) == novo["codigo"])):
                raise ValueError(f"Esse material já tem constante: {i['descricao']}.")
        if indice is None:
            self.itens.append(novo)
        else:
            self.itens[indice] = novo
        self.salvar()

    def excluir_item(self, indice):
        self.recarregar_se_mudou()
        if 0 <= indice < len(self.itens):
            self.itens.pop(indice)
            self.salvar()

    def definir(self, itens):
        self.dados["itens"] = itens
        self.salvar()


CONSTANTES = Constantes(ARQ_CONSTANTES)
montar_tabelas_de_consulta()
