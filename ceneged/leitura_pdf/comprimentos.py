"""Leitor próprio de comprimentos ("45m") desenhados como linhas no PDF.

Parte do programa Levantamento de Materiais (Ceneged)."""

import math
import re
import cv2
import numpy as np

# ---------------------------------------------------------------------------
#  Leitor próprio de comprimentos ("45m") desenhados como linhas no PDF.
#  Os programas de CAD escrevem esses números com fontes de traço único
#  (tipo ISOCP/ROMANS). Aqui cada dígito tem um modelo desenhado com o mesmo
#  tipo de traço, e cada letra encontrada é comparada com os modelos.
#  Não precisa de Tesseract nem de nenhum programa extra.
# ---------------------------------------------------------------------------
_W, _H = 20, 32
_K3 = np.ones((3, 3), np.uint8)


def _esqueleto(m):
    m = m.copy()
    sk = np.zeros_like(m)
    el = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
    while m.any():
        er = cv2.erode(m, el)
        sk |= (m & ~cv2.dilate(er, el) & 1)
        m = er
    return sk


def _furos(m):
    cs, hi = cv2.findContours(m.astype(np.uint8), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hi is None:
        return 0
    lim = 0.02 * m.shape[0] * m.shape[1]
    return sum(1 for i, h in enumerate(hi[0]) if h[3] >= 0 and cv2.contourArea(cs[i]) > lim)


def _normaliza(m):
    ys, xs = np.nonzero(m)
    m = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h, w = m.shape
    esc = min(_H / h, _W / w)
    r = cv2.resize(m.astype(np.uint8) * 255, (max(1, int(w * esc)), max(1, int(h * esc))),
                   interpolation=cv2.INTER_AREA)
    q = np.zeros((_H + 8, _W + 8), np.uint8)
    y0, x0 = (_H + 8 - r.shape[0]) // 2, (_W + 8 - r.shape[1]) // 2
    q[y0:y0 + r.shape[0], x0:x0 + r.shape[1]] = (r > 50)
    q = cv2.GaussianBlur(cv2.dilate(_esqueleto(q), _K3).astype(np.float32), (7, 7), 0)
    q -= q.mean()
    q /= np.linalg.norm(q) + 1e-6
    return q.ravel(), w / h


def _cisalha(m, s):
    h, w = m.shape
    M = np.float32([[1, s, (-s * h if s < 0 else 0)], [0, 1, 0]])
    return cv2.warpAffine(m, M, (w + int(abs(s) * h) + 2, h))


def _arco(cx, cy, rx, ry, t0, t1, n=24):
    return [(cx + rx * math.cos(math.radians(t0 + (t1 - t0) * i / n)),
             cy + ry * math.sin(math.radians(t0 + (t1 - t0) * i / n))) for i in range(n + 1)]


def _L(*p):
    return list(p)


# modelos dos caracteres (x para a direita, y para baixo, altura 1)
_TRACOS = {
    "0": [[_arco(.3, .5, .3, .5, 0, 360)]],
    "1": [[_L((.3, 0), (.3, 1)), _L((.08, .2), (.3, 0))], [_L((.3, 0), (.3, 1))]],
    "2": [[_arco(.3, .27, .3, .27, 180, 400) + _L((0, 1), (.6, 1))],
          [_arco(.3, .27, .3, .27, 190, 370) + _L((.6, .27), (0, 1), (.6, 1))]],
    "3": [[_arco(.3, .25, .28, .25, 200, 450), _arco(.3, .74, .3, .26, 270, 520)],
          [_L((0, 0), (.6, 0), (.25, .42)) + _arco(.3, .7, .3, .3, 240, 520)]],
    "4": [[_L((.45, 1), (.45, 0), (0, .7), (.6, .7))],
          [_L((.4, 0), (0, .7), (.6, .7)), _L((.45, .35), (.45, 1))]],
    "5": [[_L((.55, 0), (.05, 0), (.03, .42)) + _arco(.3, .7, .3, .3, 225, 520)]],
    "6": [[_arco(.3, .7, .3, .3, 0, 360), _arco(.6, .65, .6, .65, 250, 180)],
          [_arco(.3, .7, .3, .3, 0, 360), _L((.5, 0), (.02, .65))]],
    "7": [[_L((0, 0), (.6, 0), (.15, 1))], [_L((0, 0), (.6, 0), (.25, 1))]],
    "8": [[_arco(.3, .25, .25, .25, 0, 360), _arco(.3, .73, .3, .27, 0, 360)]],
    "9": [[_arco(.3, .3, .3, .3, 0, 360), _arco(0, .35, .6, .65, 0, 70)],
          [_arco(.3, .3, .3, .3, 0, 360), _L((.6, .3), (.1, 1))]],
    "m": [[_L((0, 1), (0, .35)), _arco(.2, .55, .2, .2, 180, 360), _L((.4, .55), (.4, 1)),
           _arco(.6, .55, .2, .2, 180, 360), _L((.8, .55), (.8, 1))]],
}


def _desenha(tracos, alt=120, esp=6):
    pts = np.array([p for t in tracos for p in t])
    x0, y0 = pts.min(0)
    img = np.zeros((alt + 40, int(alt * (pts[:, 0].max() - x0)) + 40), np.uint8)
    for t in tracos:
        pp = np.array([[(x - x0) * alt + 20, (y - y0) * alt + 20] for x, y in t], np.int32)
        cv2.polylines(img, [pp], False, 1, esp)
    return img


_MODELOS = []
for _c, _vars in _TRACOS.items():
    for _tr in _vars:
        _m = _desenha(_tr)
        _nf = _furos(_m)
        for _s in (0, 0.12, -0.12):
            _v, _a = _normaliza(_cisalha(_m, _s) if _s else _m)
            _MODELOS.append((_c, _v, _a, _nf))
_MV = np.stack([m[1] for m in _MODELOS])
_MA = np.array([m[2] for m in _MODELOS])
_MF = np.array([m[3] for m in _MODELOS])
_MC = [m[0] for m in _MODELOS]


def _classifica_letra(m):
    v, a = _normaliza(m)
    nf = _furos(cv2.dilate(m, _K3))
    nota = _MV @ v - 0.3 * np.abs(np.log(_MA / a)) - 0.5 * (_MF != nf)
    melhor = {}
    for c, x in zip(_MC, nota):
        melhor[c] = max(melhor.get(c, -9), x)
    o = sorted(melhor.items(), key=lambda t: -t[1])
    c = o[0][0]
    if {o[0][0], o[1][0]} == {"3", "5"} and o[0][1] - o[1][1] < 0.1:
        ys, xs = np.nonzero(m)
        g = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        h, w = g.shape
        faixa = g[int(h * 0.2):int(h * 0.42)]
        esq, dir_ = faixa[:, :max(1, int(w * 0.3))].any(), faixa[:, int(w * 0.7):].any()
        if esq and not dir_:
            c = "5"
        elif dir_ and not esq:
            c = "3"
    return c, o[0][1]


def _ler_comprimento(palavra, nota_min=0.45):
    """Lê uma palavra (preto no branco, em pé). Devolve '45m' ou None."""
    tinta = (palavra < 128).astype(np.uint8)
    if tinta.sum() == 0:
        return None
    # acerta a inclinação (fonte itálica): a que deixa mais colunas vazias
    s = max(np.arange(0, 0.45, 0.05), key=lambda s: (_cisalha(tinta, s).sum(0) == 0).sum())
    t = cv2.dilate(_cisalha(tinta, s), _K3)
    n, lab, st, _ = cv2.connectedComponentsWithStats(t, connectivity=8)
    comps = sorted([k for k in range(1, n) if st[k, 4] > 5], key=lambda k: st[k, 0])
    grupos = []                          # pedaços de uma mesma letra (sobrepostos em x)
    for k in comps:
        x, w = st[k, 0], st[k, 2]
        if grupos:
            gx0, gx1, ks = grupos[-1]
            if min(gx1, x + w) - max(gx0, x) > 0.4 * min(w, gx1 - gx0):
                grupos[-1] = (min(gx0, x), max(gx1, x + w), ks + [k])
                continue
        grupos.append((x, x + w, [k]))
    if not 2 <= len(grupos) <= 5:
        return None
    txt = ""
    for _, _, ks in grupos:
        c, nota = _classifica_letra(np.isin(lab, ks).astype(np.uint8))
        if nota < nota_min:
            return None                  # não parece com nenhum caractere
        txt += c
    return txt if RE_COMPRIMENTO.match(txt) else None


RE_COMPRIMENTO = re.compile(r"^\d{1,4}\s?[mM]$")
