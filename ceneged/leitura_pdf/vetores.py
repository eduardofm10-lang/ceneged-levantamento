"""Vetores da página: caminhos, caixas e pilhas de caixas.

Parte do programa Levantamento de Materiais (Ceneged)."""

import ctypes
import cv2
import numpy as np
import pypdfium2.raw as pdfium_c

# ------------------------------------------------------------------ vetores da página
def coletar_caminhos(page):
    """Um passe só por todos os caminhos: [(obj, preenchido, contornado, subcaminhos)]"""
    out = []
    for i in range(pdfium_c.FPDFPage_CountObjects(page.raw)):
        o = pdfium_c.FPDFPage_GetObject(page.raw, i)
        if pdfium_c.FPDFPageObj_GetType(o) != pdfium_c.FPDF_PAGEOBJ_PATH:
            continue
        fm, st = ctypes.c_int(), ctypes.c_int()
        pdfium_c.FPDFPath_GetDrawMode(o, fm, st)
        out.append((i, bool(fm.value), bool(st.value), _subcaminhos(o)))
    return out


def caixas_vetoriais(caminhos):
    """Retângulos alinhados (caixas de material). -> [(x0, y0, x1, y1)]"""
    out = []
    for i, fill, stroke, subs in caminhos:
        if not stroke:
            continue
        for s in subs:
            if not 4 <= len(s) <= 6:
                continue
            a = np.array(s)
            x0, y0 = a.min(0)
            x1, y1 = a.max(0)
            w, h = x1 - x0, y1 - y0
            if w <= 0 or h <= 0:
                continue
            if all(min(abs(x - x0), abs(x - x1)) < 0.05 * w + 0.05 and min(abs(y - y0), abs(y - y1)) < 0.05 * h + 0.05
                   for x, y in a) and 2 < min(w, h) < 30 and 4 < max(w, h) < 150:
                if not any(abs(x0 - b[0]) < 0.3 and abs(y0 - b[1]) < 0.3 and abs(x1 - b[2]) < 0.3 and abs(y1 - b[3]) < 0.3
                           for b in out):
                    out.append((x0, y0, x1, y1))
    return out


def retangulos_de_linhas(caminhos, tol=0.4):
    """Retângulos desenhados com linhas soltas (cada lado um traço): duas horizontais com o
    mesmo começo e fim, fechadas por verticais nas duas pontas. Inclui o retângulo de fora
    de uma caixa com divisória. -> [(x0, y0, x1, y1)]"""
    hs, vs = [], []
    for i, fill, stroke, subs in caminhos:
        if not stroke:
            continue
        for s_ in subs:
            for k in range(len(s_) - 1):
                (xa, ya), (xb, yb) = s_[k], s_[k + 1]
                if abs(ya - yb) <= 0.05 and abs(xb - xa) > 2:
                    hs.append((min(xa, xb), max(xa, xb), (ya + yb) / 2))
                elif abs(xa - xb) <= 0.05 and abs(yb - ya) > 1:
                    vs.append(((xa + xb) / 2, min(ya, yb), max(ya, yb)))
    if not hs or not vs:
        return []
    V = np.array(vs, float)

    def fecha(x, y0, y1):
        m = (np.abs(V[:, 0] - x) <= tol) & (V[:, 1] <= y1 + tol) & (V[:, 2] >= y0 - tol)
        if not m.any():
            return False
        seg = sorted(V[m][:, 1:].tolist())
        pos = y0
        for a, b in seg:                     # os pedaços verticais cobrem de y0 a y1
            if a > pos + tol:
                return False
            pos = max(pos, b)
        return pos >= y1 - tol
    grupos = {}
    for x0, x1, y in hs:
        if not 4 < x1 - x0 < 150:
            continue
        grupos.setdefault((round(x0 / tol), round(x1 / tol)), []).append((x0, x1, y))
    out = []
    for lst in grupos.values():
        ys = sorted({round(y, 2) for _, _, y in lst})
        x0 = float(np.mean([a for a, _, _ in lst]))
        x1 = float(np.mean([b for _, b, _ in lst]))
        for i in range(len(ys)):
            for j in range(i + 1, len(ys)):
                if not 2 < ys[j] - ys[i] < 30:
                    continue
                if fecha(x0, ys[i], ys[j]) and fecha(x1, ys[i], ys[j]):
                    r = (x0, ys[i], x1, ys[j])
                    if not any(all(abs(r[q] - o[q]) < tol for q in range(4)) for o in out):
                        out.append(r)
    return out


