"""Núcleo da detecção de balões (sem interface): regiões fechadas, texto, filtros.

Parte do programa Levantamento de Materiais (Ceneged)."""

import ctypes
import math
import re
import cv2
import numpy as np
import pypdfium2.raw as pdfium_c

from ceneged.comum.texto import chave_nome
from ceneged.leitura_pdf.comprimentos import (RE_COMPRIMENTO, _ler_comprimento)
from ceneged.leitura_pdf.vetores import coletar_caminhos

# ---------------------------------------------------------------------------
#  Núcleo: detecção (sem interface)
# ---------------------------------------------------------------------------

def ler_caracteres(page):
    """Lista de caracteres do PDF com caixa (coordenadas do PDF) e ângulo."""
    tp = page.get_textpage()
    chars = []
    espaco_antes = False
    for i in range(tp.count_chars()):
        cod = pdfium_c.FPDFText_GetUnicode(tp.raw, i)
        if cod == 0:
            continue
        ch = chr(cod)
        if ch.isspace() or ord(ch) < 32:
            espaco_antes = True        # o espaço real do PDF separa palavras
            continue
        l, b, r, t = tp.get_charbox(i)
        if r - l <= 0 and t - b <= 0:
            continue
        ang = pdfium_c.FPDFText_GetCharAngle(tp.raw, i)
        chars.append({"c": ch, "l": l, "b": b, "r": r, "t": t,
                      "ang": ang if ang >= 0 else 0.0, "esp": espaco_antes})
        espaco_antes = False
    return chars


def remover_textos(page, tipos=None):
    """
    Remove os objetos de texto da página (inclusive dentro de blocos/forms).
    Renderizando a página "só com desenho", o texto nunca encosta nem corta
    a borda do balão. O texto em si é lido antes, direto do PDF.
    """
    if tipos is None:
        tipos = (pdfium_c.FPDF_PAGEOBJ_TEXT,)

    def limpar(contar, pegar, remover):
        for i in reversed(range(contar())):
            obj = pegar(i)
            tipo = pdfium_c.FPDFPageObj_GetType(obj)
            if tipo in tipos:
                if remover(obj):
                    pdfium_c.FPDFPageObj_Destroy(obj)
            elif tipo == pdfium_c.FPDF_PAGEOBJ_FORM:      # blocos do CAD
                limpar(lambda f=obj: pdfium_c.FPDFFormObj_CountObjects(f),
                       lambda k, f=obj: pdfium_c.FPDFFormObj_GetObject(f, k),
                       lambda o, f=obj: pdfium_c.FPDFFormObj_RemoveObject(f, o))

    limpar(lambda: pdfium_c.FPDFPage_CountObjects(page.raw),
           lambda k: pdfium_c.FPDFPage_GetObject(page.raw, k),
           lambda o: pdfium_c.FPDFPage_RemoveObject(page.raw, o))
    page.gen_content()


def remover_imagens(page):
    """Remove fotos/imagens (mapa de satélite, logotipo...) da página."""
    remover_textos(page, (pdfium_c.FPDF_PAGEOBJ_IMAGE,))


def afinar_tracos(page, fator=0.15):
    """
    Deixa todas as linhas finas. Comprimentos como '45m' costumam ser letras
    DESENHADAS com caneta grossa (as letras se encostam); com traço fino elas
    ficam separadas e legíveis.
    """
    def afinar(contar, pegar):
        for i in range(contar()):
            obj = pegar(i)
            tipo = pdfium_c.FPDFPageObj_GetType(obj)
            if tipo == pdfium_c.FPDF_PAGEOBJ_PATH:
                w = ctypes.c_float()
                if pdfium_c.FPDFPageObj_GetStrokeWidth(obj, w) and w.value > 0:
                    pdfium_c.FPDFPageObj_SetStrokeWidth(obj, w.value * fator)
            elif tipo == pdfium_c.FPDF_PAGEOBJ_FORM:
                afinar(lambda f=obj: pdfium_c.FPDFFormObj_CountObjects(f),
                       lambda k, f=obj: pdfium_c.FPDFFormObj_GetObject(f, k))

    afinar(lambda: pdfium_c.FPDFPage_CountObjects(page.raw),
           lambda k: pdfium_c.FPDFPage_GetObject(page.raw, k))
    page.gen_content()


def montar_texto(chars):
    """Junta caracteres em linhas/palavras respeitando a direção do texto."""
    if not chars:
        return ""
    # direção predominante (texto pode estar girado no desenho)
    angs = [round(math.degrees(c["ang"]) / 90) % 4 * 90 for c in chars]
    ang = math.radians(max(set(angs), key=angs.count))
    # o pdfium mede o ângulo no sentido horário; y do PDF cresce para cima
    dx, dy = math.cos(ang), -math.sin(ang)         # direção da leitura
    nx, ny = dy, -dx                               # direção "para baixo" (próxima linha)

    itens = []
    for c in chars:
        cx, cy = (c["l"] + c["r"]) / 2, (c["b"] + c["t"]) / 2
        w, h = c["r"] - c["l"], c["t"] - c["b"]
        alt = abs(h * dx) + abs(w * dy)            # altura da letra
        larg = abs(w * dx) + abs(h * dy)           # largura da letra
        itens.append({"y": cx * nx + cy * ny, "x": cx * dx + cy * dy,
                      "alt": alt, "larg": larg, "c": c["c"], "esp": c["esp"]})

    alt_med = float(np.median([i["alt"] for i in itens])) or 1.0
    # 1) linhas formadas pelas letras "altas" (vírgula, ponto e hífen ficam fora)
    altas = sorted([i for i in itens if i["alt"] >= alt_med * 0.6], key=lambda i: i["y"])
    linhas = []
    for it in altas:
        if linhas and abs(it["y"] - linhas[-1][-1]["y"]) <= alt_med * 0.5:
            linhas[-1].append(it)
        else:
            linhas.append([it])
    centros = [float(np.mean([i["y"] for i in ln])) for ln in linhas]
    # 2) sinais pequenos entram na linha mais próxima
    for it in itens:
        if it["alt"] < alt_med * 0.6:
            if not linhas:
                linhas.append([it]); centros.append(it["y"]); continue
            k = int(np.argmin([abs(it["y"] - c) for c in centros]))
            linhas[k].append(it)

    saida = []
    for ln in linhas:
        ln.sort(key=lambda i: i["x"])
        txt, fim_ant = "", None
        for it in ln:
            ini = it["x"] - it["larg"] / 2
            if fim_ant is not None and (it["esp"] or ini - fim_ant > alt_med * 0.6) \
                    and not txt.endswith(" "):
                txt += " "
            txt += it["c"]
            fim_ant = it["x"] + it["larg"] / 2
        saida.append(txt.strip())
    return "\n".join(saida)


