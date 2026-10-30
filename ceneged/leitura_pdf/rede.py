"""Rede de cabos: linhas tracejadas, comprimentos por vão, FLBIT/FLABIT meio/fim.

Parte do programa Levantamento de Materiais (Ceneged)."""

import ctypes
import math
import re
import numpy as np
import pypdfium2.raw as pdfium_c

from ceneged.leitura_pdf.vetores import _subcaminhos

def _alinhados(subs, gap=4.0):
    """fração de traços que têm outro traço na mesma reta logo em seguida (tracejado)."""
    A = np.array([(s[0][0], s[0][1], s[-1][0], s[-1][1]) for s in subs])
    ok = 0
    for k, (x0, y0, x1, y1) in enumerate(A):
        L = math.hypot(x1 - x0, y1 - y0)
        if L < 0.5:
            continue
        ux, uy = (x1 - x0) / L, (y1 - y0) / L
        perto = np.nonzero((np.hypot(A[:, 0] - x1, A[:, 1] - y1) < gap) | (np.hypot(A[:, 2] - x0, A[:, 3] - y0) < gap))[0]
        for j in perto:
            if j == k:
                continue
            X0, Y0, X1, Y1 = A[j]
            L2 = math.hypot(X1 - X0, Y1 - Y0)
            if L2 < 0.5:
                continue
            if abs(ux * (Y1 - Y0) / L2 - uy * (X1 - X0) / L2) < 0.1 and abs((X0 - x0) * uy - (Y0 - y0) * ux) < 0.4:
                ok += 1
                break
    return ok / max(len(A), 1)


def tracos_dos_caminhos(caminhos):
    """-> (tracejados {obj: [segmentos]}, solidos [segmentos])"""
    tracej, solidos = {}, []
    for i, fill, stroke, subs in caminhos:
        if not stroke:
            continue
        segs = [(s[k][0], s[k][1], s[k + 1][0], s[k + 1][1]) for s in subs for k in range(len(s) - 1)]
        segs = [g for g in segs if math.hypot(g[2] - g[0], g[3] - g[1]) > 1e-3]
        if len(subs) >= 4 and not fill:
            L = [sum(math.hypot(s[k + 1][0] - s[k][0], s[k + 1][1] - s[k][1]) for k in range(len(s) - 1))
                 for s in subs]
            med = float(np.median(L))
            if (1.5 < med < 35 and np.mean([abs(x - med) < 0.6 * med for x in L]) > 0.6
                    and _alinhados(subs, gap=max(4.0, 0.8 * med)) > 0.7):
                tracej[i] = segs
                continue
        solidos += segs
    return tracej, solidos


