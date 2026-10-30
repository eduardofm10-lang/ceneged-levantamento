"""Cerca: aterramento e seccionamento, nº de fios.

Parte do programa Levantamento de Materiais (Ceneged)."""

import ctypes
import math
import re
import cv2
import numpy as np
import pypdfium2.raw as pdfium_c
from PIL import ImageDraw

from ceneged.comum.texto import chave_nome
from ceneged.leitura_pdf.texto_contornos import (_matriz, _segmentos)
from ceneged.leitura_pdf.rede import _dist_seg
from ceneged.dados.composicoes import COMPOSICOES
from ceneged.dominio.materiais import itens_do_kit

# ---------------------------------------------------------------------------
#  Cerca: aterramento de cerca e seccionamento (figuras do desenho) + nº de fios
#  -> material principal "SIT. 01 - SECCIONAMENTO + ATERRAMENTOS"
# ---------------------------------------------------------------------------
RE_FIOS = re.compile(r"(\d{1,2})\s*F\s*[IlÍí1]\s*[O0]\s*S?\b")


def palavra_riscada(cs, S, cores=None, cor=None):
    """A palavra tem uma reta atravessando pelo meio, no sentido da escrita (texto riscado
    = cabo/material existente a retirar)? cs: letras da palavra; S: segmentos (N x 4).
    cores/cor: cor de cada segmento e a da palavra - o risco é da mesma cor do texto (a
    linha cinza da estrada passando por cima do texto não é risco)."""
    if cores is not None and cor is not None and len(S):
        ok = [k for k, c_ in enumerate(cores) if c_ is not None and max(abs(x - y) for x, y in zip(c_, cor)) <= 40]
        S = np.asarray(S)[ok] if ok else np.zeros((0, 4))
    if len(cs) < 3 or not len(S):
        return False
    pts = np.array([((c["l"] + c["r"]) / 2, (c["b"] + c["t"]) / 2) for c in cs])
    alt = float(np.median([min(c["t"] - c["b"], c["r"] - c["l"]) if False else max(c["t"] - c["b"], 0.3) for c in cs]))
    u = pts - pts.mean(0)
    _, _, vt = np.linalg.svd(u, full_matrices=False)
    d = vt[0]
    t = u @ d
    comp = float(t.max() - t.min())
    if comp <= 0:
        return False
    x0, y0 = pts.min(0) - 2
    x1, y1 = pts.max(0) + 2
    m = ((np.maximum(S[:, 0], S[:, 2]) >= x0) & (np.minimum(S[:, 0], S[:, 2]) <= x1) &
         (np.maximum(S[:, 1], S[:, 3]) >= y0) & (np.minimum(S[:, 1], S[:, 3]) <= y1))
    for g in S[m]:
        v = np.array([g[2] - g[0], g[3] - g[1]])
        L = float(np.hypot(*v))
        if L < 0.6 * comp or abs(v @ d) / L < 0.97:
            continue
        a = (np.array(g[:2]) - pts.mean(0)) @ d
        b = (np.array(g[2:]) - pts.mean(0)) @ d
        cobre = min(max(a, b), t.max()) - max(min(a, b), t.min())
        meio = (np.array([(g[0] + g[2]) / 2, (g[1] + g[3]) / 2]) - pts.mean(0))
        lado = abs(meio @ np.array([-d[1], d[0]]))
        if cobre >= 0.6 * comp and lado <= 0.45 * max(alt, 0.5):
            return True
    return False


def palavras_de_texto(chars):
    """Palavras lidas das letras desenhadas (cada leitor marca a palavra de cada letra).
    -> [(texto, (x0, y0, x1, y1), cor, [chars])]"""
    grupos = {}
    for c in chars:
        if c.get("pal") is not None:
            grupos.setdefault(c["pal"], []).append(c)
    saida = []
    for cs in grupos.values():
        txt = "".join(c["c"] for c in cs)
        bb = (min(c["l"] for c in cs), min(c["b"] for c in cs), max(c["r"] for c in cs), max(c["t"] for c in cs))
        saida.append((txt, bb, cs[0].get("cor"), cs))
    return saida