def angulo_texto(chars):
    """Ângulo predominante do texto (0, 90, 180, 270 graus; sentido do pdfium)."""
    angs = [round(math.degrees(c["ang"]) / 90) % 4 * 90 for c in chars]
    return max(set(angs), key=angs.count) if angs else 0


def faixas_no_texto(bbox, ang_graus):
    """Projeta um retângulo do PDF no sistema do texto:
    (ini, fim) ao longo da leitura e (ini, fim) 'para baixo' (entre linhas)."""
    a = math.radians(ang_graus)
    dx, dy = math.cos(a), -math.sin(a)
    nx, ny = dy, -dx
    xs = [bbox[0], bbox[2]]
    ys = [bbox[1], bbox[3]]
    ao_longo = [x * dx + y * dy for x in xs for y in ys]
    abaixo = [x * nx + y * ny for x in xs for y in ys]
    return (min(ao_longo), max(ao_longo)), (min(abaixo), max(abaixo))


def juntar_empilhados(baloes):
    """
    Balões colados um embaixo do outro (separados só por uma linha) são o mesmo
    material: o de cima é o principal e o de baixo vai entre parênteses.
    """
    n = len(baloes)
    abaixo_de = {}                      # i -> j (j está logo abaixo de i)
    for i in range(n):
        A = baloes[i]
        la, da = faixas_no_texto(A["bbox_pdf"], A["ang"])
        melhor = None
        for j in range(n):
            if i == j or baloes[j]["ang"] != A["ang"]:
                continue
            lb, db = faixas_no_texto(baloes[j]["bbox_pdf"], A["ang"])
            sobrepoe = min(la[1], lb[1]) - max(la[0], lb[0])
            menor = min(la[1] - la[0], lb[1] - lb[0])
            vao = db[0] - da[1]                 # espaço entre o fundo de A e o topo de B
            tol = max(A["alt"], baloes[j]["alt"], 2.0)
            if sobrepoe >= 0.5 * menor and -tol * 0.5 <= vao <= tol:
                if melhor is None or vao < melhor[0]:
                    melhor = (vao, j)
        if melhor:
            abaixo_de[i] = melhor[1]

    tem_acima = set(abaixo_de.values())
    usados, saida = set(), []
    for i in range(n):
        if i in tem_acima or i in usados:
            continue
        cadeia = [i]
        while cadeia[-1] in abaixo_de and abaixo_de[cadeia[-1]] not in cadeia:
            cadeia.append(abaixo_de[cadeia[-1]])
        usados.update(cadeia)
        b = dict(baloes[i])
        b["complementos"] = [baloes[k]["texto"] for k in cadeia[1:]]
        b["em_pilha"] = len(cadeia) > 1
        b["membros"] = [baloes[k]["bbox_pdf"] for k in cadeia]
        if len(cadeia) > 1:
            bbs = [baloes[k]["bbox_pdf"] for k in cadeia]
            b["bbox_pdf"] = (min(x[0] for x in bbs), min(x[1] for x in bbs),
                             max(x[2] for x in bbs), max(x[3] for x in bbs))
            b["chars"] = [c for k in cadeia for c in baloes[k]["chars"]]
        saida.append(b)
    for i in range(n):                    # sobra só em caso de ciclo (não deve ocorrer)
        if i not in usados:
            saida.append(dict(baloes[i], complementos=[]))
    return saida


# regra: até 4 números terminados em M (ex.: 45m, 120M, 1500m)
DEBUG_CANTOS = False


def canto_arredondado(page, bbox, uniao=False):
    """Renderiza o balão em alta resolução e olha os 4 cantos da área interna:
    balão tem canto arredondado; caixa retangular tem canto vivo.
    uniao=True (caixas empilhadas): junta as partes separadas pela divisória e olha
    os cantos de fora do conjunto."""
    x0, y0, x1, y1 = bbox
    lado = min(x1 - x0, y1 - y0)
    if lado <= 0:
        return True
    m = max(0.2 * lado, 1.5)          # margem maior que a espessura da borda (caixa fininha)
    sc = min(max(12.0, 90.0 / lado), 60.0)
    pl, pb, pr, pt = page.get_bbox()
    try:
        img = page.render(scale=sc, crop=(x0 - m - pl, y0 - m - pb, pr - x1 - m, pt - y1 - m)).to_numpy()
    except Exception:
        return True
    papel = (img[:, :, :3].min(2) > 200).astype(np.uint8)
    H, W = papel.shape
    if uniao:
        n, lab, st, _ = cv2.connectedComponentsWithStats(papel, connectivity=4)
        borda = set(np.unique(lab[0])) | set(np.unique(lab[-1])) | set(np.unique(lab[:, 0])) | \
            set(np.unique(lab[:, -1]))
        partes = [i for i in range(1, n) if i not in borda and st[i, cv2.CC_STAT_AREA] >= 0.03 * H * W]
        if not partes:
            return False
        mask = np.isin(lab, partes).astype(np.uint8)
        cs, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        c = cv2.convexHull(np.vstack(cs))      # contorno de fora (por cima da divisória / da linha)
        bx, by, bw, bh = cv2.boundingRect(c)
        cheio = np.zeros((bh, bw), np.uint8)
        cv2.drawContours(cheio, [c - [bx, by]], -1, 1, thickness=-1)
        # só a pontinha do canto (~0,6 pt): canto vivo fica cheio; arredondado fica vazio
        k = max(2, int(round(min(sc * 0.6, 0.1 * min(bw, bh)))))
        cantos = [cheio[:k, :k].mean(), cheio[:k, -k:].mean(), cheio[-k:, :k].mean(), cheio[-k:, -k:].mean()]
        if DEBUG_CANTOS:
            print("   cantos (pilha)", [round(float(x), 2) for x in cantos])
        return sum(x < 0.85 for x in cantos) >= 3
    n, lab = cv2.connectedComponents(papel, connectivity=4)
    cy, cx = H // 2, W // 2
    reg = lab[cy, cx]
    if reg == 0:
        # o centro caiu numa letra (caixa justa no texto: "CAVA C/ PERFURATRIZ"):
        # olha o miolo inteiro, por cima das letras
        return canto_arredondado(page, bbox, uniao=True)
    mask = (lab == reg).astype(np.uint8)
    if mask[0].any() or mask[-1].any() or mask[:, 0].any() or mask[:, -1].any():
        return True                                   # não fechou (balão cortado): não decide
    cs, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    bx, by, bw, bh = cv2.boundingRect(max(cs, key=cv2.contourArea))
    cheio = np.zeros((bh, bw), np.uint8)
    cv2.drawContours(cheio, [max(cs, key=cv2.contourArea) - [bx, by]], -1, 1, thickness=-1)
    k = max(3, int(round(0.1 * min(bw, bh))))
    cantos = [cheio[:k, :k].mean(), cheio[:k, -k:].mean(), cheio[-k:, :k].mean(), cheio[-k:, -k:].mean()]
    if DEBUG_CANTOS:
        print("   cantos", [round(c, 2) for c in cantos])
    if sum(c < 0.85 for c in cantos) >= 3:
        return True
    # balão grande com arredondado pequeno: olha só a pontinha do canto (~0,6 pt)
    kp = max(2, int(round(min(sc * 0.35, 0.1 * min(bw, bh)))))
    ponta = [cheio[:kp, :kp].mean(), cheio[:kp, -kp:].mean(), cheio[-kp:, :kp].mean(), cheio[-kp:, -kp:].mean()]
    if DEBUG_CANTOS:
        print("   pontas", [round(c, 2) for c in ponta])
    return sum(c < 0.7 for c in ponta) >= 3
