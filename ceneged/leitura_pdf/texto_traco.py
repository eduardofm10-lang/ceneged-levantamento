"""Leitura de textos na fonte de traço do CAD (projetos "empilhados").

Parte do programa Levantamento de Materiais (Ceneged)."""

import cv2
import numpy as np

from ceneged.leitura_pdf.comprimentos import (_K3, _L, _arco)

# ---------------------------------------------------------------------------
#  Projetos "empilhados": textos em fonte de traço do CAD (ISOCP itálico),
#  materiais em caixas empilhadas e cabos seguindo o caminho tracejado
# ---------------------------------------------------------------------------
_TW, _TH = 20, 32


def _tr_esqueleto(m):
    m = (m > 0).astype(np.uint8)
    sk = np.zeros_like(m)
    el = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
    while m.any():
        er = cv2.erode(m, el)
        sk |= (m & ~cv2.dilate(er, el) & 1)
        m = er
    return sk


def _tr_furos(m):
    m = cv2.dilate(m.astype(np.uint8), _K3)
    cs, hi = cv2.findContours(m, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hi is None:
        return 0
    lim = 0.03 * m.shape[0] * m.shape[1]
    return sum(1 for i, h in enumerate(hi[0]) if h[3] >= 0 and cv2.contourArea(cs[i]) > lim)


def _tr_normal(m):
    ys, xs = np.nonzero(m)
    m = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1].astype(np.uint8)
    h, w = m.shape
    e = min((_TH - 4) / h, (_TW - 4) / w)
    r = cv2.resize(m * 255, (max(1, round(w * e)), max(1, round(h * e))), interpolation=cv2.INTER_AREA)
    q = np.zeros((_TH, _TW), np.uint8)
    y0, x0 = (_TH - r.shape[0]) // 2, (_TW - r.shape[1]) // 2
    q[y0:y0 + r.shape[0], x0:x0 + r.shape[1]] = r > 40
    return _tr_esqueleto(q)


def _tr_vet_esq(q):
    v = cv2.GaussianBlur(cv2.dilate(q.astype(np.uint8), _K3).astype(np.float32), (5, 5), 0).ravel()
    v -= v.mean()
    return v / (np.linalg.norm(v) + 1e-6)


def _tr_vetor(m):
    return _tr_vet_esq(_tr_normal(m))


def _tr_cisalha(m, s):
    h, w = m.shape
    M = np.float32([[1, s, (-s * h if s < 0 else 0)], [0, 1, 0]])
    return cv2.warpAffine(m, M, (w + int(abs(s) * h) + 2, h), flags=cv2.INTER_NEAREST)


def _lw(tr, y0=0.4):
    """desenho de altura 0..1 levado para altura de minúscula (y0..1)."""
    return [[(x, y0 + y * (1 - y0)) for x, y in t] for t in tr]