def linhas_de_texto(chars):
    """Junta letras em linhas (mesma direção e alinhadas). -> [(texto, [chars])]"""
    saida = []
    por_ang = {}
    for c in chars:
        a = round(math.degrees(c.get("ang", 0)) / 90) % 4 * 90
        por_ang.setdefault(a, []).append(c)
    for a, cs in por_ang.items():
        th = math.radians(a)
        ux, uy = math.cos(th), math.sin(th)
        itens = []
        for c in cs:
            cx, cy = (c["l"] + c["r"]) / 2, (c["b"] + c["t"]) / 2
            h = max(min(c["t"] - c["b"], c["r"] - c["l"]) if a % 180 == 0 else min(c["r"] - c["l"], c["t"] - c["b"]),
                    0.3)
            h = (c["t"] - c["b"]) if a % 180 == 0 else (c["r"] - c["l"])
            itens.append((cx * ux + cy * uy, -cx * uy + cy * ux, max(h, 0.3), c))
        itens.sort(key=lambda t: (t[1], t[0]))
        linhas = []
        for it in sorted(itens, key=lambda t: t[1]):
            ln = next((l_ for l_ in linhas if abs(l_[0] - it[1]) <= 0.5 * it[2]), None)
            if ln is None:
                linhas.append([it[1], [it]])
            else:
                ln[1].append(it)
        for v, its in linhas:
            its.sort(key=lambda t: t[0])
            atual, txt, ult = [], "", None
            for u, v_, h, c in its:
                if ult is not None and u - ult > 2.5 * h:
                    saida.append((txt, atual))
                    atual, txt = [], ""
                if ult is not None and u - ult > 0.9 * h and txt:
                    txt += " "
                txt += c["c"]
                atual.append(c)
                ult = u
            if atual:
                saida.append((txt, atual))
    return saida


def rotulos_fios(chars):
    """'N FIOS' escritos no desenho: [(n, x, y)]"""
    out = []
    for txt, cs in linhas_de_texto(chars):
        # (texto girado pode vir de trás para frente)
        ms = list(RE_FIOS.finditer(txt.upper())) or list(RE_FIOS.finditer(txt.upper()[::-1]))
        for m in ms:
            x = float(np.mean([(c["l"] + c["r"]) / 2 for c in cs]))
            y = float(np.mean([(c["b"] + c["t"]) / 2 for c in cs]))
            out.append((int(m.group(1)), x, y))
    return out