# metros no balão: "45M", "16,5M" (com decimal)
RE_METROS = re.compile(r"(?<![\w.,/-])(\d{1,4}(?:[.,]\d{1,2})?)\s?[mM](?!\w)")


def _num_metros(txt):
    """'16,5' -> 16.5; '45' -> 45 (inteiro quando não tem decimal)"""
    v = float(str(txt).replace(",", "."))
    return int(v) if v == int(v) else v


def comprimentos_em_texto(chars, usados, area):
    """Rótulos tipo '45m' escritos como texto do PDF, fora dos balões."""
    x0, y0, x1, y1 = area
    livres = [c for c in chars if id(c) not in usados
              and c["l"] >= x0 and c["r"] <= x1 and c["b"] >= y0 and c["t"] <= y1]
    tokens, atual = [], []
    for c in livres:
        if atual:
            p = atual[-1]
            tam = max(p["t"] - p["b"], p["r"] - p["l"], 1e-3)
            gap = max(c["l"] - p["r"], p["l"] - c["r"], c["b"] - p["t"], p["b"] - c["t"], 0)
            outra_pal = c.get("pal") is not None and p.get("pal") is not None and c["pal"] != p["pal"]
            if c["esp"] or gap > tam * 0.8 or outra_pal:
                tokens.append(atual)
                atual = []
        atual.append(c)
    if atual:
        tokens.append(atual)
    caixas = [(min(c["l"] for c in t), min(c["b"] for c in t), max(c["r"] for c in t), max(c["t"] for c in t))
              for t in tokens]
    achados = []
    for k, tk_ in enumerate(tokens):
        txt = montar_texto(tk_).replace(" ", "")
        if not RE_COMPRIMENTO.match(txt):
            continue
        bb = caixas[k]
        alt = max(min(bb[2] - bb[0], bb[3] - bb[1]), 0.5)
        # outra palavra colada na mesma linha (ex.: "10M RAMAL"): é legenda de
        # outra coisa, não o comprimento de um balão
        frase = False
        grupo_k = tk_[0].get("pal")
        for j, ob in enumerate(caixas):
            if j == k or RE_COMPRIMENTO.match(montar_texto(tokens[j]).replace(" ", "")):
                continue
            grupo_j = tokens[j][0].get("pal")
            if grupo_k is not None and grupo_j is not None and grupo_k[:-1] != grupo_j[:-1]:
                continue                 # letras desenhadas de outro texto (outro desenho)
            ang = round(math.degrees(tk_[0]["ang"]) / 90) % 2
            if ang == 0:     # linha deitada
                mesma = min(bb[3], ob[3]) - max(bb[1], ob[1]) > 0.4 * alt
                vao = max(ob[0] - bb[2], bb[0] - ob[2])
            else:            # linha em pé
                mesma = min(bb[2], ob[2]) - max(bb[0], ob[0]) > 0.4 * alt
                vao = max(ob[1] - bb[3], bb[1] - ob[3])
            if mesma and vao < 1.5 * alt:
                frase = True
                break
        if not frase:
            achados.append({"texto": txt, "bbox_pdf": bb})
    return achados


def _desfaz_giro(u, v, W, H, giro):
    """Ponto (u, v) na imagem girada -> ponto na imagem original (W x H)."""
    if giro == 90:                       # foi girada 90° anti-horário
        return W - 1 - v, u
    if giro == 270:                      # foi girada 90° horário
        return v, H - 1 - u
    if giro == 180:
        return W - 1 - u, H - 1 - v
    return u, v