def contar_pilhas(caixas):
    """Quantas caixas têm outra caixa de mesmo tamanho encostada (empilhada)."""
    n = 0
    for i, a in enumerate(caixas):
        vert = (a[3] - a[1]) > (a[2] - a[0])          # caixa "deitada" na leitura girada
        for j, b in enumerate(caixas):
            if i == j:
                continue
            if vert:
                mesma = abs(a[1] - b[1]) < 1.0 and abs(a[3] - b[3]) < 1.0
                gap = min(abs(b[0] - a[2]), abs(a[0] - b[2]))
                lado = a[2] - a[0]
            else:
                mesma = abs(a[0] - b[0]) < 1.0 and abs(a[2] - b[2]) < 1.0
                gap = min(abs(b[1] - a[3]), abs(a[1] - b[3]))
                lado = a[3] - a[1]
            if mesma and gap < 0.6 * lado:
                n += 1
                break
    return n


def pilhas_de_caixas(caixas):
    """Número da pilha de cada caixa (caixas encostadas = mesma pilha/balão)."""
    pai = list(range(len(caixas)))

    def raiz(i):
        while pai[i] != i:
            pai[i] = pai[pai[i]]
            i = pai[i]
        return i
    for i, a in enumerate(caixas):
        vert = (a[3] - a[1]) > (a[2] - a[0])
        for j in range(i + 1, len(caixas)):
            b = caixas[j]
            if vert:
                mesma = abs(a[1] - b[1]) < 1.0 and abs(a[3] - b[3]) < 1.0
                gap = min(abs(b[0] - a[2]), abs(a[0] - b[2]))
                lado = a[2] - a[0]
            else:
                mesma = abs(a[0] - b[0]) < 1.0 and abs(a[2] - b[2]) < 1.0
                gap = min(abs(b[1] - a[3]), abs(a[1] - b[3]))
                lado = a[3] - a[1]
            if mesma and gap < 0.6 * lado:
                pai[raiz(i)] = raiz(j)
    return [raiz(i) for i in range(len(caixas))]


_PARA_PE_TR = {0: lambda x, y: (x, -y), 90: lambda x, y: (-y, -x),
               180: lambda x, y: (-x, y), 270: lambda x, y: (y, x)}


