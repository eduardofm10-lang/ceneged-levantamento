"""Composições (materiais extras / kits).

Parte do programa Levantamento de Materiais (Ceneged)."""

import os
import re
import time

from ceneged.comum.texto import (_sem_acento, _und, chave_nome, info_poste, normaliza_codigo)
from ceneged.dados.armazenamento import (ARQ_COMPOSICOES, ler_dados, salvar_json, versao_dados)

APELIDOS_KIT_PADRAO = {            # nome do principal -> nomes usados nos projetos
    "ATERRAM. DE SECUNDÁRIO": ["ATRINT BT", "ATRINT"],
    "ESTAI": ["ESTAI SOLO"],
}
MOVIMENTOS = ("Aplicação", "Retirada / devolução")
_RE_COND_POSTE = re.compile(r"\(\s*POSTE\s+CIRC\w*\.?\s+(\d{1,2})\s*/\s*(\d{3,4})\s*\)", re.I)


def _kit_partes(titulo):
    """'RES-0190  ·  FLBIT' -> ('RES-0190', 'FLBIT')"""
    t = re.sub(r"\s+", " ", str(titulo or "")).strip()
    m = re.match(r"^([A-Za-z]{2,6}-?\d{1,6})\s*[·•|:–—-]\s*(.+)$", t)
    if m:
        return m.group(1).upper(), m.group(2).strip()
    return "", t


def _num(v):
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v).strip().replace(" ", "")
    if re.fullmatch(r"-?\d{1,3}(\.\d{3})+(,\d+)?", t):
        t = t.replace(".", "")
    t = t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def kit_limpo(k):
    itens = []
    for i in k.get("itens", []):
        nome = re.sub(r"\s+", " ", str(i.get("nome", ""))).strip()
        if not nome:
            continue
        q = _num(i.get("qtd"))
        itens.append({"nome": nome, "codigo": normaliza_codigo(i.get("codigo") or ""),
                      "und": str(i.get("und") or "CDA").strip().upper(),
                      "qtd": q if q is not None else 1.0,
                      "mov": str(i.get("mov") or MOVIMENTOS[0]).strip()})
    nome = re.sub(r"\s+", " ", str(k.get("nome", ""))).strip()
    auto = k.get("auto")
    if auto is None:
        auto = not itens or any(not _sem_acento(i["mov"]).upper().startswith("RETIR") for i in itens)
    kit = {"id": str(k.get("id") or "").strip(), "categoria": str(k.get("categoria") or "SEM CLASSIFICAÇÃO").strip(),
           "nome": nome, "apelidos": [str(a).strip() for a in k.get("apelidos", []) if str(a).strip()],
           "auto": bool(auto), "itens": itens}
    if k.get("normativo"):                 # ligada a uma estrutura do normativo ("DIS-NOR-018|N1")
        kit["normativo"] = str(k["normativo"])
    if k.get("itens_antes"):               # itens que a composição tinha antes do normativo
        kit["itens_antes"] = list(k["itens_antes"])
    return kit


def titulo_kit(k):
    return f"{k['id']}  ·  {k['nome']}" if k.get("id") else k["nome"]


def kit_por_metro(k):
    """Composição de cabo (todos os itens em metros): a quantidade é por metro lançado."""
    return bool(k["itens"]) and all(_und(i["und"]) == "M" for i in k["itens"])


def poste_do_kit(k):
    """Composição de poste -> {'altura', 'esforco', 'tipo', 'fibra', 'secc'} ou None."""
    if "POSTE" not in _sem_acento(k.get("categoria", "")).upper():
        return None
    txt = _sem_acento(k["nome"] + " " + " ".join(i["nome"] for i in k["itens"][:2])).upper()
    m = re.search(r"(\d{1,2})(?:[.,]\d)?\s*/\s*(\d{3,4})", txt)
    if not m:
        return None
    tipo = "dt" if re.search(r"\bDT\b|DUPLO", txt) else \
        ("circular" if re.search(r"CIRC|FIBRA|QUAD", txt) else None)
    return {"altura": int(m.group(1)), "esforco": int(m.group(2)), "tipo": tipo,
            "fibra": "FIBRA" in txt, "secc": "SECCION" in txt}