def comprimentos_por_ocr(page_fino, baloes, area):
    """
    Rótulos tipo '45m' que foram DESENHADOS no PDF (o CAD exporta como linhas,
    não como texto). Em volta de cada balão, renderiza o desenho em alta
    resolução, apaga os balões e lê com OCR procurando 'número + m'.
    """
    if not baloes or page_fino is None:
        return []
    pl, pb, pr, pt = page_fino.get_bbox()
    ax0, ay0, ax1, ay1 = area
    giros = {0: None, 90: cv2.ROTATE_90_COUNTERCLOCKWISE,
             180: cv2.ROTATE_180, 270: cv2.ROTATE_90_CLOCKWISE}
    achados = []
    for b in baloes:
        if RE_METROS.search(" ".join([b["texto"]] + b.get("complementos", []))):
            continue                                # o comprimento já está dentro do balão
        bx0, by0, bx1, by1 = b["bbox_pdf"]
        lado = min(bx1 - bx0, by1 - by0)
        e = max(lado * 2.0, b["alt"] * 6)           # faixa de busca em volta do balão
        cx0, cy0 = max(bx0 - e, ax0, pl), max(by0 - e, ay0, pb)
        cx1, cy1 = min(bx1 + e, ax1, pr), min(by1 + e, ay1, pt)
        if cx1 - cx0 < 1 or cy1 - cy0 < 1:
            continue                                 # balão fora da área: nada para ler
        esc = max(4.0, 30.0 / max(b["alt"], 0.5))  # letra do balão com ~30 px
        esc = min(esc, 4000.0 / max(cx1 - cx0, cy1 - cy0))
        try:
            bmp = page_fino.render(scale=esc, crop=(cx0 - pl, cy0 - pb, pr - cx1, pt - cy1))
            cinza = cv2.cvtColor(np.ascontiguousarray(bmp.to_numpy()[:, :, :3]), cv2.COLOR_RGB2GRAY)
            bmp.close()                          # libera a imagem grande logo (memória)
            del bmp
        except Exception:
            continue
        _, bw = cv2.threshold(cinza, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        H, W = bw.shape
        # apaga os balões (borda incluída) para não confundir o OCR
        borda = max(2, int(esc * 0.8))
        for o in baloes:
            ox0, oy0, ox1, oy1 = o["bbox_pdf"]
            u0, v0 = int((ox0 - cx0) * esc) - borda, int((cy1 - oy1) * esc) - borda
            u1, v1 = int((ox1 - cx0) * esc) + borda, int((cy1 - oy0) * esc) + borda
            if u1 > 0 and v1 > 0 and u0 < W and v0 < H:
                bw[max(v0, 0):max(v1, 0), max(u0, 0):max(u1, 0)] = 255
        # fica só com o que tem tamanho de letra (ruas e linhas da rede somem)
        alt_px = b["alt"] * esc
        n, lab, st, _ = cv2.connectedComponentsWithStats(255 - bw, connectivity=8)
        manter = np.zeros(n, bool)
        for k in range(1, n):
            maior = max(st[k, 2], st[k, 3])
            manter[k] = alt_px * 0.5 <= maior <= alt_px * 5
        bw = np.where(manter[lab], 0, 255).astype(np.uint8)
        g = b["ang"]
        im = bw if giros[g] is None else cv2.rotate(bw, giros[g])
        # junta as letras em "palavras" e lê cada palavra separadamente
        Hr, Wr = im.shape
        tinta_r = (im == 0).astype(np.uint8)
        kx, ky = max(3, int(alt_px * 1.2)), max(3, int(alt_px * 0.3))
        m, _, gst, _ = cv2.connectedComponentsWithStats(
            cv2.dilate(tinta_r, np.ones((ky, kx), np.uint8)), connectivity=8)
        for j in range(1, m):
            u, v, w, h, _ = gst[j]
            u, v = u + kx // 2, v + ky // 2
            w, h = w - kx + 1, h - ky + 1
            if w <= 0 or h <= 0 or not (h * 1.1 <= w <= h * 5):
                continue                            # "45m" é mais largo que alto
            palavra = im[max(v, 0):v + h, max(u, 0):u + w]
            # traço solto encostado (cerca, poste) separado por um vão grande: fica de fora;
            # vale o pedaço que termina no "m"
            cols = (palavra == 0).any(0)
            lin_ = np.nonzero((palavra == 0).any(1))[0]
            hh = (lin_[-1] - lin_[0] + 1) if len(lin_) else h
            corte, k_ = 0, 0
            while k_ < len(cols):
                if not cols[k_]:
                    k2 = k_
                    while k2 < len(cols) and not cols[k2]:
                        k2 += 1
                    lin_d = np.nonzero((palavra[:, k2:] == 0).any(1))[0] if k2 < len(cols) else []
                    hh = (lin_d[-1] - lin_d[0] + 1) if len(lin_d) else hh
                    if 0 < k_ and k2 < len(cols) and (k2 - k_) > 0.45 * hh:
                        corte = k2
                    k_ = k2
                else:
                    k_ += 1
            if corte:
                palavra = palavra[:, corte:]
                u, w = u + corte, w - corte
            txt = _ler_comprimento(palavra)
            if txt is None:
                continue
            pts = [_desfaz_giro(uu, vv, W, H, g) for uu, vv in ((u, v), (u + w, v + h))]
            px0, px1 = sorted(p[0] for p in pts)
            py0, py1 = sorted(p[1] for p in pts)
            bb = (cx0 + px0 / esc, cy1 - py1 / esc, cx0 + px1 / esc, cy1 - py0 / esc)
            cx, cy = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2
            if any(abs(cx - (r["bbox_pdf"][0] + r["bbox_pdf"][2]) / 2) < b["alt"] * 2 and
                   abs(cy - (r["bbox_pdf"][1] + r["bbox_pdf"][3]) / 2) < b["alt"] * 2
                   for r in achados):
                continue                            # já lido a partir de outro balão
            achados.append({"texto": txt, "bbox_pdf": bb})
    return achados


def ligar_comprimentos(baloes, rotulos):
    """Cada rótulo de comprimento vai para o balão mais próximo."""
    for r in rotulos:
        rx0, ry0, rx1, ry1 = r["bbox_pdf"]
        alt = min(rx1 - rx0, ry1 - ry0)
        melhor = None
        for b in baloes:
            bx0, by0, bx1, by1 = b["bbox_pdf"]
            d = math.hypot(max(bx0 - rx1, rx0 - bx1, 0), max(by0 - ry1, ry0 - by1, 0))
            if melhor is None or d < melhor[0]:
                melhor = (d, b)
        if melhor and melhor[0] <= max(alt, melhor[1]["alt"]) * 4:
            b = melhor[1]
            b["comprimento"] = (b.get("comprimento", "") + " " + r["texto"]).strip()


_PALAVRAS_LEGENDA = ("COMPONENTE", "LEGENDA", "CONVENC", "ANOTAC", "SIMBOLOGIA", "DEPARTAMENTO",
                     "NUMERODANOTA", "FAIXADEDOMINIO", "SOLICITANTE", "CODIFICACAO", "TIPODOCONDUTOR")


def perto_de_legenda(b, chars, raio=45.0):
    """Balão com palavras de legenda/carimbo dentro ou em volta (exemplo de balão da legenda)."""
    x0, y0, x1, y1 = b["bbox_pdf"]
    proprios = {id(c) for c in b.get("chars", [])}
    perto = [c for c in chars if id(c) not in proprios and
             x0 - raio <= (c["l"] + c["r"]) / 2 <= x1 + raio and y0 - raio <= (c["b"] + c["t"]) / 2 <= y1 + raio]
    txt = chave_nome(b.get("texto", "") + " " + montar_texto(perto) if perto else b.get("texto", ""))
    return any(p in txt for p in _PALAVRAS_LEGENDA)


def caixas_arredondadas(caminhos):
    """Balões desenhados como retângulo de canto arredondado (vetor): [(x0,y0,x1,y1, divisorias_y)].
    Acha pares de lados deitados (cima/baixo) e em pé (esquerda/direita) recuados pelo raio
    do canto, com o arco do canto ligando os dois. Uma linha cortando o balão não atrapalha."""
    segs = []
    for i, fill, stroke, subs in caminhos:
        if not stroke:
            continue
        for s in subs:
            for k in range(len(s) - 1):
                segs.append((s[k][0], s[k][1], s[k + 1][0], s[k + 1][1]))
    if not segs:
        return []
    S = np.array(segs, float)
    dx, dy = S[:, 2] - S[:, 0], S[:, 3] - S[:, 1]
    L = np.hypot(dx, dy)
    hor = (np.abs(dy) <= 0.03 * L) & (L >= 1.5)
    ver = (np.abs(dx) <= 0.03 * L) & (L >= 0.5)
    H = np.column_stack([np.minimum(S[hor, 0], S[hor, 2]), np.maximum(S[hor, 0], S[hor, 2]),
                         (S[hor, 1] + S[hor, 3]) / 2])                 # x0, x1, y
    V = np.column_stack([np.minimum(S[ver, 1], S[ver, 3]), np.maximum(S[ver, 1], S[ver, 3]),
                         (S[ver, 0] + S[ver, 2]) / 2])                 # y0, y1, x
    H = H[(H[:, 1] - H[:, 0]) <= 200]
    V = V[(V[:, 1] - V[:, 0]) <= 80]
    P = np.vstack([S[:, :2], S[:, 2:]])
    # lados deitados agrupados pelas pontas
    grupos = {}
    for k, (a, b, y) in enumerate(H):
        grupos.setdefault((int(a * 2), int(b * 2)), []).append(k)
    Vx = V[:, 2]
    saida = []
    vistos = set()
    for (ga, gb), ks in grupos.items():
        cand = []
        for da in (-1, 0, 1):
            for db in (-1, 0, 1):
                cand += grupos.get((ga + da, gb + db), [])
        cand = sorted(set(cand), key=lambda k: H[k, 2])
        for i in ks:
            for j in cand:
                if H[j, 2] <= H[i, 2]:
                    continue
                a, b, yb = H[i]
                yt = H[j, 2]
                hgt = yt - yb
                w = b - a
                if not (1.0 <= hgt <= 60) or abs(H[j, 0] - a) > 0.1 * w + 0.2 or abs(H[j, 1] - b) > 0.1 * w + 0.2:
                    continue
                lados = []
                for lado, xh in ((0, a), (1, b)):
                    # lado em pé recuado pelo raio: x = xh -/+ r, de yb + r até yt - r
                    sel = np.nonzero((np.abs(Vx - xh) <= 0.6 * hgt) & (V[:, 0] >= yb - 0.1) & (V[:, 1] <= yt + 0.1))[0]
                    melhor = None
                    for v in sel:
                        r = (xh - Vx[v]) if lado == 0 else (Vx[v] - xh)
                        if r < 0.08 * min(hgt, w) or r > 0.6 * hgt:
                            continue
                        r2, r3 = V[v, 0] - yb, yt - V[v, 1]
                        tol = max(0.25, 0.35 * r)
                        if abs(r2 - r) <= tol and abs(r3 - r) <= tol:
                            melhor = (v, r)
                            break
                    if melhor is None:
                        break
                    lados.append(melhor)
                if len(lados) < 2:
                    continue
                r = (lados[0][1] + lados[1][1]) / 2
                X0, X1 = Vx[lados[0][0]], Vx[lados[1][0]]
                # arcos dos cantos: algum ponto no quadradinho de cada canto
                ok = True
                for cx, cy in ((X0, yb), (X1, yb), (X0, yt), (X1, yt)):
                    qx0, qx1 = min(cx, a if cx == X0 else b), max(cx, a if cx == X0 else b)
                    qy0, qy1 = (yb, yb + r) if cy == yb else (yt - r, yt)
                    m = ((P[:, 0] > qx0 + 0.15 * r) & (P[:, 0] < qx1 - 0.15 * r) &
                         (P[:, 1] > qy0 + 0.15 * r) & (P[:, 1] < qy1 - 0.15 * r))
                    if not m.any():
                        ok = False
                        break
                if not ok:
                    continue
                chave = (round(X0, 1), round(yb, 1), round(X1, 1), round(yt, 1))
                if chave in vistos:
                    continue
                vistos.add(chave)
                # divisórias internas (balão empilhado)
                # (só linha que fica dentro do balão; rua que atravessa não é divisória)
                divs = [H[k, 2] for k in range(len(H)) if yb + 0.15 * hgt < H[k, 2] < yt - 0.15 * hgt
                        and X0 - 0.3 <= H[k, 0] <= X0 + 0.2 * w and X1 - 0.2 * w <= H[k, 1] <= X1 + 0.3]
                saida.append((X0, yb, X1, yt, sorted(set(round(d, 2) for d in divs))))
    return saida


_CACHE_SEGS = {}


def _segs_retos(page):
    """todos os traços (x0,y0,x1,y1) da página (com cache)"""
    k = id(page)
    if k not in _CACHE_SEGS:
        segs = []
        for i, fill, stroke, subs in coletar_caminhos(page):
            if stroke:
                segs += [(s[j][0], s[j][1], s[j + 1][0], s[j + 1][1]) for s in subs for j in range(len(s) - 1)]
        _CACHE_SEGS.clear()
        _CACHE_SEGS[k] = np.array(segs, float).reshape(-1, 4)
    return _CACHE_SEGS[k]


def entre_duas_linhas(bb, S):
    """A caixa está entre duas retas paralelas que passam bem além dela dos dois lados
    (cima e baixo, ou esquerda e direita)?"""
    if not len(S):
        return False
    x0, y0, x1, y1 = bb
    w, h = x1 - x0, y1 - y0
    for eixo in (0, 1):
        if eixo == 0:     # retas deitadas na borda de cima e de baixo
            a0, a1, b0, b1, lado = x0, x1, y0, y1, h
            X0, Y0, X1, Y1 = S[:, 0], S[:, 1], S[:, 2], S[:, 3]
        else:             # retas em pé na esquerda e na direita
            a0, a1, b0, b1, lado = y0, y1, x0, x1, w
            X0, Y0, X1, Y1 = S[:, 1], S[:, 0], S[:, 3], S[:, 2]
        comp = a1 - a0
        lo, hi = np.minimum(X0, X1), np.maximum(X0, X1)
        inc = np.abs(Y1 - Y0) <= 0.02 * np.maximum(hi - lo, 1e-6)
        passa = inc & (lo <= a0 - 0.1) & (hi >= a1 + 0.1) & ((hi - lo) >= 1.5 * comp)
        ym = (Y0 + Y1) / 2
        tol = max(0.5 * lado, 0.6)          # (borda da região fica dentro do traço grosso)
        em_baixo = passa & (np.abs(ym - b0) <= tol)
        em_cima = passa & (np.abs(ym - b1) <= tol)
        if em_baixo.any() and em_cima.any():
            return True
    return False


def _sobrepoe(a, b, frac=0.5):
    ix = min(a[2], b[2]) - max(a[0], b[0])
    iy = min(a[3], b[3]) - max(a[1], b[1])
    if ix <= 0 or iy <= 0:
        return False
    return ix * iy >= frac * min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))


