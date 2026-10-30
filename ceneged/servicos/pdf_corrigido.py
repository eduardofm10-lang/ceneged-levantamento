"""Projeto em PDF com os balões corrigidos (na tela e no arquivo que sai com o relatório).

Parte do programa Levantamento de Materiais (Ceneged)."""

import math
import re
import numpy as np
import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c

from ceneged.comum.texto import _sem_acento
from ceneged.leitura_pdf.deteccao import angulo_texto

# ---------------------------------------------------------------------------
#  Projeto em PDF com os balões corrigidos: onde a pessoa mudou o texto de um balão
#  ("Corrigir texto") ou marcou um balão à mão, o texto antigo é coberto de branco e o
#  texto novo é escrito no lugar (mesma direção do texto original). Opcional: contorno
#  vermelho nos balões alterados. O PDF original não é mexido: sai uma cópia.
# ---------------------------------------------------------------------------
# larguras da fonte Helvetica (unidades de 1/1000 do tamanho), para caber o texto no balão
_LARG_HELV = dict(zip(
    " !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~",
    [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,
     556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556, 1015,
     667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778, 667, 778, 722, 667,
     611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556, 333,
     556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500,
     278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584]))


def largura_texto(txt, tam):
    """Largura (em pontos) do texto na fonte Helvetica de tamanho tam."""
    return sum(_LARG_HELV.get(_sem_acento(c) or c, 600) for c in txt) * tam / 1000.0


def _quebrar_linhas(txt, larg_max, tam):
    """Quebra nas vírgulas (e, se precisar, nos espaços) para caber na largura."""
    linhas = []
    for bloco in str(txt).split("\n"):
        partes = re.split(r"(?<=,)\s*", bloco.strip())
        atual = ""
        for p in partes:
            cand = (atual + " " + p).strip() if atual else p
            if not atual or largura_texto(cand, tam) <= larg_max:
                atual = cand
                continue
            linhas.append(atual)
            atual = p
        if atual:
            linhas.append(atual)
    out = []
    for l in linhas:                                   # linha ainda larga: quebra nos espaços
        if largura_texto(l, tam) <= larg_max:
            out.append(l)
            continue
        atual = ""
        for w in l.split(" "):
            cand = (atual + " " + w).strip()
            if atual and largura_texto(cand, tam) > larg_max:
                out.append(atual)
                atual = w
            else:
                atual = cand
        if atual:
            out.append(atual)
    return out or [""]


def _caixa_dos_chars(chars):
    if not chars:
        return None
    return (min(c["l"] for c in chars), min(c["b"] for c in chars),
            max(c["r"] for c in chars), max(c["t"] for c in chars))


def layout_balao_corrigido(b, texto=None):
    """Como escrever o texto novo dentro do balão. ->
    {"ang", "tam", "linhas": [(texto, largura, v_centro)], "centro": (x, y),
     "u": vetor da leitura, "v": vetor para cima, "branco": caixa a cobrir (x0, y0, x1, y1)}"""
    texto = texto if texto is not None else b.get("principal") or b.get("texto") or ""
    x0, y0, x1, y1 = b["bbox_pdf"]
    _ant = _caixa_dos_chars(b.get("chars") or [])
    if _ant:                                  # a caixa do balão às vezes fica menor que o texto
        x0, y0, x1, y1 = min(x0, _ant[0]), min(y0, _ant[1]), max(x1, _ant[2]), max(y1, _ant[3])
    ang = int(round(float(b.get("ang") or 0) / 90.0)) % 4 * 90
    t = math.radians(ang)                     # sentido do pdfium: 90 = lendo para baixo
    u = (math.cos(t), -math.sin(t))
    v = (math.sin(t), math.cos(t))
    W, H = (x1 - x0, y1 - y0) if ang in (0, 180) else (y1 - y0, x1 - x0)
    folga = 0.08 if b.get("arredondado") else 0.05       # balão redondo: fica longe dos cantos
    Wu, Hu = W * (1 - 2 * folga), H * (1 - 2 * folga * 0.8)
    alt = float(b.get("alt") or 0) or H / 3
    tam = max(min(alt / 0.72, H * 0.8), 0.3)            # alt = altura das letras maiúsculas
    while True:
        linhas = _quebrar_linhas(texto, Wu, tam)
        lh = tam * 1.15
        caber = max(largura_texto(l, tam) for l in linhas) <= Wu and len(linhas) * lh <= Hu
        if caber or tam <= 0.3:            # balões bem pequenos (projeto em escala grande)
            break
        tam *= 0.92
    lh = tam * 1.15
    topo = len(linhas) * lh / 2
    lins = [(l, largura_texto(l, tam), topo - i * lh - lh / 2) for i, l in enumerate(linhas)]
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    # caixa branca: o texto antigo + o bloco do texto novo (sem passar da borda do balão)
    bw = max(w for _, w, _ in lins) / 2 + tam * 0.25
    bh = topo + tam * 0.15
    cantos = [(cx + su * bw * u[0] + sv * bh * v[0], cy + su * bw * u[1] + sv * bh * v[1])
              for su in (-1, 1) for sv in (-1, 1)]
    xs, ys = [p[0] for p in cantos], [p[1] for p in cantos]
    caixa = [min(xs), min(ys), max(xs), max(ys)]
    antigo = _caixa_dos_chars(b.get("chars") or [])
    if antigo:
        # cobre as letras antigas inteiras (com uma folga pequena, proporcional ao tamanho delas):
        # a caixa do balão às vezes é um pouco menor que o texto, então não corta por ela
        pad = max(alt * 0.12, 0.05)
        caixa = [min(caixa[0], antigo[0] - pad), min(caixa[1], antigo[1] - pad),
                 max(caixa[2], antigo[2] + pad), max(caixa[3], antigo[3] + pad)]
        lim = alt * 0.35
        caixa = (max(caixa[0], x0 - lim), max(caixa[1], y0 - lim), min(caixa[2], x1 + lim), min(caixa[3], y1 + lim))
    else:
        m = min(x1 - x0, y1 - y0) * 0.04
        caixa = (max(caixa[0], x0 + m), max(caixa[1], y0 + m), min(caixa[2], x1 - m), min(caixa[3], y1 - m))
    return {"ang": ang, "tam": tam, "linhas": lins, "centro": (cx, cy), "u": u, "v": v, "branco": caixa}


