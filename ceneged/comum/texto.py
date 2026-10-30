"""Funções de texto usadas em todas as camadas (acentos, comparação de nomes).

Parte do programa Levantamento de Materiais (Ceneged)."""

import collections
import difflib
import re
import unicodedata

# ---------------------------------------------------------------------------
#  Cadastro de materiais (nome usado na empresa) e materiais extras
#  (materiais que obrigatoriamente vêm junto com outro).
# ---------------------------------------------------------------------------

def _sem_acento(s):
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()


def chave_nome(s):
    """Forma de comparar nomes: maiúsculas, sem acento, só letras e números."""
    return re.sub(r"[^A-Z0-9]", "", _sem_acento(s).upper())


def _numeros(s):
    return [str(int(n)) for n in re.findall(r"\d+", _sem_acento(s))]


def _letras(s):
    return re.findall(r"[A-Z]+", _sem_acento(s).upper())


def semelhanca(proj, cad):
    """
    Nota de 0 a 1 de o nome do projeto ser o nome do cadastro.
    - os números do projeto têm que existir no nome do cadastro (PB35 nunca
      vira PB70; 3xS04 nunca vira 1xS04);
    - as letras do projeto têm que aparecer no começo das palavras do cadastro
      ou o texto ser parecido letra a letra.
    """
    a, b = chave_nome(proj), chave_nome(cad)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    pp = info_poste(proj)
    if pp and "POSTE" in _sem_acento(cad).upper():
        cu = _sem_acento(cad).upper()
        nums = {int(x) for x in re.findall(r"\d+", cu)}
        if pp["altura"] in nums and pp["esforco"] in nums:
            tipo_cad = "dt" if re.search(r"\bDT\b|DUPLO", cu) else \
                ("circular" if re.search(r"CIRC|\bFV\b|FIBRA", cu) else None)
            if tipo_cad is None or pp["tipo"] is None or tipo_cad == pp["tipo"]:
                return 0.93
        return 0.0
    na, nb = _numeros(proj), _numeros(cad)
    if collections.Counter(na) - collections.Counter(nb):
        return 0.0
    pena = 0.05 * (len(nb) - len(na))            # cadastro com números a mais
    nota = difflib.SequenceMatcher(None, a, b).ratio()
    if min(len(a), len(b)) < 8:          # código curto: uma letra muda o material (FLBIM x FLBIT)
        nota = 0.0
    if a in b and (len(a) >= 4 or na):
        nota = max(nota, 0.8 + 0.2 * len(a) / len(b))
    toks = _letras(proj)
    if toks:
        palavras = _letras(cad)
        # letra solta (o "R" de IT-R) tem que ser igual; sigla pode ser começo de palavra
        achou = sum(len(t) for t in toks
                    if (t in palavras if len(t) == 1 else any(p.startswith(t) for p in palavras)))
        cob = achou / sum(len(t) for t in toks)
        nota = max(nota, (0.5 + 0.4 * cob) if na else (0.3 + 0.45 * cob))
        # palavra do projeto que não existe no cadastro (o ATRINT de "ATRINT PARA-RAIO")
        pena += 0.2 * sum(1 for t in toks if len(t) >= 3 and not any(p.startswith(t) for p in palavras)
                          and t not in b)
        # nome curto que só aparece no meio de um nome comprido ("ATERRAMENTO" dentro de
        # "ARRUELA PRESILHA ATERRAMENTO FURO 18MM") não é esse material
        if palavras and not palavras[0].startswith(toks[0][:3]) and len(a) < 0.4 * len(b):
            nota = min(nota, 0.6)
    return max(0.0, min(nota - pena, 0.99))


def normaliza_codigo(c):
    c = str(c).strip()
    if isinstance(c, str) and re.fullmatch(r"\d+(\.0+)?", c):
        c = str(int(float(c)))            # 0400057 / 400057.0 -> 400057
    return c


def info_poste(nome):
    """'11400FV' -> altura 11 m, 400 daN, circular; '12600D' -> 12 m, 600 daN, DT;
    '400/9' -> 9 m, 400 daN. None se não for poste."""
    t = _sem_acento(nome).upper().replace(" ", "")
    m = re.fullmatch(r"(\d{3,4})/(\d{1,2})(DT|D|FV|C|CC|CIRC)?", t)
    if m:
        alt, esf, suf = int(m.group(2)), int(m.group(1)), m.group(3)
    else:
        m = re.fullmatch(r"(\d{4,6})(DT|D|FV|C|CC|CIRC|B)?", t)
        if not m:
            return None
        dig, suf = m.group(1), m.group(2)
        if len(dig) == 4:
            alt, esf = int(dig[0]), int(dig[1:])
        else:
            alt, esf = int(dig[:2]), int(dig[2:])
    if not (7 <= alt <= 23) or esf < 75:
        return None
    if suf in ("DT", "D"):
        tipo = "dt"
    elif suf in ("FV", "C", "CC", "CIRC"):
        tipo = "circular"
    else:
        tipo = None                     # não informado: usa a configuração
    return {"altura": alt, "esforco": esf, "tipo": tipo, "fibra": suf == "FV"}


def fmt_num(v):
    return (f"{v:.2f}".rstrip("0").rstrip(".")).replace(".", ",")


def _und(u):
    u = (u or "").strip().upper()
    return {"CDA": "UN", "UN": "UN", "PC": "UN", "PÇ": "UN", "CJ": "CJ", "M": "M", "KG": "KG"}.get(u, u or "UN")


def formata_num(q):
    q = round(float(q), 3)
    return str(int(q)) if q == int(q) else f"{q:g}".replace(".", ",")


def formata_qtd(lin):
    u = lin["unidade"]
    return formata_num(lin["qtd"]) + (f" {u}" if u in ("M", "KG") else "")