def completar_com_vetor(baloes, caixas, chars):
    """Balões que a imagem não separou (rua, cerca ou rede passando por cima do balão)
    mas que estão desenhados como retângulo de canto arredondado no PDF. Só entra se o
    projeto desenha os balões assim (a maioria dos balões achados bate com uma caixa)."""
    if not caixas or not baloes:
        return baloes
    bate = sum(1 for b in baloes if any(_sobrepoe(b["bbox_pdf"], c[:4]) for c in caixas))
    if bate < max(3, 0.8 * len(baloes)):
        return baloes
    novos = []
    for X0, Y0, X1, Y1, divs in caixas:
        if any(_sobrepoe(b["bbox_pdf"], (X0, Y0, X1, Y1)) for b in baloes + novos):
            continue
        cs = [c for c in chars if X0 <= (c["l"] + c["r"]) / 2 <= X1 and Y0 <= (c["b"] + c["t"]) / 2 <= Y1]
        if len(cs) < 2:
            continue
        # caixa dentro de outra caixa com texto (legenda, quadro) não é balão
        cortes = [Y0] + [d for d in divs] + [Y1]
        partes = []
        for k in range(len(cortes) - 1):
            ya, yb_ = cortes[k], cortes[k + 1]
            cp = [c for c in cs if ya <= (c["b"] + c["t"]) / 2 <= yb_]
            if len(cp) >= 1:
                partes.append(((X0, ya, X1, yb_), cp))
        for bb, cp in partes:
            ang = angulo_texto(cp)
            horiz = ang in (0, 180)
            alt = float(np.median([(c["t"] - c["b"]) if horiz else (c["r"] - c["l"]) for c in cp]))
            novos.append({"texto": montar_texto(cp), "bbox_pdf": bb, "chars": cp, "arredondado": True,
                          "ang": ang, "alt": alt, "comprimento": "", "vetor": True})
    return baloes + novos