def _encadear_alinhados(F, med):
    """Junta traços de um tracejado: ponta perto da ponta do outro E seguindo na mesma
    direção (o ramal que sai de lado fica numa linha separada). -> id da linha de cada traço"""
    n = len(F)
    pai = list(range(n))

    def raiz(a):
        while pai[a] != a:
            pai[a] = pai[pai[a]]
            a = pai[a]
        return a
    U = np.column_stack([F[:, 2] - F[:, 0], F[:, 3] - F[:, 1]])
    U = U / np.maximum(np.hypot(U[:, 0], U[:, 1]), 1e-9)[:, None]
    P = np.vstack([F[:, :2], F[:, 2:]])
    dono = np.concatenate([np.arange(n), np.arange(n)])
    Lf = np.hypot(F[:, 2] - F[:, 0], F[:, 3] - F[:, 1])
    gap = max(2.0, 1.2 * med) if med is not None else 0.0
    cel = max(2.0, 1.2 * float(np.max(Lf)))          # grade com a maior distância possível
    grade = {}
    for q, (x, y) in enumerate(P):
        grade.setdefault((int(x // cel), int(y // cel)), []).append(q)
    for q, (x, y) in enumerate(P):
        gx, gy = int(x // cel), int(y // cel)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for q2 in grade.get((gx + dx, gy + dy), ()):
                    a, b = dono[q], dono[q2]
                    if a == b or raiz(a) == raiz(b):
                        continue
                    d = math.hypot(P[q2, 0] - x, P[q2, 1] - y)
                    if med is not None:
                        lim_ = gap
                        if max(Lf[a], Lf[b]) <= 5 * min(Lf[a], Lf[b]):
                            lim_ = max(gap, 1.2 * max(Lf[a], Lf[b]))   # traços compridos: vão maior
                        if d > lim_ or abs(U[a] @ U[b]) < 0.9:
                            continue
                    # vão até 1,2 traço; traços de tamanhos muito diferentes não são da mesma linha
                    elif d > max(2.0, 1.2 * max(Lf[a], Lf[b])) or abs(U[a] @ U[b]) < 0.9 \
                            or max(Lf[a], Lf[b]) > 5 * min(Lf[a], Lf[b]):
                        continue
                    if d > 1e-6:
                        v = (P[q2] - P[q]) / d
                        if abs(U[a] @ v) < 0.85:
                            continue
                    pai[raiz(a)] = raiz(b)
    return np.array([raiz(k) for k in range(n)])


def _cabo_de_cada_linha(rede, ancoras, lim, cores=None):
    """Cabo de cada linha do tracejado (linha = objeto da rede, um trecho reto):
    a linha onde encosta a caixa do cabo fica com ele; as linhas que continuam ponta com
    ponta (curva do cabo num poste) herdam, a mais próxima em passos; o ramal que sai do
    meio de outra linha não herda. ancoras: {peça: cabo} -> {obj: cabo}"""
    objs = sorted(set(rede.obj.tolist()))
    pontas = {}
    for o in objs:
        P = np.vstack([rede.P[rede.obj == o, :2], rede.P[rede.obj == o, 2:]])
        if len(P) < 2:
            continue
        u = P - P.mean(0)
        _, _, vt = np.linalg.svd(u, full_matrices=False)
        t = u @ vt[0]
        pontas[o] = (P[int(np.argmin(t))], P[int(np.argmax(t))])
    viz = {o: [] for o in pontas}
    lista = list(pontas)
    for i, a in enumerate(lista):
        for b in lista[i + 1:]:
            if min(math.dist(p, q) for p in pontas[a] for q in pontas[b]) <= lim:
                viz[a].append(b)
                viz[b].append(a)
    cabo, fila = {}, []
    for peca, nome in ancoras.items():
        o = rede.obj[peca]
        if o not in cabo:
            cabo[o] = nome
            fila.append(o)
    while fila:                                   # espalha pelas curvas (passo a passo)
        prox = []
        for o in fila:
            for v in viz.get(o, ()):
                if v in cabo:
                    continue
                if cores is not None and cores.get(o) is not None and cores.get(v) is not None \
                        and max(abs(a - b) for a, b in zip(cores[o], cores[v])) > 40:
                    continue                  # linha de outra cor (outra rede) não herda o cabo
                cabo[v] = cabo[o]
                prox.append(v)
        fila = prox
    # ramal sem nome escrito saindo do meio da linha de um cabo (num poste), da mesma cor:
    # é o mesmo cabo (ramal com nome próprio, como o 3#4CAA, já tem âncora e fica com o dele)
    mudou = True
    while mudou:
        mudou = False
        for o in pontas:
            if o in cabo:
                continue
            melhor = None
            for p_ in pontas[o]:
                for o2 in list(cabo):
                    if cores is not None and cores.get(o) is not None and cores.get(o2) is not None \
                            and max(abs(a - b) for a, b in zip(cores[o], cores[o2])) > 40:
                        continue
                    for g in rede.P[rede.obj == o2]:
                        d_ = _dist_seg(p_[0], p_[1], g)[0]
                        if d_ <= min(lim, 15.0) and (melhor is None or d_ < melhor[0]):
                            melhor = (d_, o2)
            if melhor:
                cabo[o] = cabo[melhor[1]]
                mudou = True
    return cabo


def tracejados_soltos(page, caminhos, min_tracos=3, cores=None):
    """Tracejado desenhado com cada traço num objeto separado (CAD que "explode" a linha):
    junta os traços curtos da mesma cor e espessura, em sequência na mesma direção.
    -> ({chave: [segmentos]}, {índices dos objetos usados}); chave = número negativo"""
    r_, g_, b_, a_ = ctypes.c_uint(), ctypes.c_uint(), ctypes.c_uint(), ctypes.c_uint()
    w_ = ctypes.c_float()
    por_estilo = {}
    for i, fill, stroke, subs in caminhos:
        if not stroke or fill or len(subs) != 1 or len(subs[0]) != 2:
            continue
        (x0, y0), (x1, y1) = subs[0]
        L = math.hypot(x1 - x0, y1 - y0)
        if not 1.5 < L < 60:
            continue
        o = pdfium_c.FPDFPage_GetObject(page.raw, i)
        pdfium_c.FPDFPageObj_GetStrokeColor(o, r_, g_, b_, a_)
        pdfium_c.FPDFPageObj_GetStrokeWidth(o, w_)
        est = ((r_.value, g_.value, b_.value), round(w_.value, 2))
        por_estilo.setdefault(est, []).append((i, (x0, y0, x1, y1)))
    saida, usados, chave = {}, set(), -1
    for est, lst in por_estilo.items():
        if len(lst) < min_tracos:
            continue
        F = np.array([g for _, g in lst], float)
        Lf = np.hypot(F[:, 2] - F[:, 0], F[:, 3] - F[:, 1])
        med_est = float(np.median(Lf))
        uniforme = np.mean(np.abs(Lf - med_est) < 0.4 * med_est) >= 0.6
        if uniforme:
            # cor/espessura só do tracejado (traços do mesmo tamanho)
            comp = _encadear_alinhados(F, med_est)
            minimo = max(min_tracos, 4)
        else:
            # mesma cor/espessura usada também em outros desenhos: separa linha por linha
            comp = _encadear_alinhados(F, None)
            minimo = min_tracos
        for c in set(comp.tolist()):
            ks = np.nonzero(comp == c)[0]
            if len(ks) < minimo:
                continue
            # tracejado: os traços da linha têm o mesmo tamanho
            med = float(np.median(Lf[ks]))
            if not uniforme and np.mean(np.abs(Lf[ks] - med) < 0.4 * med) < 0.6:
                continue
            saida[chave] = [tuple(F[k]) for k in ks]
            usados.update(lst[k][0] for k in ks)
            if cores is not None:
                cores[chave] = est[0]
            chave -= 1
    return saida, usados


def tracos_da_pagina(page):
    """-> (tracejados {obj: [segmentos]}, solidos [segmentos]); segmento = (x0,y0,x1,y1)"""
    tracej, solidos = {}, []
    for i in range(pdfium_c.FPDFPage_CountObjects(page.raw)):
        o = pdfium_c.FPDFPage_GetObject(page.raw, i)
        if pdfium_c.FPDFPageObj_GetType(o) != pdfium_c.FPDF_PAGEOBJ_PATH:
            continue
        fm, st = ctypes.c_int(), ctypes.c_int()
        pdfium_c.FPDFPath_GetDrawMode(o, fm, st)
        if not st.value:
            continue
        subs = _subcaminhos(o)
        segs = [(s[k][0], s[k][1], s[k + 1][0], s[k + 1][1]) for s in subs for k in range(len(s) - 1)]
        segs = [g for g in segs if math.hypot(g[2] - g[0], g[3] - g[1]) > 1e-3]
        if len(subs) >= 4 and not fm.value:
            L = [sum(math.hypot(s[k + 1][0] - s[k][0], s[k + 1][1] - s[k][1]) for k in range(len(s) - 1))
                 for s in subs]
            med = float(np.median(L))
            if (1.5 < med < 10 and np.mean([abs(x - med) < 0.6 * med for x in L]) > 0.6
                    and _alinhados(subs) > 0.7):
                tracej[i] = segs
                continue
        solidos += segs
    return tracej, solidos


def _dist_seg(px, py, s):
    x0, y0, x1, y1 = s
    dx, dy = x1 - x0, y1 - y0
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / L2))
    return math.hypot(px - (x0 + t * dx), py - (y0 + t * dy)), t


class Rede:
    def __init__(self, tracejados, area=None):
        """tracejados: {obj: [segmentos]}"""
        self.pecas = []          # (obj, seg)
        for obj, segs in tracejados.items():
            for s in segs:
                if area is None or (area[0] <= (s[0] + s[2]) / 2 <= area[2] and area[1] <= (s[1] + s[3]) / 2 <= area[3]):
                    self.pecas.append((obj, s))
        self.P = np.array([s for _, s in self.pecas], float) if self.pecas else np.zeros((0, 4))
        self.obj = np.array([o for o, _ in self.pecas])
        self._viz = None

    def mais_proxima(self, x, y, raio, obj=None):
        """peças a até 'raio' de (x, y): [(dist, idx)] ordenado."""
        if not len(self.P):
            return []
        P = self.P
        cx, cy = (P[:, 0] + P[:, 2]) / 2, (P[:, 1] + P[:, 3]) / 2
        meia = np.hypot(P[:, 2] - P[:, 0], P[:, 3] - P[:, 1]) / 2
        cand = np.nonzero(np.hypot(cx - x, cy - y) <= raio + meia)[0]
        out = []
        for i in cand:
            if obj is not None and self.obj[i] != obj:
                continue
            d, _ = _dist_seg(x, y, P[i])
            if d <= raio:
                out.append((d, int(i)))
        return sorted(out)

    def vizinhos(self, lim):
        """grafo: peças do mesmo objeto cujas pontas estão a até 'lim'."""
        if self._viz is not None:
            return self._viz
        P = self.P
        viz = [[] for _ in range(len(P))]
        pontas = np.vstack([P[:, :2], P[:, 2:]])
        dono = np.concatenate([np.arange(len(P)), np.arange(len(P))])
        ordem = np.argsort(pontas[:, 0])
        ps = pontas[ordem]
        for a in range(len(ps)):
            b = a + 1
            while b < len(ps) and ps[b, 0] - ps[a, 0] <= lim:
                if abs(ps[b, 1] - ps[a, 1]) <= lim:
                    i, j = dono[ordem[a]], dono[ordem[b]]
                    if i != j and self.obj[i] == self.obj[j] and math.hypot(*(ps[b] - ps[a])) <= lim:
                        d = math.hypot(*(ps[b] - ps[a]))
                        viz[i].append((j, d))
                        viz[j].append((i, d))
                b += 1
        self._viz = viz
        return viz


def ancoras_de_cabo(rede, baloes, solidos, tol=1.5, raio=10.0, raio_sem_chamada=30.0, raio_alt=25.0,
                    sem_chamada=True):
    """Liga cada balão de cabo a pontos do cabo tracejado:
    1) por cada linha de chamada (traço sólido que sai da borda do balão, seguindo
       os trechos encadeados até a ponta) - um balão pode ter mais de uma chamada;
    2) sem chamada: o cabo tracejado mais perto do balão.
    -> [(indice_balao, indice_peca)]"""
    S = np.array(solidos, float) if solidos else np.zeros((0, 4))
    pontas = np.vstack([S[:, :2], S[:, 2:]]) if len(S) else np.zeros((0, 2))
    lista = []                                   # (balão, candidatos)
    for k, b in enumerate(baloes):
        x0, y0, x1, y1 = b["bbox_pdf"]
        dentro = lambda x, y: (x0 - tol <= x <= x1 + tol) and (y0 - tol <= y <= y1 + tol)
        achou = False
        for lado in (0, 1):
            if not len(S):
                break
            px, py = S[:, 2 * lado], S[:, 2 * lado + 1]
            qx, qy = S[:, 2 - 2 * lado], S[:, 3 - 2 * lado]
            perto = ((px >= x0 - tol) & (px <= x1 + tol) & (py >= y0 - tol) & (py <= y1 + tol))
            fora = ~((qx >= x0 - tol) & (qx <= x1 + tol) & (qy >= y0 - tol) & (qy <= y1 + tol))
            for i in np.nonzero(perto & fora)[0]:
                ex, ey, usados = qx[i], qy[i], {i}
                for _ in range(6):                # segue a chamada encadeada
                    d = np.hypot(pontas[:, 0] - ex, pontas[:, 1] - ey)
                    prox = [j for j in np.nonzero(d < 0.3)[0] if j % len(S) not in usados]
                    if not prox:
                        break
                    seg = prox[0] % len(S)
                    usados.add(seg)
                    outro = S[seg, 2:] if prox[0] < len(S) else S[seg, :2]
                    if dentro(*outro):
                        break
                    ex, ey = outro
                if rede.mais_proxima(ex, ey, raio):
                    lista.append((k, rede.mais_proxima(ex, ey, raio_alt)))
                    achou = True
        if not achou and sem_chamada:
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            c = rede.mais_proxima(cx, cy, raio_sem_chamada + max(x1 - x0, y1 - y0) / 2)
            if c:
                lista.append((k, c))
    return _resolver(rede, baloes, lista)


# ---------------------------------------------------------------------------
#  FLBIT / FLABIT: poste no meio da rede leva conectores perfurantes; no fim, não.
#  A posição sai do desenho (linhas coloridas da rede que saem do poste) e pode
#  ser corrigida à mão.
# ---------------------------------------------------------------------------
RE_FIM_DE_REDE = re.compile(r"\bFLA?BIT\b")
def linhas_coloridas(page, caminhos, min_croma=120):
    """Traços coloridos (rede, normalmente) de subcaminhos abertos: [(x0,y0,x1,y1)].
    Fica de fora o que é preto/cinza (ruas, chamadas) e figuras fechadas (balões, caixas)."""
    out = []
    r, g, b, a = ctypes.c_uint(), ctypes.c_uint(), ctypes.c_uint(), ctypes.c_uint()
    for i, fill, stroke, subs in caminhos:
        if not stroke:
            continue
        o = pdfium_c.FPDFPage_GetObject(page.raw, i)
        if not pdfium_c.FPDFPageObj_GetStrokeColor(o, r, g, b, a):
            continue
        if max(r.value, g.value, b.value) - min(r.value, g.value, b.value) < min_croma:
            continue
        fechados = []
        n = pdfium_c.FPDFPath_CountSegments(o)
        for k in range(n):
            sg = pdfium_c.FPDFPath_GetPathSegment(o, k)
            if pdfium_c.FPDFPathSegment_GetType(sg) == pdfium_c.FPDF_SEGMENT_MOVETO:
                fechados.append(False)
            elif fechados and pdfium_c.FPDFPathSegment_GetClose(sg):
                fechados[-1] = True
        for j, s in enumerate(subs):
            if (j < len(fechados) and fechados[j]) or (len(s) > 3 and math.hypot(s[0][0] - s[-1][0], s[0][1] - s[-1][1]) < 0.05):
                continue
            out += [(s[k][0], s[k][1], s[k + 1][0], s[k + 1][1], r.value, g.value, b.value)
                    for k in range(len(s) - 1)]
    return out


def _matiz(cores):
    """matiz (0-360) de cores RGB [n x 3]"""
    c = np.asarray(cores, float).reshape(-1, 3) / 255.0
    mx, mn = c.max(1), c.min(1)
    d = np.maximum(mx - mn, 1e-9)
    r, g, b = c[:, 0], c[:, 1], c[:, 2]
    h = np.where(mx == r, ((g - b) / d) % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4))
    return h * 60.0


def _chamada_vertices(bbox, S, tol=1.5, passos=6):
    """Linhas de chamada (traço sólido que sai da borda do balão): [[vértices fora do balão]]"""
    if not len(S):
        return []
    x0, y0, x1, y1 = bbox
    dentro = lambda x, y: (x0 - tol <= x <= x1 + tol) and (y0 - tol <= y <= y1 + tol)
    P = np.vstack([S[:, :2], S[:, 2:]])
    saida = []
    for lado in (0, 1):
        px, py = S[:, 2 * lado], S[:, 2 * lado + 1]
        qx, qy = S[:, 2 - 2 * lado], S[:, 3 - 2 * lado]
        perto = (px >= x0 - tol) & (px <= x1 + tol) & (py >= y0 - tol) & (py <= y1 + tol)
        fora = ~((qx >= x0 - tol) & (qx <= x1 + tol) & (qy >= y0 - tol) & (qy <= y1 + tol))
        for i in np.nonzero(perto & fora)[0]:
            ex, ey, us = float(qx[i]), float(qy[i]), {int(i)}
            vert = [(ex, ey)]
            for _ in range(passos):
                d = np.hypot(P[:, 0] - ex, P[:, 1] - ey)
                pr = [j for j in np.nonzero(d < 0.3)[0] if j % len(S) not in us]
                if not pr:
                    break
                s = pr[0] % len(S)
                us.add(int(s))
                o = S[s, 2:] if pr[0] < len(S) else S[s, :2]
                if dentro(*o):
                    break
                ex, ey = float(o[0]), float(o[1])
                vert.append((ex, ey))
            saida.append(vert)
    return saida


def linhas_de_rede(segs, min_solido=20.0, min_cadeia=30.0, mascara=False):
    """Das linhas coloridas, as que formam rede: traço longo, ou tracejado/polilinha
    (pedaços alinhados e encadeados) com extensão de pelo menos `min_cadeia`."""
    C = np.asarray(segs, float).reshape(-1, 4)
    if not len(C):
        return np.zeros(0, bool) if mascara else C
    L = np.hypot(C[:, 2] - C[:, 0], C[:, 3] - C[:, 1])
    rede = L >= min_solido
    idx = np.nonzero((L >= 0.3) & (L < min_solido))[0]
    pai = {int(k): int(k) for k in idx}

    def raiz(a):
        while pai[a] != a:
            pai[a] = pai[pai[a]]
            a = pai[a]
        return a
    cel, grade = 6.0, {}
    for k in idx:
        for e in (0, 2):
            grade.setdefault((int(C[k, e] // cel), int(C[k, e + 1] // cel)), []).append((int(k), e))
    U = np.stack([C[:, 2] - C[:, 0], C[:, 3] - C[:, 1]], 1) / np.maximum(L, 1e-9)[:, None]
    for k in idx:
        for e in (0, 2):
            x, y = C[k, e], C[k, e + 1]
            gx, gy = int(x // cel), int(y // cel)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for j, f in grade.get((gx + dx, gy + dy), ()):
                        if j <= k or abs(U[k] @ U[j]) < 0.97:
                            continue
                        vx, vy = C[j, f] - x, C[j, f + 1] - y
                        g = math.hypot(vx, vy)
                        if g > max(6.0, 2.0 * max(L[k], L[j])):
                            continue
                        if g > 0.3 and abs((vx * U[k, 0] + vy * U[k, 1]) / g) < 0.97:
                            continue
                        pai[raiz(int(k))] = raiz(j)
    comp = {}
    for k in idx:
        comp.setdefault(raiz(int(k)), []).append(int(k))
    for ks in comp.values():
        if len(ks) < 3:
            continue
        P = np.vstack([C[ks, :2], C[ks, 2:]])
        if math.hypot(*(P.max(0) - P.min(0))) >= min_cadeia:
            rede[ks] = True
    return rede if mascara else C[rede]


def direcoes_da_rede(C, x, y, r1=3.0, rm=15.0, r2=45.0):
    """Direções (graus) em que a rede sai do ponto (x, y): trechos que se afastam do
    ponto e cobrem bem os dois anéis (perto e longe)."""
    nb = 36
    ci, co = np.zeros(nb), np.zeros(nb)
    if not len(C):
        return []
    cx, cy = (C[:, 0] + C[:, 2]) / 2, (C[:, 1] + C[:, 3]) / 2
    L = np.hypot(C[:, 2] - C[:, 0], C[:, 3] - C[:, 1])
    for k in np.nonzero((np.hypot(cx - x, cy - y) <= r2 + L / 2) & (L > 0.3))[0]:
        n = max(2, int(L[k] / 0.4) + 1)
        t = np.linspace(0, 1, n)
        st = L[k] / (n - 1)
        ux, uy = (C[k, 2] - C[k, 0]) / L[k], (C[k, 3] - C[k, 1]) / L[k]
        px = C[k, 0] + t * (C[k, 2] - C[k, 0]) - x
        py = C[k, 1] + t * (C[k, 3] - C[k, 1]) - y
        r = np.hypot(px, py)
        pr = (px * ux + py * uy) / np.maximum(r, 1e-6)
        ok = (r >= r1) & (r <= r2) & (np.abs(pr) > 0.85)
        if not ok.any():
            continue
        sg = np.sign(pr)
        a = (np.degrees(np.arctan2(sg * uy, sg * ux)) % 360 // (360 / nb)).astype(int) % nb
        for rr, aa in zip(r[ok], a[ok]):
            (ci if rr < rm else co)[aa] += st
    f = lambda v: np.maximum(np.maximum(v, np.roll(v, 1) + v), np.roll(v, -1) + v)
    ci, co = f(ci) / (rm - r1), f(co) / (r2 - rm)
    cand = sorted(((min(ci[b], co[b]), b * 10 + 5) for b in range(nb) if ci[b] >= 0.35 and co[b] >= 0.35),
                  reverse=True)
    dirs = []
    for _, ang in cand:
        if not any(min(abs(ang - d), 360 - abs(ang - d)) < 45 for d in dirs):
            dirs.append(ang)
    return dirs


def _ponto_na_rede(C, x, y, raio):
    if not len(C):
        return None
    cx, cy = (C[:, 0] + C[:, 2]) / 2, (C[:, 1] + C[:, 3]) / 2
    L = np.hypot(C[:, 2] - C[:, 0], C[:, 3] - C[:, 1])
    melhor = None
    for k in np.nonzero(np.hypot(cx - x, cy - y) <= raio + L / 2)[0]:
        x0, y0, x1, y1 = C[k]
        dx, dy = x1 - x0, y1 - y0
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((x - x0) * dx + (y - y0) * dy) / L2))
        qx, qy = x0 + t * dx, y0 + t * dy
        d = math.hypot(qx - x, qy - y)
        if d <= raio and (melhor is None or d < melhor[0]):
            melhor = (d, qx, qy)
    return melhor


def posicao_na_rede(bbox, solidos, rede, raio=25.0):
    """'fim' (a rede só chega por um lado), 'meio' (passa ou se divide no poste) ou None.
    O poste é a ponta da linha de chamada do balão (o vértice mais perto da rede).
    -> (posição, ponto do poste)"""
    d = analisar_poste(bbox, solidos, rede, raio)
    return d["pos"], d["poste"]


def ponto_da_chamada(bbox, solidos, rede, raio=10.0):
    """Onde a chamada de um balão de cabo encosta na rede (ou None)."""
    melhor = None
    for vert in _chamada_vertices(bbox, solidos):
        for vx, vy in vert:
            p = _ponto_na_rede(rede, vx, vy, raio)
            if p and (melhor is None or p[0] < melhor[0]):
                melhor = p
            if p:
                break
    return (melhor[1], melhor[2]) if melhor else None


def cabos_de_cada_lado(q, dirs, ancoras, alcance=400.0):
    """Para cada direção da rede que sai do poste, o cabo (PB) do balão de cabo cuja
    chamada encosta na rede nessa direção (o mais perto). ancoras: [(bitola, x, y)]"""
    saida = []
    for d in dirs:
        ux, uy = math.cos(math.radians(d)), math.sin(math.radians(d))
        melhor = None
        for g, x, y in ancoras:
            vx, vy = x - q[0], y - q[1]
            ao_longo = vx * ux + vy * uy
            lado = abs(-vx * uy + vy * ux)
            if 3.0 < ao_longo <= alcance and lado <= max(10.0, 0.2 * ao_longo):
                if melhor is None or ao_longo < melhor[0]:
                    melhor = (ao_longo, g)
        saida.append(melhor[1] if melhor else None)
    return saida


def analisar_poste(bbox, solidos, rede, raio=25.0):
    """-> {"pos": fim|meio|None, "poste": (x,y) ponta da chamada, "q": ponto na rede,
           "dirs": [graus]}"""
    vazio = {"pos": None, "poste": None, "q": None, "dirs": []}
    melhor = None
    for vert in _chamada_vertices(bbox, solidos):
        andado = 0.0
        for n, (vx, vy) in enumerate(vert):
            if n:
                andado += math.hypot(vx - vert[n - 1][0], vy - vert[n - 1][1])
            p = _ponto_na_rede(rede, vx, vy, raio)
            # quanto mais longe do balão (seguindo a chamada), pior: a chamada pode
            # encostar no poste e continuar por outra linha (aterramento, nota...)
            if p and (melhor is None or p[0] + 0.25 * andado < melhor[0]):
                melhor = (p[0] + 0.25 * andado, p[1], p[2], vx, vy)
            if p and p[0] <= 8.0:          # chegou na rede: o poste é aqui
                break
    if melhor is None:
        return vazio
    # as direções são medidas em cima da linha da rede; a marca na tela fica na
    # ponta da chamada, que é onde está o poste
    dirs = direcoes_da_rede(rede, melhor[1], melhor[2])
    pos = None if not dirs else ("fim" if len(dirs) == 1 else "meio")
    return {"pos": pos, "poste": (melhor[3], melhor[4]), "q": (melhor[1], melhor[2]), "dirs": dirs}


def _familia(txt):
    """'PB70' -> 'PB', '3xS04-13,8kV' -> 'kV' (rede primária)."""
    t = txt.upper()
    if "KV" in t:
        return "MT"
    return re.sub(r"[^A-Z]", "", t)[:2] or t


def _resolver(rede, baloes, lista):
    """Cada camada (objeto tracejado) costuma ser de uma rede só (MT ou BT).
    Se a chamada de um cabo BT cair na linha da MT (ou o contrário), por estarem
    lado a lado no mesmo poste, troca para a linha paralela da rede certa."""
    from collections import Counter
    esc = [lst[0][1] for _, lst in lista]
    cont = {}
    for (k, _), i in zip(lista, esc):
        cont.setdefault(rede.obj[i], Counter())[_familia(baloes[k]["texto"])] += 1
    dono = {o: c.most_common(1)[0][0] for o, c in cont.items()
            if len(c) == 1 or c.most_common(2)[0][1] > c.most_common(2)[1][1]}
    out = []
    for (k, lst), i in zip(lista, esc):
        f = _familia(baloes[k]["texto"])
        if dono.get(rede.obj[i], f) != f:
            i = next((j for d, j in lst if dono.get(rede.obj[j], f) == f), i)
        out.append((k, i))
    return out


def _ancoras_ordenadas(rede, p0, ancoras_peca, viz, max_cabos=6, max_dist=4000.0):
    """cabos alcançáveis a partir da peça p0 seguindo o tracejado: [(dist, cabo)]"""
    import heapq
    dist = {p0: 0.0}
    fila = [(0.0, p0)]
    achados = {}
    while fila and len(achados) < max_cabos:
        d, p = heapq.heappop(fila)
        if d > dist.get(p, 1e18) or d > max_dist:
            continue
        if p in ancoras_peca and ancoras_peca[p] not in achados:
            achados[ancoras_peca[p]] = d
        P = rede.P[p]
        comp = math.hypot(P[2] - P[0], P[3] - P[1])
        for q, g in viz[p]:
            nd = d + comp + g
            if nd < dist.get(q, 1e18):
                dist[q] = nd
                heapq.heappush(fila, (nd, q))
    return sorted((d, c) for c, d in achados.items())


def distribuir_comprimentos(rede, rotulos, ancoras_peca, baloes_cabo=(), raio=25.0, lim_viz=12.0, tol_par=7.0,
                            perto_proprio=45.0):
    """
    rotulos: [(metros, x, y)]; ancoras_peca: {indice_peca: cabo}
    baloes_cabo: [(cabo, bbox)] - para comprimento escrito colado no balão
    Cada comprimento vale para todas as linhas que passam por aquele vão (linhas
    paralelas = cabos diferentes, ex.: MT e BT no mesmo poste). O cabo de cada
    linha é o do balão mais próximo seguindo o próprio caminho tracejado.
    -> ({cabo: metros}, [(metros, x, y, [(cabo, peça)])])
    """
    viz = rede.vizinhos(lim_viz)
    cache = {}
    total, detalhe = {}, []
    for metros, x, y in rotulos:
        cand = rede.mais_proxima(x, y, raio)
        usados = []
        if cand:
            d0, i0 = cand[0]
            P0 = rede.P[i0]
            L0 = math.hypot(P0[2] - P0[0], P0[3] - P0[1]) or 1
            ux, uy = (P0[2] - P0[0]) / L0, (P0[3] - P0[1]) / L0
            linhas = []                                   # uma peça por linha paralela
            for d, i in cand:
                if d > d0 + tol_par:
                    break
                P = rede.P[i]
                L = math.hypot(P[2] - P[0], P[3] - P[1]) or 1
                if abs(ux * (P[3] - P[1]) / L - uy * (P[2] - P[0]) / L) > 0.2:
                    continue
                # distância com sinal do rótulo até a reta da peça: linhas
                # paralelas diferentes ficam em distâncias diferentes
                vx, vy = (P[2] - P[0]) / L, (P[3] - P[1]) / L
                if vx < 0 or (vx == 0 and vy < 0):
                    vx, vy = -vx, -vy
                off = (x - P[0]) * vy - (y - P[1]) * vx
                if all(abs(off - o2) > 2.0 for o2, _ in linhas):
                    linhas.append((off, i))
            opcoes = []
            for _, i in linhas:
                if i not in cache:
                    cache[i] = _ancoras_ordenadas(rede, i, ancoras_peca, viz)
                opcoes.append((i, cache[i]))
            # atribuição gulosa: cada linha paralela recebe um cabo diferente.
            # Se a linha não tem balão próprio por perto, ela é da outra rede
            # (ex.: MT passando no mesmo poste da BT), não da mesma família.
            livres = dict(opcoes)
            ja, familias = set(), set()
            while livres:
                melhor = None
                for i, lst in livres.items():
                    disp = [(d, c) for d, c in lst if c not in ja]
                    if not disp:
                        continue
                    d, c = disp[0]
                    if familias and _familia(c) in familias and d > perto_proprio:
                        outra = next(((d2, c2) for d2, c2 in disp if _familia(c2) not in familias), None)
                        if outra:
                            d, c = outra
                    if melhor is None or d < melhor[0]:
                        melhor = (d, i, c)
                if melhor is None:
                    break
                _, i, c = melhor
                usados.append((c, i))
                ja.add(c)
                familias.add(_familia(c))
                del livres[i]
        if not usados:                                    # comprimento ao lado do balão
            for c, (bx0, by0, bx1, by1) in baloes_cabo:
                if math.hypot(max(bx0 - x, 0, x - bx1), max(by0 - y, 0, y - by1)) <= 20:
                    usados = [(c, -1)]
                    break
        for c, _ in usados:
            total[c] = total.get(c, 0) + metros
        detalhe.append((metros, x, y, usados))
    return total, detalhe


def cabo_de_cada_peca(rede, ancoras_peca, lim_viz=12.0):
    """Para visualização: cabo de cada peça (âncora mais próxima pelo caminho)."""
    import heapq
    viz = rede.vizinhos(lim_viz)
    dist, cabo = {}, {}
    fila = []
    for p, c in ancoras_peca.items():
        dist[p] = 0.0; cabo[p] = c
        heapq.heappush(fila, (0.0, p))
    while fila:
        d, p = heapq.heappop(fila)
        if d > dist.get(p, 1e18):
            continue
        P = rede.P[p]
        comp = math.hypot(P[2] - P[0], P[3] - P[1])
        for q, g in viz[p]:
            nd = d + comp + g
            if nd < dist.get(q, 1e18):
                dist[q] = nd; cabo[q] = cabo[p]
                heapq.heappush(fila, (nd, q))
    return cabo