def simbolos_cerca(page, caminhos, com_cor=False):
    """Símbolos de cerca no desenho: aterramento de cerca (círculo com o sinal de terra
    dentro) e seccionamento (círculo cheio com uma barra). -> [(tipo 'A'|'S', x, y, r)]"""
    cor_de = {}
    r_, g_, b_, a_ = ctypes.c_uint(), ctypes.c_uint(), ctypes.c_uint(), ctypes.c_uint()
    segs, cheios, circ, polis, bolinhas, fechados = [], [], [], [], [], []
    for i, fill, stroke, subs in caminhos:
        o = pdfium_c.FPDFPage_GetObject(page.raw, i)
        # figura pequena: com as curvas (círculo feito de arcos)
        if subs:
            todos = np.array([q for s_ in subs for q in s_], float)
            if np.ptp(todos[:, 0]) < 25 and np.ptp(todos[:, 1]) < 25:
                try:
                    sc_ = _segmentos(o, _matriz(o))
                    if sc_:
                        subs = sc_
                except Exception:
                    pass
        if stroke:
            pdfium_c.FPDFPageObj_GetStrokeColor(o, r_, g_, b_, a_)
        else:
            pdfium_c.FPDFPageObj_GetFillColor(o, r_, g_, b_, a_)
        cor = (r_.value, g_.value, b_.value)
        croma = max(cor) - min(cor)
        for s in subs:
            P = np.array(s, float)
            if len(P) < 2:
                continue
            x0, y0 = P.min(0)
            x1, y1 = P.max(0)
            if fill:
                cheios.append((x0, y0, x1, y1, cor))
                if len(P) >= 3 and max(x1 - x0, y1 - y0) < 25:
                    polis.append((x0, y0, x1, y1, P))
            if len(P) >= 6 and max(x1 - x0, y1 - y0) < 30 and np.hypot(*(P[0] - P[-1])) < 0.05 * max(x1 - x0, y1 - y0, 1e-6):
                fechados.append((x0, y0, x1, y1, P, cor))
            if stroke:
                segs += [(P[k, 0], P[k, 1], P[k + 1, 0], P[k + 1, 1], cor) for k in range(len(P) - 1)]
                if len(P) >= 8 and croma >= 60:
                    Q = P[:-1] if np.hypot(*(P[0] - P[-1])) < 1e-6 else P
                    c = Q.mean(0)
                    d = np.hypot(P[:, 0] - c[0], P[:, 1] - c[1])
                    rr = d.mean()
                    if 1.0 < rr < 8.0 and d.std() < 0.12 * rr and np.hypot(*(P[0] - P[-1])) < 0.3 * rr:
                        circ.append((c[0], c[1], rr, cor))
                    elif 0.25 < rr <= 1.0 and d.std() < 0.15 * rr and np.hypot(*(P[0] - P[-1])) < 0.3 * rr:
                        bolinhas.append((c[0], c[1], rr, cor))
    if not circ and not bolinhas:
        return []
    S = np.array([s[:4] for s in segs], float).reshape(-1, 4)
    Scor = [s[4] for s in segs]
    saida = []
    for cx, cy, rr, cor in circ:
        if any(math.hypot(cx - q[1], cy - q[2]) < 0.5 * rr for q in saida):
            continue
        # cheio de mesma cor ocupando o círculo -> seccionamento
        # disco cheio (do tamanho do círculo, centrado)
        cheio = any(c_ == cor and x0 >= cx - 1.2 * rr and x1 <= cx + 1.2 * rr and y0 >= cy - 1.2 * rr and
                    y1 <= cy + 1.2 * rr and (x1 - x0) * (y1 - y0) >= 0.6 * (2 * rr) ** 2 and
                    math.hypot((x0 + x1) / 2 - cx, (y0 + y1) / 2 - cy) <= 0.3 * rr
                    for x0, y0, x1, y1, c_ in cheios)
        dentro, barra, cauda = [], 0, False
        if len(S):
            d0 = np.hypot(S[:, 0] - cx, S[:, 1] - cy)
            d1 = np.hypot(S[:, 2] - cx, S[:, 3] - cy)
            L = np.hypot(S[:, 2] - S[:, 0], S[:, 3] - S[:, 1])
            mesma = np.array([c_ == cor for c_ in Scor])
            m = ((d0 <= 1.0 * rr) & (d1 <= 1.0 * rr) & mesma & (L > 0.15 * rr) &
                 ~((d0 >= 0.8 * rr) & (d1 >= 0.8 * rr) & (L <= 0.8 * rr)))   # sem o próprio contorno
            dentro = list(np.nonzero(m)[0])
            # barra do seccionamento: duas retas paralelas que atravessam o círculo, uma de
            # cada lado do centro (a faixa branca)
            bs = []
            for k in np.nonzero(mesma & (L >= 1.2 * rr))[0]:
                dc, _ = _dist_seg(cx, cy, S[k])
                if dc <= 0.6 * rr and max(d0[k], d1[k]) <= 1.6 * rr:
                    bs.append(k)
            for i1 in range(len(bs)):
                for i2 in range(i1 + 1, len(bs)):
                    k1, k2 = bs[i1], bs[i2]
                    a1 = math.atan2(S[k1, 3] - S[k1, 1], S[k1, 2] - S[k1, 0])
                    a2 = math.atan2(S[k2, 3] - S[k2, 1], S[k2, 2] - S[k2, 0])
                    da = abs(math.degrees(a1 - a2)) % 180
                    if min(da, 180 - da) < 10:
                        nx, ny = -math.sin(a1), math.cos(a1)
                        o1 = (S[k1, 0] - cx) * nx + (S[k1, 1] - cy) * ny
                        o2 = (S[k2, 0] - cx) * nx + (S[k2, 1] - cy) * ny
                        if o1 * o2 < 0 and abs(o1 - o2) <= 0.9 * rr:
                            barra += 1
            # cauda do aterramento: reta que sai da borda do círculo para fora
            # (sai de dentro, do sinal de terra, e passa da borda)
            for k in np.nonzero(mesma & (L >= 1.0 * rr))[0]:
                perto, longe = min(d0[k], d1[k]), max(d0[k], d1[k])
                if perto <= 0.75 * rr and longe >= 1.8 * rr:
                    cauda = k
                    break
        paralelas = 0
        if cauda is not False and len(dentro) >= 3:
            # sinal de terra: traços perpendiculares à cauda, um atrás do outro no eixo
            # dela, cada um menor que o anterior
            at = math.atan2(S[cauda, 3] - S[cauda, 1], S[cauda, 2] - S[cauda, 0])
            ux, uy = math.cos(at), math.sin(at)
            tr = []
            for k in dentro:
                if k == cauda:
                    continue
                a_ = math.atan2(S[k, 3] - S[k, 1], S[k, 2] - S[k, 0])
                da = abs(math.degrees(a_ - at)) % 180
                if abs(da - 90) > 20:
                    continue
                mx, my = (S[k, 0] + S[k, 2]) / 2 - cx, (S[k, 1] + S[k, 3]) / 2 - cy
                lado = abs(-mx * uy + my * ux)
                if lado <= 0.35 * rr:
                    tr.append((mx * ux + my * uy, L[k]))
            tr.sort()
            if len(tr) >= 3:
                ls = [l_ for _, l_ in tr]
                cres = all(ls[j] < ls[j + 1] + 0.05 * rr for j in range(len(ls) - 1))
                decr = all(ls[j] > ls[j + 1] - 0.05 * rr for j in range(len(ls) - 1))
                if (cres or decr) and max(ls) >= 1.6 * min(ls):
                    paralelas = len(tr)
        # disco preenchido (de qualquer cor, ou hachurado) partido ao meio por uma faixa
        # vazia que passa pelo centro
        partido = False
        if not cheio:
            n_ = 41
            m_ = np.zeros((n_, n_), np.uint8)
            esc_ = (n_ - 1) / (2.4 * rr)
            for x0, y0, x1, y1, P in polis:
                if x1 < cx - 1.2 * rr or x0 > cx + 1.2 * rr or y1 < cy - 1.2 * rr or y0 > cy + 1.2 * rr:
                    continue
                q = np.column_stack([(P[:, 0] - (cx - 1.2 * rr)) * esc_, ((cy + 1.2 * rr) - P[:, 1]) * esc_])
                cv2.fillPoly(m_, [np.round(q).astype(np.int32)], 1)
            yy, xx = np.mgrid[0:n_, 0:n_]
            disco = np.hypot(xx - (n_ - 1) / 2, yy - (n_ - 1) / 2) <= 0.9 * rr * esc_
            cob = (m_[disco] > 0).mean() if disco.any() else 0
            meio = m_[(n_ // 2 - 1):(n_ // 2 + 2), (n_ // 2 - 1):(n_ // 2 + 2)]
            if cob >= 0.35 and meio.mean() < 0.5:
                nc, _, stc, _ = cv2.connectedComponentsWithStats((m_ * disco).astype(np.uint8))
                grandes = sum(1 for k in range(1, nc) if stc[k, 4] >= 0.12 * disco.sum())
                partido = grandes >= 2
        # círculo vazio cortado por duas barras paralelas ("//"), sem o sinal de terra
        # (o símbolo de poste meio cheio tem dezenas de traços paralelos do preenchimento)
        aberto_barras = (not cheio and 1 <= barra <= 4 and paralelas < 3 and cauda is False
                         and len(dentro) <= 4)
        if (cheio and barra >= 1) or partido or aberto_barras:
            saida.append(("S", cx, cy, rr, cor))
        elif not cheio and not partido and paralelas >= 3:
            saida.append(("A", cx, cy, rr, cor))
    saida += _halteres(bolinhas, S, Scor, cheios, saida, circ, fechados)
    return saida if com_cor else [q[:4] for q in saida]


def _cruza_seg(q, s, minimo):
    """o raio q (x0,y0 -> x1,y1) corta o segmento s a mais de 'minimo' da origem?"""
    x1, y1, x2, y2 = q
    x3, y3, x4, y4 = s[:4]
    den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(den) < 1e-12:
        return False
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
    u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / den
    return 0 <= t <= 1 and 0 <= u <= 1 and t * math.hypot(x2 - x1, y2 - y1) > minimo


def _halteres(bolinhas, S, Scor, cheios, ja, circ=(), fechados=()):
    """Aterramento de cerca desenhado como "halter": duas bolinhas pequenas preenchidas
    (ou hachuradas), da mesma cor e tamanho parecido, ligadas por um traço reto.
    -> [("A", x, y, r, cor)]"""
    if len(bolinhas) < 2 or not len(S):
        return []
    B = np.array([b[:3] for b in bolinhas], float)
    L = np.hypot(S[:, 2] - S[:, 0], S[:, 3] - S[:, 1])

    def preenchida(cx, cy, rr, cor):
        if any(c_ == cor and x0 >= cx - 1.3 * rr and x1 <= cx + 1.3 * rr and y0 >= cy - 1.3 * rr and
               y1 <= cy + 1.3 * rr and (x1 - x0) * (y1 - y0) >= 0.5 * (2 * rr) ** 2
               for x0, y0, x1, y1, c_ in cheios):
            return True
        # hachura: traços curtos da mesma cor dentro da bolinha
        d0 = np.hypot(S[:, 0] - cx, S[:, 1] - cy)
        d1 = np.hypot(S[:, 2] - cx, S[:, 3] - cy)
        dentro = (d0 <= 1.05 * rr) & (d1 <= 1.05 * rr) & (L >= 0.3 * rr)
        return sum(1 for k in np.nonzero(dentro)[0] if Scor[k] == cor) >= 2

    usadas, saida = set(), []
    for i in range(len(bolinhas)):
        if i in usadas:
            continue
        xi, yi, ri, ci = bolinhas[i]
        d = np.hypot(B[:, 0] - xi, B[:, 1] - yi)
        for j in np.argsort(d):
            j = int(j)
            if j == i or j in usadas:
                continue
            xj, yj, rj, cj = bolinhas[j]
            dist = d[j]
            if dist > 5.5 * max(ri, rj):
                break
            # halter: as bolinhas separadas por um traço visível (não encostadas)
            if cj != ci or dist - ri - rj < 0.5 * max(ri, rj) or max(ri, rj) > 1.6 * min(ri, rj):
                continue
            # traço reto da mesma cor ligando as duas bolinhas (de borda a borda)
            liga = False
            for k in np.nonzero(L >= 0.4 * (dist - ri - rj))[0]:
                if Scor[k] != ci:
                    continue
                a_ = (S[k, 0], S[k, 1]); b_ = (S[k, 2], S[k, 3])
                ok1 = min(math.dist(a_, (xi, yi)), math.dist(b_, (xi, yi))) <= 1.6 * ri
                ok2 = min(math.dist(a_, (xj, yj)), math.dist(b_, (xj, yj))) <= 1.6 * rj
                if ok1 and ok2:
                    liga = True
                    break
            if not liga or not (preenchida(xi, yi, ri, ci) and preenchida(xj, yj, rj, cj)):
                continue
            mx, my = (xi + xj) / 2, (yi + yj) / 2
            # pedaço de dentro de outra figura (contorno fechado maior da mesma cor em
            # volta, como o círculo do sinal de terra): não é halter
            dentro_de = False
            for x0, y0, x1, y1, P_, c_ in fechados:
                if c_ != ci or (x1 - x0) * (y1 - y0) < (2 * dist) ** 2:
                    continue
                if x0 <= mx <= x1 and y0 <= my <= y1 and \
                        cv2.pointPolygonTest(P_.astype(np.float32), (float(mx), float(my)), False) >= 0:
                    dentro_de = True
                    break
            if not dentro_de:
                # contorno feito de arcos abertos: traço da mesma cor em volta, nos 4 lados
                R_ = 3.0 * dist
                lados = 0
                ux, uy = (xj - xi) / dist, (yj - yi) / dist
                for vx, vy in ((ux, uy), (-ux, -uy), (-uy, ux), (uy, -ux)):
                    q = (mx, my, mx + R_ * vx, my + R_ * vy)
                    for k in np.nonzero(np.minimum(np.hypot(S[:, 0] - mx, S[:, 1] - my),
                                                   np.hypot(S[:, 2] - mx, S[:, 3] - my)) <= R_ + L)[0]:
                        if Scor[k] == ci and _cruza_seg(q, S[k], dist / 2 + max(ri, rj)):
                            lados += 1
                            break
                dentro_de = lados == 4
            if dentro_de:
                continue
            if any(math.hypot(mx - q[1], my - q[2]) < 1.5 * q[3] for q in ja + saida):
                continue
            # pedaço de dentro de outra figura (círculo maior em volta): não é halter
            if any(math.hypot(mx - c_[0], my - c_[1]) <= 1.2 * c_[2] + dist / 2 for c_ in circ):
                continue
            usadas.update((i, j))
            saida.append(("A", mx, my, dist / 2 + max(ri, rj), ci))
            break
    return saida


def segmentos_coloridos(page, caminhos, max_len=None):
    """[(x0,y0,x1,y1)], [(cor, largura)] de todos os traços"""
    S, info = [], []
    r_, g_, b_, a_ = ctypes.c_uint(), ctypes.c_uint(), ctypes.c_uint(), ctypes.c_uint()
    w_ = ctypes.c_float()
    for i, fill, stroke, subs in caminhos:
        if not stroke:
            continue
        o = pdfium_c.FPDFPage_GetObject(page.raw, i)
        pdfium_c.FPDFPageObj_GetStrokeColor(o, r_, g_, b_, a_)
        pdfium_c.FPDFPageObj_GetStrokeWidth(o, w_)
        cw = ((r_.value, g_.value, b_.value), round(w_.value, 2))
        for s in subs:
            for k in range(len(s) - 1):
                S.append((s[k][0], s[k][1], s[k + 1][0], s[k + 1][1]))
                info.append(cw)
    return np.array(S, float).reshape(-1, 4), info


def cercas_dos_simbolos(page, caminhos, simb):
    """Liga cada figura de cerca à linha da cerca onde ela está e junta as figuras da
    mesma cerca (pedaços encadeados da mesma cor e espessura).
    -> (comp_de_simbolo [id|None], S, info, comp[] por segmento)"""
    S, info = segmentos_coloridos(page, caminhos)
    if not len(S) or not simb:
        return [None] * len(simb), S, info, None
    L = np.hypot(S[:, 2] - S[:, 0], S[:, 3] - S[:, 1])
    mid = (S[:, :2] + S[:, 2:]) / 2
    sementes = []
    for q_ in simb:
        t, cx, cy, rr = q_[:4]
        # traços perto da figura mas fora dela (a linha da cerca)
        d0 = np.hypot(S[:, 0] - cx, S[:, 1] - cy)
        d1 = np.hypot(S[:, 2] - cx, S[:, 3] - cy)
        dm = np.array([_dist_seg(cx, cy, S[k])[0] if (min(d0[k], d1[k]) < 6 * rr + L[k]) else 99
                       for k in range(len(S))])
        fora = (np.maximum(d0, d1) > 1.3 * rr)          # não é traço do próprio símbolo
        alcance = 1.6 * rr if t == "S" else 4.5 * rr       # aterramento: cauda até a cerca
        cand = np.nonzero(fora & (dm <= alcance) & (L > 0.2))[0]
        # cor/espessura mais comum entre os candidatos, sem a cor do próprio símbolo
        sementes.append(list(cand))
    return sementes, S, info, None


def encadear(F):
    """Pedaços de linha (tracejado) ligados pelas pontas, seguindo a direção nas falhas.
    -> id do conjunto de cada pedaço"""
    if not len(F):
        return np.zeros(0, int)
    n = len(F)
    # liga pedaços (tracejado) cujas pontas estão perto
    P = np.vstack([F[:, :2], F[:, 2:]])
    dono = np.concatenate([np.arange(n), np.arange(n)])
    Lf = np.hypot(F[:, 2] - F[:, 0], F[:, 3] - F[:, 1])
    gap = max(2.0, 2.5 * float(np.median(Lf)))
    pai = list(range(n))

    def raiz(a):
        while pai[a] != a:
            pai[a] = pai[pai[a]]
            a = pai[a]
        return a
    cel = gap
    grade = {}
    for q, (x, y) in enumerate(P):
        grade.setdefault((int(x // cel), int(y // cel)), []).append(q)
    for q, (x, y) in enumerate(P):
        gx, gy = int(x // cel), int(y // cel)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for q2 in grade.get((gx + dx, gy + dy), ()):
                    if dono[q2] != dono[q] and math.hypot(P[q2, 0] - x, P[q2, 1] - y) <= gap:
                        pai[raiz(dono[q])] = raiz(dono[q2])
    comp = np.array([raiz(k) for k in range(n)])
    # cerca com uma falha no desenho (vão maior): junta pedaços cujas pontas ficam a até
    # 4 vãos, se seguem na mesma direção
    U = np.column_stack([F[:, 2] - F[:, 0], F[:, 3] - F[:, 1]]) / np.maximum(Lf, 1e-9)[:, None]
    for q, (x, y) in enumerate(P):
        k = dono[q]
        d = np.hypot(P[:, 0] - x, P[:, 1] - y)
        for q2 in np.nonzero((d > gap) & (d <= 4 * gap))[0]:
            k2 = dono[q2]
            if raiz(k) == raiz(k2):
                continue
            v = (P[q2] - P[q]) / max(d[q2], 1e-9)
            if abs(U[k] @ v) > 0.95 and abs(U[k2] @ v) > 0.95:
                pai[raiz(k)] = raiz(k2)
    comp = np.array([raiz(k) for k in range(n)])
    return comp


def _pontas_do_pedaco(Q, R=8.0):
    """Pontos de um pedaço de cerca que ficam na ponta (os vizinhos estão todos de um lado só)."""
    if len(Q) <= 2:
        return Q
    fica = []
    for k, (x, y) in enumerate(Q):
        v = Q - (x, y)
        n = np.hypot(v[:, 0], v[:, 1])
        perto = (n > 0.3) & (n <= R)
        if not perto.any():
            fica.append(k)
            continue
        u = v[perto] / n[perto][:, None]
        if np.hypot(*u.mean(axis=0)) > 0.7:
            fica.append(k)
    return Q[fica]


def _pontes_da_cerca(S, idx, F, comp, tol=1.5, max_len=40.0, so_vao=False):
    """Cerca que passa por uma figura (ex.: caixa com X, portão): o desenho liga a ponta de
    um pedaço da cerca à ponta do outro com um traço de outra cor. Esse traço junta os dois
    pedaços na mesma cerca. -> (F com as pontes, comp)"""
    if not len(F):
        return F, comp
    comp = comp.copy()
    P = np.vstack([F[:, :2], F[:, 2:]])
    dono = np.concatenate([np.arange(len(F)), np.arange(len(F))])
    usa = np.ones(len(S), bool)
    usa[idx] = False
    L = np.hypot(S[:, 2] - S[:, 0], S[:, 3] - S[:, 1])
    cand = np.nonzero(usa & (L > 3 * tol) & (L <= max_len))[0]
    if so_vao:
        cand = cand[:0]
    x0, y0, x1, y1 = P[:, 0].min(), P[:, 1].min(), P[:, 0].max(), P[:, 1].max()
    novos, ids = [], []
    for k in cand:
        s = S[k]
        if max(s[0], s[2]) < x0 - tol or min(s[0], s[2]) > x1 + tol or \
           max(s[1], s[3]) < y0 - tol or min(s[1], s[3]) > y1 + tol:
            continue
        da = np.hypot(P[:, 0] - s[0], P[:, 1] - s[1])
        db = np.hypot(P[:, 0] - s[2], P[:, 1] - s[3])
        qa, qb = int(np.argmin(da)), int(np.argmin(db))
        if da[qa] > tol or db[qb] > tol:
            continue
        ca, cb = comp[dono[qa]], comp[dono[qb]]
        if ca == cb:
            continue
        comp[comp == cb] = ca
        if ids:
            ids = [ca if c_ == cb else c_ for c_ in ids]
        novos.append(s)
        ids.append(ca)
    # cancela/portão desenhado de outro jeito (sem traço ligando as pontas): dois pedaços
    # que terminam perto um do outro com algum desenho no vão entre eles
    outros = S[usa]
    om = (outros[:, :2] + outros[:, 2:]) / 2 if len(outros) else np.zeros((0, 2))
    mudou = True
    while mudou:
        mudou = False
        cs = sorted(set(int(c_) for c_ in comp[:len(F)]))
        pts = {c_: _pontas_do_pedaco(P[comp[dono] == c_]) for c_ in cs}
        for i_, ca in enumerate(cs):
            for cb in cs[i_ + 1:]:
                A, B = pts[ca], pts[cb]
                if not len(A) or not len(B):
                    continue
                if A[:, 0].min() - B[:, 0].max() > max_len or B[:, 0].min() - A[:, 0].max() > max_len or \
                   A[:, 1].min() - B[:, 1].max() > max_len or B[:, 1].min() - A[:, 1].max() > max_len:
                    continue
                D = np.hypot(A[:, None, 0] - B[None, :, 0], A[:, None, 1] - B[None, :, 1])
                ia, ib = np.unravel_index(int(np.argmin(D)), D.shape)
                d = D[ia, ib]
                if d > max_len or d < 2 * tol:
                    continue
                m = (A[ia] + B[ib]) / 2
                dentro = np.nonzero(np.hypot(om[:, 0] - m[0], om[:, 1] - m[1]) <= d / 2 + tol)[0]
                if len(dentro) < 3:                # nada desenhado no vão: não é cancela
                    continue
                # a cancela encosta nas duas pontas da cerca
                sg = outros[dentro]
                ta = min(_dist_seg(A[ia][0], A[ia][1], q_)[0] for q_ in sg)
                tb = min(_dist_seg(B[ib][0], B[ib][1], q_)[0] for q_ in sg)
                if ta > 2 * tol or tb > 2 * tol:
                    continue
                comp[comp == cb] = ca
                ids = [ca if c_ == cb else c_ for c_ in ids]
                novos.append(np.array([A[ia][0], A[ia][1], B[ib][0], B[ib][1]]))
                ids.append(ca)
                mudou = True
                break
            if mudou:
                break
    if novos:
        F = np.vstack([F, np.array(novos, float)])
        comp = np.concatenate([comp, np.array(ids, int)])
    return F, comp


def componentes_cerca(page, caminhos, simb):
    """-> (id da cerca de cada figura ou None, segmentos da cerca, id de cada segmento)"""
    sem, S, info, _ = cercas_dos_simbolos(page, caminhos, simb)
    if not len(S) or not simb:
        return [None] * len(simb), np.zeros((0, 4)), np.zeros(0, int)
    votos = {}
    for c in sem:
        for st in set(info[k] for k in c):
            votos[st] = votos.get(st, 0) + 1
    # a cor/espessura que aparece perto de quase todas as figuras é a da cerca
    # (a do próprio símbolo é a de dentro do círculo: tira)
    cor_sim = set(q[4] for q in simb if len(q) > 4)      # cor do próprio símbolo
    cand = sorted(((v, st) for st, v in votos.items() if st[0] not in cor_sim), reverse=True)
    if not cand or cand[0][0] < 0.5 * len(simb):
        return [None] * len(simb), np.zeros((0, 4)), np.zeros(0, int)
    estilo = cand[0][1]
    idx = np.array([k for k in range(len(S)) if info[k] == estilo])
    F = S[idx]
    comp = encadear(F)
    F, comp = _pontes_da_cerca(S, idx, F, comp)
    saida = []
    pos = {g: q for q, g in enumerate(idx)}
    for c in sem:
        ks = [k for k in c if info[k] == estilo]
        if not ks:
            saida.append(None)
            continue
        saida.append(int(comp[pos[ks[0]]]))
    return saida, F, comp


def caixa_do_trecho(tr, folga=25.0):
    xs, ys = [], []
    for sg in tr.get("linha") or []:
        xs += [sg[0], sg[2]]
        ys += [sg[1], sg[3]]
    for q in tr.get("pontos") or []:
        xs.append(q[1])
        ys.append(q[2])
    if tr.get("fios_pos"):
        xs.append(tr["fios_pos"][0])
        ys.append(tr["fios_pos"][1])
    if not xs and tr.get("centro"):
        xs, ys = [tr["centro"][0]], [tr["centro"][1]]
    if not xs:
        return None
    return (min(xs) - folga, min(ys) - folga, max(xs) + folga, max(ys) + folga)


def imagem_do_trecho(page, tr, giro=0, lado=330):
    """Desenho da cerca do trecho (recorte da folha) com a linha da cerca em laranja,
    as figuras marcadas e o "N FIOS". -> PIL.Image ou None"""
    bb = caixa_do_trecho(tr)
    if bb is None:
        return None
    pl, pb, pr, pt = page.get_bbox()
    x0, y0 = max(bb[0], pl), max(bb[1], pb)
    x1, y1 = min(bb[2], pr), min(bb[3], pt)
    if x1 <= x0 or y1 <= y0:
        return None
    esc = min(lado / max(x1 - x0, y1 - y0), 12.0)
    img = page.render(scale=esc, crop=(x0 - pl, y0 - pb, pr - x1, pt - y1)).to_pil().convert("RGB")
    d = ImageDraw.Draw(img)
    T = lambda x, y: ((x - x0) * esc, (y1 - y) * esc)
    for sg in tr.get("linha") or []:
        d.line([T(sg[0], sg[1]), T(sg[2], sg[3])], fill=(255, 106, 0), width=4)
    for q in tr.get("pontos") or []:
        X, Y = T(q[1], q[2])
        R = max(7, q[3] * esc * 1.5)
        cor = (139, 0, 255) if q[0] == "A" else (0, 80, 255)
        d.ellipse([X - R, Y - R, X + R, Y + R], outline=cor, width=3)
        d.text((X + R + 2, Y - R), "ATERR" if q[0] == "A" else "SECC", fill=cor)
    if tr.get("fios_pos"):
        X, Y = T(*tr["fios_pos"])
        d.rectangle([X - 30, Y - 9, X + 30, Y + 9], outline=(0, 160, 0), width=2)
    if giro:
        img = img.rotate(-giro, expand=True)
    if max(img.size) > lado:
        f = lado / max(img.size)
        img = img.resize((max(1, int(img.size[0] * f)), max(1, int(img.size[1] * f))))
    return img


def kit_cerca(comp=None):
    """O material principal da cerca nos materiais extras (SIT. 01 - SECCIONAMENTO +
    ATERRAMENTOS)."""
    comp = comp or COMPOSICOES
    for k in comp.kits:
        if chave_nome(k["nome"]) == "SIT01SECCIONAMENTOATERRAMENTOS":
            return k
    for k in comp.kits:            # a que tem seccionador (a da cerca)
        if chave_nome(k["nome"]).startswith("SIT01") and any("SECCIONADOR" in chave_nome(i["nome"])
                                                             for i in k["itens"]):
            return k
    for k in comp.kits:
        if chave_nome(k["nome"]).startswith("SIT01"):
            return k
    for k in comp.kits:
        c = chave_nome(k["nome"])
        if "SECCIONAMENTO" in c and "ATERRAMENTO" in c:
            return k
    return None


def qtd_item_cerca(nome, q, cerca):
    """Quantidade de um material da SIT. 01:
       seccionador          = qtd x seccionamentos x fios
       conector L de cerca  = qtd x fios x aterramentos
       haste, arame         = qtd x aterramentos
       outros               = qtd (uma vez)"""
    c = chave_nome(nome)
    fios, aterr, secc = cerca.get("fios") or 0, cerca.get("aterr") or 0, cerca.get("secc") or 0
    if "SECCIONADOR" in c:
        return q * secc * fios
    if c.startswith("CONECTORL") or c.startswith("CONETORL"):
        return q * fios * aterr
    if "HASTE" in c or "ARAME" in c:
        return q * aterr
    return q


def cerca_valida(c):
    """cerca conferida: os três números (fios, aterramentos, seccionamentos) maiores que zero"""
    return bool(c) and not c.get("nao") and all((c.get(k) or 0) > 0 for k in ("fios", "aterr", "secc"))


def itens_do_kit_cerca(kit, cerca, ref):
    saida = []
    for m in itens_do_kit(kit, 1, ref, kit["nome"]):
        q = qtd_item_cerca(m["nome"], m["qtd"], cerca)
        if q <= 0:
            continue
        rot = (f"{kit['nome']} ({cerca['fios']} fios, {cerca['aterr']} aterr., "
               f"{cerca['secc']} secc.)")
        m.update(qtd=q, de=rot, partes={rot: q})
        saida.append(m)
    return saida