_TR_O = _arco(.3, .5, .3, .5, 0, 360)
_TR_TRACOS = {
    "0": [[_arco(.27, .5, .27, .5, 0, 360)]],
    "1": [[_L((.3, 0), (.3, 1)), _L((.08, .2), (.3, 0))]],
    "2": [[_arco(.27, .27, .27, .27, 180, 400) + _L((0, 1), (.55, 1))],
          [_arco(.27, .27, .27, .27, 190, 370) + _L((.54, .27), (0, 1), (.55, 1))]],
    "3": [[_arco(.27, .25, .25, .25, 200, 450), _arco(.27, .74, .27, .26, 270, 520)],
          [_L((0, 0), (.55, 0), (.22, .42)) + _arco(.27, .7, .27, .3, 240, 520)]],
    "4": [[_L((.42, 1), (.42, 0), (0, .7), (.56, .7))]],
    "5": [[_L((.5, 0), (.05, 0), (.03, .42)) + _arco(.27, .7, .27, .3, 225, 520)]],
    "6": [[_arco(.27, .72, .27, .28, 0, 360), _L((.48, .02), (.02, .65))],
          [_arco(.27, .72, .27, .28, 0, 360), _arco(.54, .65, .54, .65, 250, 180)]],
    "7": [[_L((0, 0), (.55, 0), (.15, 1))]],
    "8": [[_arco(.27, .25, .23, .25, 0, 360), _arco(.27, .73, .27, .27, 0, 360)]],
    "9": [[_arco(.27, .28, .27, .28, 0, 360), _L((.54, .3), (.08, 1))]],
    "A": [[_L((0, 1), (.3, 0), (.6, 1)), _L((.1, .67), (.5, .67))]],
    "B": [[_L((0, 1), (0, 0), (.32, 0)) + _arco(.32, .24, .22, .24, 270, 450) + _L((.32, .48), (0, .48)),
           _L((.34, .48)) + _arco(.34, .74, .25, .26, 270, 450) + _L((.34, 1), (0, 1))]],
    "C": [[_arco(.32, .5, .32, .5, 40, 320)]],
    "D": [[_L((0, 0), (0, 1), (.25, 1)) + _arco(.25, .5, .33, .5, 90, -90) + _L((.25, 0), (0, 0))]],
    "E": [[_L((.55, 0), (0, 0), (0, 1), (.55, 1)), _L((0, .5), (.42, .5))]],
    "F": [[_L((.55, 0), (0, 0), (0, 1)), _L((0, .5), (.42, .5))]],
    "G": [[_arco(.32, .5, .32, .5, 315, 0) + _L((.64, .5), (.64, .85)), _L((.36, .55), (.64, .55))]],
    "H": [[_L((0, 0), (0, 1)), _L((.6, 0), (.6, 1)), _L((0, .5), (.6, .5))]],
    "I": [[_L((0, 0), (0, 1))]],
    "J": [[_L((.5, 0), (.5, .72)) + _arco(.25, .72, .25, .28, 0, 180)]],
    "K": [[_L((0, 0), (0, 1)), _L((.58, 0), (0, .62)), _L((.2, .42), (.6, 1))]],
    "L": [[_L((0, 0), (0, 1), (.52, 1))]],
    "M": [[_L((0, 1), (0, 0), (.35, .65), (.7, 0), (.7, 1))]],
    "N": [[_L((0, 1), (0, 0), (.6, 1), (.6, 0))]],
    "O": [[_TR_O]],
    "P": [[_L((0, 1), (0, 0), (.36, 0)) + _arco(.36, .25, .22, .25, 270, 450) + _L((.36, .5), (0, .5))]],
    "Q": [[_TR_O, _L((.38, .72), (.66, 1.02))]],
    "R": [[_L((0, 1), (0, 0), (.36, 0)) + _arco(.36, .25, .22, .25, 270, 450) + _L((.36, .5), (0, .5)),
           _L((.3, .5), (.6, 1))]],
    "S": [[_arco(.3, .25, .28, .25, 340, 90) + _arco(.3, .75, .3, .25, 270, 520)]],
    "T": [[_L((0, 0), (.6, 0)), _L((.3, 0), (.3, 1))]],
    "U": [[_L((0, 0), (0, .7)) + _arco(.3, .7, .3, .3, 180, 0) + _L((.6, .7), (.6, 0))]],
    "V": [[_L((0, 0), (.3, 1), (.6, 0))]],
    "W": [[_L((0, 0), (.2, 1), (.4, .3), (.6, 1), (.8, 0))]],
    "X": [[_L((0, 0), (.6, 1)), _L((.6, 0), (0, 1))]],
    "Y": [[_L((0, 0), (.3, .5), (.6, 0)), _L((.3, .5), (.3, 1))]],
    "Z": [[_L((0, 0), (.6, 0), (0, 1), (.6, 1))]],
    "/": [[_L((.5, 0), (0, 1))]],
    "-": [[_L((0, .55), (.4, .55))]],
    "(": [[_arco(.4, .5, .4, .6, 140, 220)]],
    ")": [[_arco(0, .5, .4, .6, 40, -40)]],
    "+": [[_L((0, .55), (.5, .55)), _L((.25, .3), (.25, .8))]],
    ".": [[_L((0, .95), (.04, .95), (.04, 1), (0, 1), (0, .95))]],
    ",": [[_L((.05, .92), (.05, 1), (0, 1.15))]],
    "a": [_lw([_arco(.25, .5, .25, .5, 0, 360), _L((.5, 0), (.5, 1))])],
    "b": [[_L((0, 0), (0, 1))] + _lw([_arco(.25, .5, .25, .5, 0, 360)])],
    "c": [_lw([_arco(.25, .5, .25, .5, 40, 320)])],
    "d": [[_L((.5, 0), (.5, 1))] + _lw([_arco(.25, .5, .25, .5, 0, 360)])],
    "e": [_lw([_L((0, .5), (.5, .5)) + _arco(.25, .5, .25, .5, 0, -310)])],
    "i": [[_L((0, .4), (0, 1)), _L((0, .12), (0, .17))]],
    "k": [[_L((0, 0), (0, 1)), _L((.42, .4), (0, .78)), _L((.14, .66), (.44, 1))]],
    "l": [[_L((0, 0), (0, 1))]],
    "m": [_lw([_L((0, 1), (0, 0)), _arco(.18, .3, .18, .3, 180, 360) + _L((.36, .3), (.36, 1)),
               _arco(.54, .3, .18, .3, 180, 360) + _L((.72, .3), (.72, 1))])],
    "n": [_lw([_L((0, 1), (0, 0)), _arco(.22, .35, .22, .35, 180, 360) + _L((.44, .35), (.44, 1))])],
    "o": [_lw([_arco(.25, .5, .25, .5, 0, 360)])],
    "p": [[_L((0, .4), (0, 1.3))] + _lw([_arco(.25, .5, .25, .5, 0, 360)])],
    "r": [_lw([_L((0, 1), (0, 0)), _arco(.3, .4, .3, .4, 180, 290)])],
    "s": [_lw([_arco(.22, .25, .2, .25, 340, 90) + _arco(.22, .75, .22, .25, 270, 520)])],
    "t": [[_L((.1, .1), (.1, .85)) + _arco(.25, .85, .15, .15, 180, 90), _L((0, .4), (.32, .4))]],
    "u": [_lw([_L((0, 0), (0, .65)) + _arco(.22, .65, .22, .35, 180, 0), _L((.44, 0), (.44, 1))])],
    "v": [_lw([_L((0, 0), (.25, 1), (.5, 0))])],
    "x": [_lw([_L((0, 0), (.5, 1)), _L((.5, 0), (0, 1))])],
    "z": [_lw([_L((0, 0), (.5, 0), (0, 1), (.5, 1))])],
}