RE_CABO_TEXTO = re.compile(r"^\d+\s*[xX#]\s*[A-Za-z0-9][A-Za-z0-9/,.\-²]*\d[A-Za-z0-9/,.\-²]*$")
RE_POSTE_ESF_ALT = re.compile(r"^\d{3,4}\s*/\s*\d{1,2}[A-Z]?$")


RE_TEXTO_CERCA = re.compile(r"CE[RP]CA|F\s*[IlÍí1]\s*[O0]\s*S\b")
# código de estrutura/material sozinho numa caixa: CE3-CE3, CE2, N3, PR, N3-CF, AR-CE
RE_COD_ESTRUT = re.compile(r"^[A-Z]{1,4}\d{0,2}(\s*-\s*[A-Z]{1,4}\d{0,2}){0,2}$")


def _parece_balao_reto(b):
    """Caixa reta com cara de balão: texto curto (poucas linhas) e com algum número."""
    t = (b.get("texto") or "").strip()
    if RE_TEXTO_CERCA.search(t.upper()):
        return False                           # anotação da cerca (SEC./ATER. DE CERCA, N FIOS)
    letras = [ch for ch in t if ch.isalpha()]
    # balão é código (maiúsculas, números); texto de carimbo tem ":" e minúsculas (o cabo,
    # "3#185mm²", é tratado à parte)
    if ":" in t or (letras and sum(ch.isupper() for ch in letras) < 0.6 * len(letras)):
        return False
    if any(ch.islower() for ch in letras) and not RE_CABO_TEXTO.match(t.replace("\n", " ").strip()):
        return False
    return 0 < len(t) <= 80 and t.count("\n") <= 5 and any(ch.isdigit() for ch in t)


