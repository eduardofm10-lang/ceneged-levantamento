"""Delimitação automática da área do projeto.

Parte do programa Levantamento de Materiais (Ceneged)."""

import cv2
import numpy as np

# ---------------------------------------------------------------------------
#  Delimitação automática do projeto
# ---------------------------------------------------------------------------

def delimitar_automatico(page_desenho, tam=1500, info=None, sementes=None, rede_pts=None, proibidas=()):
    """
    page_desenho: página SEM textos e SEM imagens (rotação 0).
    Acha o desenho do projeto (ruas + rede) e devolve um polígono em volta dele,
    deixando de fora moldura, carimbo, legendas e tabelas.
    """
    pl, pb, pr, pt = page_desenho.get_bbox()
    sc = tam / max(pr - pl, pt - pb)
    img = page_desenho.render(scale=sc).to_numpy()[:, :, :3]
    g = cv2.cvtColor(np.ascontiguousarray(img), cv2.COLOR_RGB2GRAY)
    sat = img.max(2).astype(int) - img.min(2)
    tinta = ((g < 235) | (sat > 40)).astype(np.uint8)
    H, W = tinta.shape
    # tira retas horizontais/verticais longas (moldura, carimbo, tabelas), também as
    # tracejadas (divisória da legenda): fecha os vãos do tracejado antes de medir
    gh, gv = max(3, int(W * 0.02)), max(3, int(H * 0.02))
    lh = cv2.morphologyEx(cv2.morphologyEx(tinta, cv2.MORPH_CLOSE, np.ones((1, gh), np.uint8)),
                          cv2.MORPH_OPEN, np.ones((1, int(W * 0.12)), np.uint8))
    lv = cv2.morphologyEx(cv2.morphologyEx(tinta, cv2.MORPH_CLOSE, np.ones((gv, 1), np.uint8)),
                          cv2.MORPH_OPEN, np.ones((int(H * 0.12), 1), np.uint8))
    t = tinta & ~(lh | lv) & 1
    # divisórias: retas em pé/deitadas que cruzam boa parte da folha por dentro da
    # moldura (separam o desenho da coluna de legenda/carimbo). Nada passa por cima delas.
    def _divisorias(M, n_lin):
        """posições onde há UMA reta fina e contínua de pelo menos 45% da folha"""
        def corrida(v):
            v = np.concatenate([[0], v.astype(np.int8), [0]])
            d_ = np.diff(v)
            ini, fim = np.nonzero(d_ == 1)[0], np.nonzero(d_ == -1)[0]
            return int((fim - ini).max()) if len(ini) else 0
        cand = [i for i in range(int(M.shape[1] * 0.15), int(M.shape[1] * 0.85))
                if M[:, i].sum() >= 0.45 * n_lin and corrida(M[:, i]) >= 0.45 * n_lin]
        saida, grupo = [], []
        for i in cand + [None]:
            if grupo and (i is None or i != grupo[-1] + 1):
                if len(grupo) <= 4:            # reta fina (não é bloco de texto/tabela)
                    saida.append(grupo[len(grupo) // 2])
                grupo = []
            if i is not None:
                grupo.append(i)
        return saida
    def _cruzada(i, vertical):
        """quantas linhas do desenho atravessam a reta (desenho dos dois lados)"""
        M = t if vertical else t.T
        if i - 5 < 0 or i + 5 >= M.shape[1]:
            return 0
        return int((M[:, i - 5] & M[:, i + 5]).sum())
    # divisória atravessada pelo desenho (ruas, rede) não separa nada
    divs_x = [x for x in _divisorias(lv, H) if _cruzada(x, True) <= 0.01 * H]
    divs_y = [y for y in _divisorias(lh.T, W) if _cruzada(y, False) <= 0.01 * W]
    k = max(3, int(max(H, W) * 0.012))
    d = cv2.dilate(t, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    caixas_fora = []
    for X0, Y0, X1, Y1 in proibidas or ():        # quadros sem balão (figura, detalhe)
        u0, u1 = max(0, int((X0 - pl) * sc) - 2), min(W, int((X1 - pl) * sc) + 3)
        v0, v1 = max(0, int((pt - Y1) * sc) - 2), min(H, int((pt - Y0) * sc) + 3)
        d[v0:v1, u0:u1] = 0
        caixas_fora.append((u0, v0, u1, v1))
    for x in divs_x:
        d[:, max(0, x - 1):x + 2] = 0
    for y in divs_y:
        d[max(0, y - 1):y + 2, :] = 0
    n, lab, st, _ = cv2.connectedComponentsWithStats(d, connectivity=8)
    if n < 2:
        return [(pl, pb), (pr, pb), (pr, pt), (pl, pt)]
    # legendas e tabelas são feitas quase só de retas em pé/deitadas;
    # o desenho do projeto (ruas, rede, postes) não
    L = max(5, int(max(H, W) * 0.01))
    ax = (cv2.morphologyEx(t, cv2.MORPH_OPEN, np.ones((1, L), np.uint8)) |
          cv2.morphologyEx(t, cv2.MORPH_OPEN, np.ones((L, 1), np.uint8)))
    tot = np.bincount(lab[t > 0], minlength=n)
    axc = np.bincount(lab[ax > 0], minlength=n)

    def nota(i):
        return st[i, 2] * st[i, 3] * (1 - axc[i] / max(tot[i], 1)) ** 2

    melhor = max(range(1, n), key=nota)
    ids_sem = set()
    if sementes is not None and len(sementes):
        # partes do desenho onde estão os balões e a rede do projeto
        for X, Y in sementes:
            u, v = int((X - pl) * sc), int((pt - Y) * sc)
            if 0 <= u < W and 0 <= v < H and lab[v, u] > 0:
                ids_sem.add(int(lab[v, u]))
        if ids_sem:
            melhor = max(ids_sem, key=lambda i: st[i, 4])
    sel = (lab == melhor).astype(np.uint8)
    x, y, w, h = st[melhor, :4]
    for i in ids_sem:
        if i != melhor:
            sel |= (lab == i).astype(np.uint8)
            x2, y2 = min(x, st[i, 0]), min(y, st[i, 1])
            w, h = max(x + w, st[i, 0] + st[i, 2]) - x2, max(y + h, st[i, 1] + st[i, 3]) - y2
            x, y = x2, y2
    # outro ramal grande do mesmo projeto (desenho em duas partes que quase se tocam)
    com_rede = set()
    if ids_sem and rede_pts is not None and len(rede_pts):
        for X, Y in rede_pts:
            u, v = int((X - pl) * sc), int((pt - Y) * sc)
            if 0 <= u < W and 0 <= v < H and lab[v, u] > 0:
                com_rede.add(int(lab[v, u]))
    for i in range(1, n):
        if ids_sem and i not in com_rede:
            continue                              # com balões: só partes com rede colorida
        if i != melhor and i not in ids_sem and nota(i) >= 0.2 * nota(melhor):
            sel |= (lab == i).astype(np.uint8)
            x2, y2 = min(x, st[i, 0]), min(y, st[i, 1])
            w, h = max(x + w, st[i, 0] + st[i, 2]) - x2, max(y + h, st[i, 1] + st[i, 3]) - y2
            x, y = x2, y2
    mx, my = int(w * 0.05), int(h * 0.05)
    for i in range(1, n):                       # pedaços soltos dentro do desenho
        if i == melhor:
            continue
        cx, cy = st[i, 0] + st[i, 2] / 2, st[i, 1] + st[i, 3] / 2
        if (x - mx <= cx <= x + w + mx and y - my <= cy <= y + h + my
                and st[i, 2] < w * 0.5 and st[i, 3] < h * 0.5):
            sel |= (lab == i).astype(np.uint8)
    # desenho feito de pedaços em fila (rua reta tirada como "reta comprida", sobram os
    # postes e balões um atrás do outro): junta os pedaços vizinhos, em cadeia
    perto = max(5, int(max(H, W) * 0.025))
    borda = int(max(H, W) * 0.04)
    pode = np.zeros(n, bool)
    for i in range(1, n):
        x_, y_, w_, h_ = st[i, :4]
        longe_borda = x_ > borda and y_ > borda and x_ + w_ < W - borda and y_ + h_ < H - borda
        pequeno = max(w_, h_) < 0.05 * max(H, W)      # poste, balão: não é tabela
        pode[i] = longe_borda and (pequeno or ((1 - axc[i] / max(tot[i], 1)) >= 0.5
                                                and w_ < W * 0.3 and h_ < H * 0.3))
    pode[melhor] = False
    ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * perto + 1, 2 * perto + 1))
    for _ in range(60):
        viz = np.unique(lab[(cv2.dilate(sel, ker) > 0) & (sel == 0)])
        novos = [i for i in viz if i > 0 and pode[i]]
        if not novos:
            break
        for i in novos:
            sel |= (lab == i).astype(np.uint8)
            pode[i] = False
    # ruas retas (em pé/deitadas) foram tiradas como "reta comprida": as que encostam no
    # desenho voltam (fora as da moldura, perto da borda da folha, e as divisórias)
    try:
        retas = ((lh | lv) & 1).astype(np.uint8)
        for x in divs_x:
            retas[:, max(0, x - 3):x + 4] = 0
        for y in divs_y:
            retas[max(0, y - 3):y + 4, :] = 0
        nr, labr, str_, _ = cv2.connectedComponentsWithStats(retas, connectivity=8)
        perto_sel = cv2.dilate(sel, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * k + 1, 2 * k + 1))) > 0
        borda_r = int(max(H, W) * 0.04)
        for i in range(1, nr):
            x_, y_, w_, h_ = str_[i, :4]
            if (x_ + w_ <= borda_r or x_ >= W - borda_r or y_ + h_ <= borda_r or y_ >= H - borda_r
                    or (w_ >= 0.8 * W) or (h_ >= 0.8 * H)):
                continue                                  # moldura
            m_ = labr == i
            if (m_ & perto_sel).any():
                sel |= cv2.dilate(m_.astype(np.uint8), np.ones((3, 3), np.uint8))
    except Exception:
        pass
    # o desenho fica do lado de cada divisória onde está a maior parte dele
    lado_x, lado_y = [], []
    ys_, xs_ = np.nonzero(lab == melhor)
    for x in divs_x:
        lado_x.append((x, (xs_ < x).sum() >= (xs_ > x).sum()))
    for y in divs_y:
        lado_y.append((y, (ys_ < y).sum() >= (ys_ > y).sum()))
    for x, esq in lado_x:
        if esq:
            sel[:, x:] = 0
        else:
            sel[:, :x + 1] = 0
    for y, cima in lado_y:
        if cima:
            sel[y:, :] = 0
        else:
            sel[:y + 1, :] = 0
    kk = max(5, int(max(H, W) * 0.06))
    reg = cv2.morphologyEx(sel, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kk, kk)))
    reg = cv2.dilate(reg, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k * 2, k * 2)))
    # a área do projeto é o contorno de fora de todo o desenho (sem reentrâncias): cada
    # parte separada do projeto vira um polígono convexo, com folga
    try:
        cs0, _ = cv2.findContours(reg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if cs0:
            amax = max(cv2.contourArea(c_) for c_ in cs0)
            casca = np.zeros_like(reg)
            for c_ in cs0:
                if cv2.contourArea(c_) >= 0.15 * amax:
                    cv2.fillPoly(casca, [cv2.convexHull(c_)], 1)
            casca = cv2.dilate(casca, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k * 2, k * 2)))
            # sem invadir outra parte grande desenhada (legenda, quadros): só onde não há tinta
            # de fora do desenho
            fora_desenho = (tinta > 0) & (cv2.dilate(sel, cv2.getStructuringElement(
                cv2.MORPH_ELLIPSE, (2 * k + 1, 2 * k + 1))) == 0)
            invade = cv2.dilate(fora_desenho.astype(np.uint8), np.ones((k, k), np.uint8)) > 0
            nova = (casca > 0) & ~(invade & (reg == 0))
            reg = nova.astype(np.uint8) | reg
    except Exception:
        pass
    if info is not None:   # divisórias em coordenada do PDF: o lado do desenho
        info["cortes"] = ([("x", pl + x / sc, esq) for x, esq in lado_x] +
                          [("y", pt - y / sc, not cima) for y, cima in lado_y])
    for x, esq in lado_x:
        if esq:
            reg[:, x:] = 0
        else:
            reg[:, :x + 1] = 0
    for y, cima in lado_y:
        if cima:
            reg[y:, :] = 0
        else:
            reg[:y + 1, :] = 0
    for u0, v0, u1, v1 in caixas_fora:
        reg[v0:v1, u0:u1] = 0
    # tira tabelas (legenda, carimbo): regiões cheias de retas em pé/deitadas
    Ls = max(5, int(max(H, W) * 0.02))
    retas = (cv2.morphologyEx(tinta, cv2.MORPH_OPEN, np.ones((1, Ls), np.uint8)) |
             cv2.morphologyEx(tinta, cv2.MORPH_OPEN, np.ones((Ls, 1), np.uint8))).astype(np.float32)
    jan = max(9, int(max(H, W) * 0.04)) | 1
    dens = cv2.boxFilter(retas, -1, (jan, jan))
    tabela = (dens > 0.06).astype(np.uint8)
    tabela = cv2.morphologyEx(tabela, cv2.MORPH_CLOSE, np.ones((jan, jan), np.uint8))
    nt, lt, stt, _ = cv2.connectedComponentsWithStats(tabela)
    for i in range(1, nt):
        if stt[i, 4] >= (jan * jan) * 2:
            reg[lt == i] = 0
    cs, _ = cv2.findContours(reg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    c = max(cs, key=cv2.contourArea)
    # projeto em partes separadas (ex.: ramal desenhado mais embaixo): liga as partes
    # grandes com uma faixa estreita, para o polígono pegar todas
    outras = [o for o in cs if o is not c and cv2.contourArea(o) >= 0.15 * cv2.contourArea(c)]
    if outras:
        ponte = max(3, k)
        for o in outras:
            P, Q = c[:, 0, :].astype(np.float32), o[:, 0, :].astype(np.float32)
            P, Q = P[::max(1, len(P) // 400)], Q[::max(1, len(Q) // 400)]
            dd = ((P[:, None, :] - Q[None, :, :]) ** 2).sum(2)
            a_, b_ = np.unravel_index(int(np.argmin(dd)), dd.shape)
            cv2.line(reg, tuple(int(v) for v in P[a_]), tuple(int(v) for v in Q[b_]), 1, ponte)
        cs, _ = cv2.findContours(reg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        c = max(cs, key=cv2.contourArea)
    c = cv2.approxPolyDP(c, max(H, W) * 0.004, True)[:, 0, :]
    return [(pl + float(px) / sc, pt - float(py) / sc) for px, py in c]