def baloes_alterados(pg):
    """Balões da página com texto corrigido ou marcados à mão."""
    return [b for b in (pg.baloes or []) if b.get("corrigido") or b.get("manual")]


def _wide(txt):
    import ctypes
    buf = ctypes.create_string_buffer((txt + "\0").encode("utf-16-le"))
    return buf, ctypes.cast(buf, ctypes.POINTER(ctypes.c_ushort))


def _ret_pdf(doc, page, caixa, preencher=None, contorno=None, larg=0.6):
    x0, y0, x1, y1 = caixa
    obj = pdfium_c.FPDFPageObj_CreateNewRect(x0, y0, x1 - x0, y1 - y0)
    if preencher:
        pdfium_c.FPDFPageObj_SetFillColor(obj, *preencher, 255)
    if contorno:
        pdfium_c.FPDFPageObj_SetStrokeColor(obj, *contorno, 255)
        pdfium_c.FPDFPageObj_SetStrokeWidth(obj, larg)
    pdfium_c.FPDFPath_SetDrawMode(obj, pdfium_c.FPDF_FILLMODE_WINDING if preencher else 0, bool(contorno))
    pdfium_c.FPDFPage_InsertObject(page.raw, obj)


def _texto_pdf(doc, page, texto, tam, matriz):
    obj = pdfium_c.FPDFPageObj_NewTextObj(doc.raw, b"Helvetica", float(tam))
    buf, ptr = _wide(texto)
    pdfium_c.FPDFText_SetText(obj, ptr)
    pdfium_c.FPDFPageObj_SetFillColor(obj, 0, 0, 0, 255)
    pdfium_c.FPDFPageObj_Transform(obj, *matriz)
    pdfium_c.FPDFPage_InsertObject(page.raw, obj)


def _corrigir_pagina(doc, page, pg, destacar=True):
    """Escreve na página do PDF os textos novos dos balões alterados. -> nº de balões."""
    alterados = baloes_alterados(pg) if pg.baloes is not None else []
    for b in alterados:
        chars = b.get("chars") or []
        if b.get("manual") and not chars:          # marcado à mão: letras que estão dentro
            x0, y0, x1, y1 = b["bbox_pdf"]
            chars = [c for c in pg.chars or [] if x0 <= (c["l"] + c["r"]) / 2 <= x1 and
                     y0 <= (c["b"] + c["t"]) / 2 <= y1]
            if chars:
                b = dict(b, chars=chars, ang=angulo_texto(chars),
                         alt=float(np.median([c["t"] - c["b"] for c in chars])))
        lay = layout_balao_corrigido(b)
        _ret_pdf(doc, page, lay["branco"], preencher=(255, 255, 255))
        if b.get("manual") and not chars:            # balão novo onde não havia balão
            _ret_pdf(doc, page, b["bbox_pdf"], contorno=(0, 0, 0), larg=0.5)
        (ux, uy), (vx, vy) = lay["u"], lay["v"]
        cx, cy = lay["centro"]
        for txt, w, vc in lay["linhas"]:
            us, vs = -w / 2, vc - lay["tam"] * 0.35          # começo da linha, na base das letras
            e, f = cx + us * ux + vs * vx, cy + us * uy + vs * vy
            _texto_pdf(doc, page, txt, lay["tam"], (ux, uy, vx, vy, e, f))
        if destacar:                                 # contorno vermelho: proporcional ao balão
            x0, y0, x1, y1 = b["bbox_pdf"]
            h_ = min(x1 - x0, y1 - y0)
            d = min(max(h_ * 0.35, 0.4), 3.0)
            _ret_pdf(doc, page, (x0 - d, y0 - d, x1 + d, y1 + d), contorno=(227, 28, 36),
                     larg=min(max(h_ * 0.08, 0.12), 1.0))
    if alterados:
        page.gen_content()
    return len(alterados)


def salvar_pdf_corrigido(arq, destino, destacar=True):
    """Cópia do PDF do projeto com os textos novos nos balões alterados. -> nº de balões."""
    doc = pdfium.PdfDocument(arq.caminho)
    total = 0
    try:
        for i, pg in sorted(arq._paginas.items()):
            total += _corrigir_pagina(doc, doc[i], pg, destacar)
        doc.save(destino)
    finally:
        doc.close()
    return total


def imagem_pagina_corrigida(arq, i, pg, escala):
    """Imagem da página já com os textos corrigidos (para a tela). None se nada mudou."""
    if not (pg.baloes and baloes_alterados(pg)):
        return None
    doc = pdfium.PdfDocument(arq.caminho)
    try:
        page = doc[i]
        _corrigir_pagina(doc, page, pg, destacar=True)
        return page.render(scale=escala).to_pil()
    finally:
        doc.close()