def detectar_baloes(page, area_pdf, chars=None, page_desenho=None, page_fino=None, dpi=300, fechar_falhas=1,
                    folga_max=40.0, compacidade_min=0.80, limiar=30,
                    min_caracteres=2, max_tinta_extra=0.03, tam_max=60,
                    retangularidade_min=0.75, juntar=True, comprimentos=True,
                    ocr_comprimentos=True, poligono=None, so_arredondados=False, poligono_folga=0.0,
                    retos=None):
    """
    page         : página pypdfium2 (com rotação 0)
    page_desenho : a mesma página aberta de novo e com remover_textos() aplicado
                   (se None, o texto é apagado do mapa de tinta pelas caixas)
    area_pdf  : (x0, y0, x1, y1) em coordenadas do PDF (y para cima)
    poligono  : delimitação do projeto [(x, y), ...]; só ficam os balões de dentro
    Retorna lista de dicts: {"texto", "bbox_pdf"}.
    """
    if chars is None:
        chars = ler_caracteres(page)
    pl, pb, pr, pt = page.get_bbox()
    x0, y0, x1, y1 = area_pdf
    x0, x1 = max(min(x0, x1), pl), min(max(x0, x1), pr)
    y0, y1 = max(min(y0, y1), pb), min(max(y0, y1), pt)
    if x1 - x0 < 2 or y1 - y0 < 2:
        return []

    escala = dpi / 72.0
    max_px = 60e6                                   # protege a memória
    if (x1 - x0) * (y1 - y0) * escala ** 2 > max_px:
        escala = math.sqrt(max_px / ((x1 - x0) * (y1 - y0)))

    img = (page_desenho or page).render(scale=escala,
                      crop=(x0 - pl, y0 - pb, pr - x1, pt - y1)).to_numpy()
    # "tinta" = onde a cor muda (borda de qualquer cor, sobre fundo branco ou
    # sobre balão preenchido). Assim funciona com balão branco, verde, cinza...
    grad = cv2.morphologyEx(np.ascontiguousarray(img[:, :, :3]), cv2.MORPH_GRADIENT,
                            np.ones((2, 2), np.uint8)).max(axis=2)
    tinta = (grad > limiar).astype(np.uint8)
    H, W = tinta.shape

    def pdf2px(x, y):
        return (x - x0) * escala, (y1 - y) * escala

    # caixas (em pixels) dos caracteres que estão dentro da seleção
    caixas = []
    for c in chars:
        if c["r"] < x0 or c["l"] > x1 or c["b"] < y0 or c["t"] > y1:
            continue
        a, b_ = pdf2px(c["l"], c["t"])
        d, e = pdf2px(c["r"], c["b"])
        ia, ib = max(int(a) - 1, 0), max(int(b_) - 1, 0)
        id_, ie = min(int(math.ceil(d)) + 1, W - 1), min(int(math.ceil(e)) + 1, H - 1)
        if id_ > ia and ie > ib:
            caixas.append((c, ia, ib, id_, ie))

    if page_desenho is None:     # plano B: apaga o texto pelas caixas das letras
        for _, ia, ib, id_, ie in caixas:
            tinta[ib:ie + 1, ia:id_ + 1] = 0

    if fechar_falhas > 0:                           # fecha traços tracejados/quebrados
        k = cv2.getStructuringElement(cv2.MORPH_RECT,
                                      (2 * fechar_falhas + 1, 2 * fechar_falhas + 1))
        tinta = cv2.morphologyEx(tinta, cv2.MORPH_CLOSE, k)
    papel = (1 - tinta).astype(np.uint8)
    n, rot = cv2.connectedComponents(papel, connectivity=4)

    # regiões que tocam a borda da seleção não são fechadas
    borda = set(np.unique(np.concatenate([rot[0], rot[-1], rot[:, 0], rot[:, -1]])).tolist())

    # cada caractere pertence à região de papel onde está o seu centro
    lab_char = {}                                   # id(char) -> rótulo
    for c, ia, ib, id_, ie in caixas:
        reg = rot[ib:ie + 1, ia:id_ + 1]
        reg = reg[reg > 0]
        if reg.size:
            lab_char[id(c)] = int(np.bincount(reg).argmax())

    # Uma linha (rua, rede) pode passar POR CIMA de um balão e dividi-lo.
    # Se letras vizinhas da mesma palavra caíram em regiões diferentes,
    # essas regiões são unidas e avaliadas como uma só.
    pai = {}

    def raiz(x):
        while pai.setdefault(x, x) != x:
            pai[x] = pai[pai[x]]
            x = pai[x]
        return x

    for lab in set(lab_char.values()):
        raiz(lab)
    for c1, c2 in zip(chars, chars[1:]):
        l1, l2 = lab_char.get(id(c1)), lab_char.get(id(c2))
        if l1 is None or l2 is None or l1 == l2 or c2["esp"]:
            continue
        tam = max(c1["t"] - c1["b"], c1["r"] - c1["l"], 1e-3)
        gap = max(c2["l"] - c1["r"], c1["l"] - c2["r"], c2["b"] - c1["t"], c1["b"] - c2["t"], 0)
        if gap < tam * 0.8:
            pai[raiz(l1)] = raiz(l2)

    grupos = {}
    for c in chars:
        lab = lab_char.get(id(c))
        if lab is not None:
            g = grupos.setdefault(raiz(lab), {"labs": set(), "cs": []})
            g["labs"].add(lab)
            g["cs"].append(c)

    baloes = []
    for g in grupos.values():
        cs, labs = g["cs"], g["labs"]
        if labs & borda or len(cs) < min_caracteres:
            continue                                # região aberta (vaza da seleção)
        alt_txt = float(np.median([max(c["r"] - c["l"], c["t"] - c["b"])
                                   for c in cs])) * escala
        mask = np.isin(rot, list(labs)).astype(np.uint8)
        unido = len(labs) > 1
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if unido:
            # pedaços do mesmo balão separados por uma linha que passa por cima:
            # o balão é o contorno que envolve todos os pedaços
            cnt = cv2.convexHull(np.vstack(cnts))
        else:
            cnt = max(cnts, key=cv2.contourArea)
        area = cv2.contourArea(cnt)
        hull = cv2.contourArea(cv2.convexHull(cnt))
        if area <= 0 or hull <= 0:
            continue
        compacidade = area / hull                   # 1 = forma convexa (retângulo, oval)
        tl = min(c["l"] for c in cs); tr = max(c["r"] for c in cs)
        tb = min(c["b"] for c in cs); tt = max(c["t"] for c in cs)
        area_txt = max((tr - tl) * (tt - tb), 1e-6) * escala ** 2
        folga = area / area_txt                     # quão "justo" o contorno é ao texto
        bx, by, bw, bh = cv2.boundingRect(cnt)
        grande = max(bw, bh) > tam_max * max(alt_txt, 1)     # moldura da folha, quarteirão...
        # balão = retângulo (arredondado ou não) ou oval alinhado ao texto;
        # "bolsões" entre linhas que se cruzam costumam ser triângulos/losangos
        retangularidade = area / max(bw * bh, 1)
        if DEBUG_CANTOS:
            print("grupo", montar_texto(cs)[:25].replace("\n", " "), "comp %.2f folga %.1f grande %s ret %.2f unido %s"
                  % (compacidade, folga, grande, retangularidade, unido))
        if (compacidade < compacidade_min or folga > folga_max or grande
                or retangularidade < retangularidade_min):
            continue
        if not unido:
            # dentro de um balão só existe texto; num quarteirão/lote há postes,
            # linhas de rede etc. Mede a "tinta" interna que não é texto.
            cheio = np.zeros((bh, bw), np.uint8)
            cv2.drawContours(cheio, [cnt - [bx, by]], -1, 1, thickness=-1)
            cheio = cv2.erode(cheio, np.ones((3, 3), np.uint8))   # ignora a própria borda
            sobra = cheio & tinta[by:by + bh, bx:bx + bw]
            if sobra.sum() > max_tinta_extra * cheio.sum():
                continue
        bbox_pdf = (x0 + bx / escala, y1 - (by + bh) / escala,
                    x0 + (bx + bw) / escala, y1 - by / escala)
        ang_b = angulo_texto(cs)
        horizontal = ang_b in (0, 180)
        alt_pt = float(np.median([(c["t"] - c["b"]) if horizontal else (c["r"] - c["l"])
                                  for c in cs]))        # altura das letras, em pontos
        arred = canto_arredondado(page_desenho or page, bbox_pdf, uniao=unido)
        if DEBUG_CANTOS:
            print("cantos", montar_texto(cs)[:20].replace("\n", " "), arred)
        baloes.append({"texto": montar_texto(cs), "bbox_pdf": bbox_pdf, "chars": cs, "arredondado": arred,
                       "ang": ang_b, "alt": alt_pt, "comprimento": ""})

    # balões que a imagem não separou (linha passando por cima): pelo desenho vetorial
    try:
        baloes = completar_com_vetor(baloes, caixas_arredondadas(coletar_caminhos(page)), chars)
    except Exception:
        pass
    # espaço entre duas linhas compridas (rua, rede) não é balão: as bordas de cima e de
    # baixo (ou dos lados) são retas que passam muito além da "caixa"
    try:
        baloes = [b for b in baloes if b.get("vetor") or not entre_duas_linhas(b["bbox_pdf"], _segs_retos(page))]
    except Exception:
        pass
    if poligono is not None and len(poligono) >= 3:     # só o que está dentro da delimitação
        pg = np.array(poligono, np.float32)
        def fica(b):
            d = cv2.pointPolygonTest(pg, ((b["bbox_pdf"][0] + b["bbox_pdf"][2]) / 2,
                                          (b["bbox_pdf"][1] + b["bbox_pdf"][3]) / 2), True)
            if d >= 0:
                return True
            if d < -poligono_folga:
                return False
            # fora da área, mas perto: não pode ser exemplo da legenda ("COMPONENTE INSTALADO"...)
            return not perto_de_legenda(b, chars)
        baloes = [b for b in baloes if fica(b)]
    if so_arredondados:
        # caixa retangular (canto vivo) sozinha não é balão; retângulos empilhados
        # (padrão de alguns projetos) continuam valendo
        pilhas = juntar_empilhados(baloes)
        em_pilha = set()
        for p in pilhas:
            # pilha só vale se o conjunto tiver canto arredondado (a caixa "P1" em cima de
            # um retângulo de texto não faz dele um balão)
            # e as caixas têm que ter a mesma largura (divisória de um balão só); a caixinha
            # do número do poste (V299295) em cima do balão é outra coisa
            larg = [faixas_no_texto(bb, p["ang"])[0] for bb in p.get("membros", [])]
            mesma = bool(larg) and min(l[1] - l[0] for l in larg) >= 0.85 * max(l[1] - l[0] for l in larg)
            if p.get("em_pilha") and mesma and canto_arredondado(page_desenho or page, p["bbox_pdf"], uniao=True):
                em_pilha.add(id(p["chars"][0]) if p["chars"] else None)
                em_pilha.update(id(c) for c in p["chars"])
        arred = [b for b in baloes if b.get("arredondado", True) or
                 any(id(c) in em_pilha for c in b["chars"])]
        # projeto fora do padrão: nenhum balão no formato habitual na folha -> vale o
        # balão em caixa quadrada (canto vivo), um material por linha, sem vírgula.
        # Ficam de fora as caixas da legenda e as de texto comprido.
        q_ = []
        if not arred:
            q_ = [b for b in baloes if not perto_de_legenda(b, chars) and _parece_balao_reto(b)]
        else:
            # folha com os dois tipos: vale também a caixa quadrada cuja primeira linha é o
            # poste no formato esforço/altura ("400/12", "1000/12") - o balão de poste
            # desses projetos; as outras caixas quadradas continuam de fora
            q_ = [b for b in baloes if not b.get("arredondado", True) and id(b) not in {id(x) for x in arred}
                  and not perto_de_legenda(b, chars) and _parece_balao_reto(b)
                  and RE_POSTE_ESF_ALT.match((b.get("texto") or "").strip().split("\n")[0].strip())]
        # caixa quadrada encostada em cima/embaixo de um balão de poste aceito, com a mesma
        # largura (pilha "400/12" | "N1"): faz parte do mesmo balão
        if q_:
            ids_q = {id(x) for x in q_}
            mudou = True
            while mudou:
                mudou = False
                for b in baloes:
                    if id(b) in ids_q or b.get("arredondado", True) or not (b.get("texto") or "").strip():
                        continue
                    x0, y0, x1, y1 = b["bbox_pdf"]
                    for q in list(q_):
                        a0, b0, a1, b1 = q["bbox_pdf"]
                        sob = min(x1, a1) - max(x0, a0)
                        larg = max(x1 - x0, a1 - a0)
                        enc = min(abs(y0 - b1), abs(b0 - y1))
                        if sob >= 0.85 * larg and enc <= 1.5:
                            q_.append(b)
                            ids_q.add(id(b))
                            mudou = True
                            break
        # balão quadrado só dentro da área do projeto (o carimbo e a legenda ficam de fora)
        if q_ and poligono is not None and len(poligono) >= 3:
            pg_q = np.array(poligono, np.float32)
            q_ = [b for b in q_ if cv2.pointPolygonTest(pg_q, ((b["bbox_pdf"][0] + b["bbox_pdf"][2]) / 2,
                                                                (b["bbox_pdf"][1] + b["bbox_pdf"][3]) / 2), False) >= 0]
        if len(q_) >= 2:
            for b in q_:
                b["quadrado"] = True
            arred = arred + q_
            if retos is not None:
                retos += q_
        baloes = arred
    if juntar:
        baloes = juntar_empilhados(baloes)
    else:
        baloes = [dict(b, complementos=[]) for b in baloes]
    if comprimentos and baloes:
        usados = {id(c) for b in baloes for c in b["chars"]}
        rotulos = comprimentos_em_texto(chars, usados, (x0, y0, x1, y1))
        if ocr_comprimentos:
            rotulos += comprimentos_por_ocr(page_fino, baloes, (x0, y0, x1, y1))
        ligar_comprimentos(baloes, rotulos)
    for b in baloes:
        if b.get("quadrado"):
            # balão quadrado (poste/estrutura): a metragem escrita perto é do vão do cabo
            b.pop("comprimento", None)
    for b in baloes:
        b["principal"] = b["texto"]                  # texto original (com as quebras de linha)
        txt = b["texto"].replace("\n", " ")
        if b["complementos"]:                        # balão de baixo entre parênteses
            txt += " (" + " | ".join(c.replace("\n", " ") for c in b["complementos"]) + ")"
        if b.get("comprimento"):                    # o comprimento entra junto com o balão
            txt += " " + b["comprimento"]
        b["texto"] = txt

    # ordena de cima para baixo / esquerda para direita (no PDF)
    baloes.sort(key=lambda b: (-round(b["bbox_pdf"][3]), b["bbox_pdf"][0]))
    return baloes