class Composicoes:
    """Materiais principais e os materiais que vêm junto (planilha 'materiais interligados').
    Guardado na pasta de dados (igual para todos)."""

    def __init__(self, caminho):
        self.caminho = caminho
        self.kits = []
        self.arquivo = ""
        self.carregado = ""
        self._ind = None
        self._lido_em = None
        self.carregar()

    # ---- arquivo
    def carregar(self):
        try:
            d = ler_dados(self.caminho)
            self.kits = [kit_limpo(k) for k in d.get("kits", []) if k.get("nome")]
            self.arquivo, self.carregado = d.get("arquivo", ""), d.get("carregado", "")
        except (OSError, ValueError, TypeError, AttributeError):
            self.kits = []
        self._lido_em = self._data()
        self._ind = None

    def _data(self):
        try:
            return versao_dados(self.caminho) if self.caminho else None
        except OSError:
            return None

    def recarregar_se_mudou(self):
        d = self._data()
        if d is not None and d != self._lido_em:
            self.carregar()
            return True
        return False

    def salvar(self):
        self._ind = None
        if self.caminho:
            salvar_json(self.caminho, {"kits": self.kits, "arquivo": self.arquivo, "carregado": self.carregado})
            self._lido_em = self._data()

    def mudou(self):
        self._ind = None

    def categorias(self):
        vistas = []
        for k in self.kits:
            if k["categoria"] not in vistas:
                vistas.append(k["categoria"])
        return vistas

    def definir(self, kits, arquivo=""):
        """Troca tudo pelo conteúdo da planilha, mantendo os nomes usados nos projetos
        e o 'usar automaticamente' que já tinham sido ajustados no programa."""
        antigos = {}
        for k in self.kits:
            antigos[("id", k["id"])] = k
            antigos[("nome", k["categoria"], chave_nome(k["nome"]))] = k
        novos = []
        for bruto in kits:
            da_planilha = "auto_planilha" in bruto
            k = kit_limpo(bruto)
            a = (antigos.get(("id", k["id"])) if k["id"] else None) or \
                antigos.get(("nome", k["categoria"], chave_nome(k["nome"])))
            if a:
                if not k["apelidos"]:
                    k["apelidos"] = list(a["apelidos"])
                for c_ in ("normativo", "itens_antes"):
                    if a.get(c_) and not k.get(c_):
                        k[c_] = a[c_]
                if not da_planilha:
                    k["auto"] = a["auto"]
            elif not k["apelidos"]:
                k["apelidos"] = list(APELIDOS_KIT_PADRAO.get(k["nome"].upper(), []))
                m = re.fullmatch(r"(\d{2,3}) MULT", k["nome"].upper())
                if m:
                    k["apelidos"] = [f"PB{m.group(1)}"]
            novos.append(k)
        self.kits = novos
        self.arquivo = os.path.basename(arquivo) if arquivo else self.arquivo
        self.carregado = time.strftime("%d/%m/%Y %H:%M")
        self.salvar()

    # ---- procurar a composição de um nome do balão
    def _indice(self):
        if self._ind is None:
            ind, postes, trafos = {}, [], []
            for k in self.kits:
                if not k["auto"]:
                    continue
                p = poste_do_kit(k)
                if p:
                    postes.append((p, k))
                if "TRAFO" in _sem_acento(k["nome"]).upper():
                    trafos.append(k)
                base = _RE_COND_POSTE.sub(" ", k["nome"])
                for n in [base] + k["apelidos"]:
                    c = chave_nome(n)
                    if c:
                        ind.setdefault(c, []).append(k)
            # "B1 - CCL": o balão escreve só "B1". Vale só se houver um principal com esse começo
            # (N1 tem CCR, CCT e fibra: aí precisa ligar o nome à mão)
            curtos = {}
            for k in self.kits:
                m = re.match(r"^\s*([A-Z0-9][A-Z0-9-]{0,7})\s+-\s+\S", _sem_acento(k["nome"]).upper())
                if k["auto"] and m:
                    curtos.setdefault(chave_nome(m.group(1)), []).append(k)
            for c, ks in curtos.items():
                if len(ks) == 1 and c not in ind:
                    ind[c] = ks
            self._ind = (ind, postes, trafos)
        return self._ind

    @staticmethod
    def _variante(lst, poste, padrao):
        """IT-R x IT-R (POSTE CIRC 12/1000): escolhe pela altura/esforço do poste circular."""
        if poste and (poste.get("tipo") or padrao) == "circular":
            for k in lst:
                m = _RE_COND_POSTE.search(k["nome"])
                if m and (int(m.group(1)), int(m.group(2))) == (poste["altura"], poste["esforco"]):
                    return k
        sem = [k for k in lst if not _RE_COND_POSTE.search(k["nome"])]
        return (sem or lst)[0]

    @staticmethod
    def _kit_poste(p, postes, padrao):
        tipo = p.get("tipo") or padrao
        melhor = None
        for kp, k in postes:
            if (kp["altura"], kp["esforco"]) != (p["altura"], p["esforco"]):
                continue
            if kp["tipo"] and kp["tipo"] != tipo:
                continue
            nota = 0
            if p.get("fibra"):
                nota += 2 if kp["fibra"] else 0
            elif p.get("tipo") == "circular":
                nota += 1 if not kp["fibra"] else 0          # C / CIRC: concreto
            nota -= 1 if kp["secc"] else 0
            if melhor is None or nota > melhor[0]:
                melhor = (nota, k)
        return melhor[1] if melhor else None

    @staticmethod
    def _kit_trafo(nome, trafos):
        t = _sem_acento(nome).upper().replace(" ", "")
        m = re.search(r"(\d)F\D{0,3}?(\d+(?:[.,]\d+)?)KVA", t)
        if not m:
            return None
        mono = m.group(1) == "1"
        kva = float(m.group(2).replace(",", "."))
        for k in trafos:
            kn = _sem_acento(k["nome"]).upper()
            if mono != bool(re.search(r"\bMON", kn)):
                continue
            n = re.search(r"(\d+(?:[.,]\d+)?)\s*KVA", kn)
            if n and abs(float(n.group(1).replace(",", ".")) - kva) < 0.01:
                return k
        return None

    def achar(self, nome, poste=None, padrao="circular"):
        """Nome do balão -> (composição, multiplicador) ou None."""
        ind, postes, trafos = self._indice()
        c = chave_nome(nome)
        if not c:
            return None
        if c in ind:
            return self._variante(ind[c], poste, padrao), 1
        c2 = chave_nome(re.sub(r"\b(DE|DA|DO|DOS|DAS|E)\b", " ", _sem_acento(nome).upper()))
        if c2 != c and c2 in ind:                                   # "ESTAI DE SOLO" = "ESTAI SOLO"
            return self._variante(ind[c2], poste, padrao), 1
        p = info_poste(nome)
        if p:
            k = self._kit_poste(p, postes, padrao)
            return (k, 1) if k else None
        k = self._kit_trafo(nome, trafos)
        if k:
            return k, 1
        m = re.match(r"^\s*(\d{1,2})\s*[xX]\s+(\S.*)$", nome)          # "2x U3"
        if m:
            r = self.achar(m.group(2), poste, padrao)
            if r:
                return r[0], r[1] * int(m.group(1))
        return None


COMPOSICOES = Composicoes(ARQ_COMPOSICOES)