class TextoTraco:
    """Traços pequenos da página (letras de fonte de traço) para desenhar e ler."""

    def __init__(self, caminhos, excluir=(), max_lado=12.0):
        self.subs, caixas = [], []
        for i, fill, stroke, subs in caminhos:
            if fill or not stroke or i in excluir or len(subs) > 5000:
                continue
            for s in subs:
                a = np.asarray(s)
                x0, y0 = a.min(0)
                x1, y1 = a.max(0)
                w, h = x1 - x0, y1 - y0
                if max(w, h) > max_lado:
                    continue
                if 4 <= len(a) <= 6 and min(w, h) > 0.5 and all(
                        min(abs(x - x0), abs(x - x1)) < 0.05 * w + 0.05 and
                        min(abs(y - y0), abs(y - y1)) < 0.05 * h + 0.05 for x, y in a):
                    continue                              # moldura de caixa, não é letra
                self.subs.append(a)
                caixas.append((x0, y0, x1, y1))
        self.B = np.array(caixas) if caixas else np.zeros((0, 4))

    def dentro(self, caixa, margem=0.2):
        """traços com o centro dentro da caixa (a barra "/" costuma sair da caixa)."""
        x0, y0, x1, y1 = caixa
        B = self.B
        cx, cy = (B[:, 0] + B[:, 2]) / 2, (B[:, 1] + B[:, 3]) / 2
        return np.nonzero((cx >= x0 - margem) & (cx <= x1 + margem) &
                          (cy >= y0 - margem) & (cy <= y1 + margem))[0]

    def imagem(self, caixa, ang, esc=10.0, margem=0.2, idx=None):
        """Desenha (em pé) os traços dentro da caixa. -> imagem cinza (texto preto)"""
        idx = self.dentro(caixa, margem) if idx is None else idx
        f = _PARA_PE_TR[ang]
        x0, y0, x1, y1 = caixa
        cantos = [f(x, y) for x, y in ((x0, y0), (x1, y1))]
        X0, Y0 = min(c[0] for c in cantos), min(c[1] for c in cantos)
        X1, Y1 = max(c[0] for c in cantos), max(c[1] for c in cantos)
        W, H = int((X1 - X0) * esc) + 9, int((Y1 - Y0) * esc) + 9
        img = np.full((H, W), 255, np.uint8)
        for k in idx:
            pts = np.array([f(x, y) for x, y in self.subs[k]])
            pts = np.round(((pts - (X0, Y0)) * esc + 4) * 8).astype(np.int32)
            cv2.polylines(img, [pts], False, 0, 1, lineType=cv2.LINE_8, shift=3)
        return img

    def palavras(self, ang, area=None):
        """Agrupa traços em palavras (tolerância proporcional ao tamanho de cada traço)."""
        B = self.B
        if not len(B):
            return []
        vert = ang in (90, 270)
        hi0, hi1 = (0, 2) if vert else (1, 3)            # eixo da altura das letras
        lo0, lo1 = (1, 3) if vert else (0, 2)            # eixo da leitura
        alt = np.maximum(B[:, hi1] - B[:, hi0], B[:, lo1] - B[:, lo0])
        pai = list(range(len(B)))

        def r(i):
            while pai[i] != i:
                pai[i] = pai[pai[i]]
                i = pai[i]
            return i
        ordem = np.argsort(B[:, lo0])
        amax = float(alt.max())
        for a_ in range(len(ordem)):
            i = ordem[a_]
            for b_ in range(a_ + 1, len(ordem)):
                j = ordem[b_]
                if B[j, lo0] - B[i, lo1] > amax:
                    break
                h = max(alt[i], alt[j])
                if B[j, lo0] - B[i, lo1] > 0.9 * min(alt[i], alt[j]) + 0.3:
                    continue                    # longe demais (medido pela letra menor)
                sob = min(B[i, hi1], B[j, hi1]) - max(B[i, hi0], B[j, hi0])
                ci, cj = (B[i, hi0] + B[i, hi1]) / 2, (B[j, hi0] + B[j, hi1]) / 2
                if sob > -0.1 * h and abs(ci - cj) < 0.7 * h:
                    pai[r(i)] = r(j)
        grupos = {}
        for i in range(len(B)):
            grupos.setdefault(r(i), []).append(i)
        out = []
        for g in grupos.values():
            bb = B[g]
            x0, y0, x1, y1 = bb[:, 0].min(), bb[:, 1].min(), bb[:, 2].max(), bb[:, 3].max()
            if area is not None and not (area[0] <= (x0 + x1) / 2 <= area[2] and area[1] <= (y0 + y1) / 2 <= area[3]):
                continue
            out.append(((x0, y0, x1, y1), np.array(g)))
        return out


# ------------------------------------------------------------------ rede de cabos
def _subcaminhos(o, M=None):
    m = pdfium_c.FS_MATRIX()
    pdfium_c.FPDFPageObj_GetMatrix(o, m)
    n = pdfium_c.FPDFPath_CountSegments(o)
    subs, cur = [], []
    for k in range(n):
        sg = pdfium_c.FPDFPath_GetPathSegment(o, k)
        x, y = ctypes.c_float(), ctypes.c_float()
        pdfium_c.FPDFPathSegment_GetPoint(sg, x, y)
        X, Y = m.a * x.value + m.c * y.value + m.e, m.b * x.value + m.d * y.value + m.f
        if pdfium_c.FPDFPathSegment_GetType(sg) == pdfium_c.FPDF_SEGMENT_MOVETO:
            if len(cur) > 1:
                subs.append(cur)
            cur = [(X, Y)]
        else:
            cur.append((X, Y))
    if len(cur) > 1:
        subs.append(cur)
    return subs