def _tr_desenha(tracos, alt=100, esp=3):
    pts = np.array([p for t in tracos for p in t])
    xmin = pts[:, 0].min()
    W = int(alt * (pts[:, 0].max() - xmin)) + 60
    img = np.zeros((int(alt * 1.5) + 60, W), np.uint8)
    for t in tracos:
        pp = np.array([[(x - xmin) * alt + 30, y * alt + 30] for x, y in t], np.int32)
        cv2.polylines(img, [pp], False, 1, esp)
    return img, 30, 30 + alt


# letras da fonte ISOCP aprendidas de projetos reais (esqueleto 32x20 compactado)
_TR_APRENDIDOS = (
    "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"
)
_TR_MOD = None


def _tr_modelos():
    global _TR_MOD
    if _TR_MOD is not None:
        return _TR_MOD
    import ast
    import base64
    import zlib
    lst = []
    for ch, rh, rb, asp, nf, b in ast.literal_eval(zlib.decompress(base64.b64decode(_TR_APRENDIDOS)).decode()):
        q = np.unpackbits(np.frombuffer(base64.b64decode(b), np.uint8))[:_TH * _TW].reshape(_TH, _TW)
        lst.append((ch, _tr_vet_esq(q), rh, rb, asp, nf, 0.12))     # bônus: da própria fonte
    for ch, vars_ in _TR_TRACOS.items():
        for tr in vars_:
            m, topo, base = _tr_desenha(tr)
            cap = base - topo
            ys, xs = np.nonzero(m)
            h, w = ys.max() - ys.min() + 1, xs.max() - xs.min() + 1
            for s in (0, 0.08, -0.08):
                mm = _tr_cisalha(m, s) if s else m
                lst.append((ch, _tr_vetor(mm), h / cap, (base - ys.max()) / cap, w / h, _tr_furos(m), 0.0))
    V = np.stack([t[1] for t in lst])
    F = np.array([t[2:] for t in lst], dtype=float)
    _TR_MOD = (lst, V, F)
    return _TR_MOD


def _tr_classifica(m, rh, rb, asp):
    lst, V, F = _tr_modelos()
    nota = V @ _tr_vetor(m) + F[:, 4] - 1.0 * np.abs(np.log(F[:, 0] / max(rh, 1e-3)))         - 0.6 * np.abs(F[:, 1] - rb) - 0.4 * np.abs(np.log(F[:, 2] / max(asp, 1e-3)))         - 0.3 * (F[:, 3] != _tr_furos(m))
    i = int(np.argmax(nota))
    return lst[i][0], float(nota[i])


def _tr_incl(tinta):
    return max(np.arange(0, 0.5, 0.04), key=lambda s: ((_tr_cisalha(tinta, s).sum(0) == 0).sum(), -abs(s - 0.2)))


def estimar_inclinacao_traco(imagens, limiar=240):
    """Inclinação do itálico (a mesma em todo o desenho)."""
    est = []
    for im in imagens:
        t = (im < limiar).astype(np.uint8)
        if t.sum() >= 20:
            est.append(_tr_incl(t))
    est = [e for e in est if e < 0.42]
    return float(np.median(est)) if est else 0.27


def ler_linha_traco(cinza, s, limiar=240):
    """Lê uma linha de texto de traço em pé. -> (texto, nota média)"""
    tinta = (cinza < limiar).astype(np.uint8)
    if tinta.sum() < 5:
        return "", -9
    t = _tr_cisalha(tinta, s)
    n, lab, st, _ = cv2.connectedComponentsWithStats(cv2.dilate(t, _K3), connectivity=8)
    comps = sorted([k for k in range(1, n) if st[k, 4] > 3], key=lambda k: st[k, 0])
    grupos = []
    for k in comps:
        x, y, w, h = st[k, :4]
        if grupos:
            g = grupos[-1]
            sob = min(g[1], x + w) - max(g[0], x)
            if sob > 0.4 * min(w, g[1] - g[0]):
                grupos[-1] = (min(g[0], x), max(g[1], x + w), g[2] + [k])
                continue
        grupos.append((x, x + w, [k]))
    caixas = []
    for x0, x1, ks in grupos:
        m = (np.isin(lab, ks) & (t > 0)).astype(np.uint8)
        ys, xs = np.nonzero(m)
        caixas.append((m, xs.min(), ys.min(), xs.max() + 1, ys.max() + 1, len(ks)))
    if not caixas:
        return "", -9
    hmax = float(max(c[4] - c[2] for c in caixas))
    altos = [c for c in caixas if c[4] - c[2] > 0.6 * hmax]
    base = float(np.median([c[4] for c in altos]))
    cap = max(base - float(np.median([c[2] for c in altos])), 1.0)
    txt, notas, ant = "", [], None
    for m, x0, y0, x1, y1, nk in caixas:
        h, w = y1 - y0, x1 - x0
        if h < 0.35 * cap:                                  # sinais pequenos
            if w > 1.5 * h and w > 0.2 * cap:
                ch, nota = ("-" if (y0 + y1) / 2 < base - 0.2 * cap else "_"), 0.9
            elif y1 > base + 0.1 * cap:
                ch, nota = ",", 0.8
            else:
                ch, nota = ".", 0.8
        else:
            ch, nota = _tr_classifica(m[y0:y1, x0:x1], h / cap, (base - y1) / cap, w / max(h, 1))
            if ch == "i" and nk == 1:                         # i sem pingo é I
                ch = "I"
        if ant is not None and x0 - ant > 0.5 * cap:
            txt += " "
        txt += ch
        notas.append(nota)
        ant = x1
    return txt, float(np.mean(notas))
