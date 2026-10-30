"""Arquivo e Página: orquestra a leitura de um PDF e gera o relatório.

Parte do programa Levantamento de Materiais (Ceneged)."""

import math
import os
import re
import cv2
import numpy as np
import pypdfium2 as pdfium

from ceneged.comum.texto import (chave_nome, info_poste)
from ceneged.leitura_pdf.vetores import (TextoTraco, caixas_vetoriais, coletar_caminhos,
    contar_pilhas, pilhas_de_caixas, retangulos_de_linhas)
from ceneged.leitura_pdf.deteccao import (RE_CABO_TEXTO, RE_COD_ESTRUT, RE_METROS,
    RE_POSTE_ESF_ALT, RE_TEXTO_CERCA, afinar_tracos, comprimentos_em_texto, detectar_baloes,
    ler_caracteres, montar_texto, perto_de_legenda, remover_imagens, remover_textos)
from ceneged.leitura_pdf.texto_contornos import (cor_do_objeto, ler_caixa_raster,
    ler_texto_de_traco, ler_texto_vetorial, remover_objetos)
from ceneged.leitura_pdf.texto_traco import (estimar_inclinacao_traco, ler_linha_traco)
from ceneged.leitura_pdf.rede import (RE_FIM_DE_REDE, Rede, _cabo_de_cada_linha,
    _chamada_vertices, _dist_seg, _familia, _matiz, analisar_poste, ancoras_de_cabo,
    cabos_de_cada_lado, distribuir_comprimentos, linhas_coloridas, linhas_de_rede,
    ponto_da_chamada, tracejados_soltos, tracos_dos_caminhos)
from ceneged.leitura_pdf.delimitacao import delimitar_automatico
from ceneged.dados.cadastro import bitolas_do_cabo
from ceneged.dominio.baloes import (RE_SEPARA, _limpa)
from ceneged.dados.equipes import PROJETOS
from ceneged.dominio.tabelas import RE_CABO_PB
from ceneged.dominio.materiais import contexto_pagina
from ceneged.dominio.cerca import (_cruza_seg, cerca_valida, componentes_cerca, kit_cerca,
    palavra_riscada, palavras_de_texto, rotulos_fios, segmentos_coloridos, simbolos_cerca)
from ceneged.dominio.relatorio import (aplicar_ajustes, montar_relatorio)

# ---------------------------------------------------------------------------
#  Dados de cada arquivo / página
# ---------------------------------------------------------------------------
MAX_ARQUIVOS = 15


# balões que não levam material para o relatório (identificação de poste, etc.)
PALAVRAS_BALAO_IGNORADO = ("FANTASMA",)


def balao_ignorado(texto):
    t = chave_nome(texto)
    return any(chave_nome(p) in t for p in PALAVRAS_BALAO_IGNORADO)


class Pagina:
    def __init__(self, arq, idx):
        self.page = arq.doc[idx]
        self.rot = self.page.get_rotation()
        self.page.set_rotation(0)          # trabalha sem rotação; só a imagem é girada
        self.chars = ler_caracteres(self.page)
        objs_texto = []
        self.texto_vetorial = False
        self.aviso_formato = False
        self.texto_traco = False
        self._chars_traco = []
        if len(self.chars) < 20:              # sem texto: letras desenhadas como contorno
            chars_v, objs_texto = ler_texto_vetorial(self.page, alt_min=0.4)
            if len(chars_v) > len(self.chars):
                self.chars, self.texto_vetorial = chars_v, True
            else:
                objs_texto = []
            # letras de traço (linhas sem preenchimento), em qualquer fonte e inclinação
            try:
                chars_t = ler_texto_de_traco(self.page, coletar_caminhos(self.page))
            except Exception:
                chars_t = []
            if chars_t:
                def ocupado(c, lista=list(self.chars)):
                    cx, cy = (c["l"] + c["r"]) / 2, (c["b"] + c["t"]) / 2
                    return any(o["l"] - 0.3 <= cx <= o["r"] + 0.3 and o["b"] - 0.3 <= cy <= o["t"] + 0.3 for o in lista)
                # palavra de traço que coincide (mesmo em parte) com texto já lido: fora inteira
                ruins = {c.get("pal") for c in chars_t if ocupado(c)}
                novos_t = [c for c in chars_t if c.get("pal") not in ruins]
                # guardadas à parte: só entram se a folha não for lida no formato habitual
                self._chars_traco = novos_t
        self.desenho = arq.doc_desenho[idx]
        self.desenho.set_rotation(0)
        remover_objetos(self.desenho, objs_texto)
        remover_textos(self.desenho)
        remover_imagens(self.desenho)
        self.fino = arq.doc_fino[idx]
        self.fino.set_rotation(0)
        remover_objetos(self.fino, objs_texto)
        remover_textos(self.fino)
        afinar_tracos(self.fino)
        try:
            self._info_delim = {}
            self.poligono_auto = delimitar_automatico(self.desenho, info=self._info_delim)
        except Exception:
            pl, pb, pr, pt = self.page.get_bbox()
            self.poligono_auto = [(pl, pb), (pr, pb), (pr, pt), (pl, pt)]
        self.poligono = list(self.poligono_auto)
        self.manual = False
        # correções feitas à mão: balões tirados, texto corrigido, balões marcados
        self.correcoes = {"excluir": [], "texto": {}, "novos": [], "rede": {}}
        self.cerca_auto = None
        self._rede_cor = None              # (sólidos, linhas coloridas) p/ fim/meio de rede
        self._tok_postes = None            # etiquetas de poste (texto) da folha: poste existente
        self.baloes = None                 # None = ainda não processada
        self.arq = arq
        self.cabos, self.trechos, self.rede, self.ancoras = {}, [], None, {}
        # tipo de projeto: caixas empilhadas (fonte de traço) ou balões com vírgula
        self.caminhos = coletar_caminhos(self.page)
        self.caixas = caixas_vetoriais(self.caminhos)
        pg = np.array(self.poligono, np.float32)
        dentro = [c for c in self.caixas
                  if cv2.pointPolygonTest(pg, ((c[0] + c[2]) / 2, (c[1] + c[3]) / 2), False) >= 0]
        self.formato_auto = "empilhado" if contar_pilhas(dentro) >= 6 else "virgula"

    @property
    def formato(self):
        f = getattr(self.arq, "formato", "auto")
        return self.formato_auto if f == "auto" else f

    def processar(self, juntar=True, comprimentos=True):
        # letras de traço entram quando trazem balão de poste ("400/12") ou código de cabo
        # ("3xS4/0-13,8kV"); em projeto com balão habitual elas são só carimbo e símbolo
        if self._chars_traco and not self.texto_traco:
            uteis = any(RE_POSTE_ESF_ALT.match(t.strip()) or RE_CABO_TEXTO.match(t.strip())
                        for t, _, _, _ in palavras_de_texto(self._chars_traco))
            if uteis:
                self.chars = list(self.chars) + list(self._chars_traco)
                self.texto_traco = True
        self._processar(juntar, comprimentos)
        # marca do desenho lida como balão (círculo de corte com "K", por ex.): pequena e
        # sem número - não é material
        if self.baloes:
            def _marca(b):
                x0, y0, x1, y1 = b["bbox_pdf"]
                t_ = re.sub(r"[^A-Za-z0-9]", "", b.get("texto") or "")
                # código de material é em maiúsculas ("TE" de verdade fica); o "K" lido como "lt" sai
                return (max(x1 - x0, y1 - y0) < 12 and len(t_) <= 2 and not re.search(r"\d", t_)
                        and any(ch.islower() for ch in t_))
            self.baloes = [b for b in self.baloes if not _marca(b)]
        # balão quadrado (um material por linha) aparece como os demais: separado por vírgula
        for b in self.baloes or []:
            if b.get("quadrado"):
                for k in ("texto", "principal"):
                    if isinstance(b.get(k), str) and "\n" in b[k]:
                        b[k] = ", ".join(l_.strip() for l_ in b[k].split("\n") if l_.strip())
        self.aplicar_correcoes()
        try:
            self.detectar_cerca()
        except Exception:
            self.cerca_auto = None

    def detectar_cerca(self):
        """Cerca por trecho: cada "N FIOS" escrito é um trecho; as figuras de aterramento
        de cerca e de seccionamento vão para o "N FIOS" mais perto. Figuras longe de
        qualquer "N FIOS" formam trechos sem fios. Vale como cerca se algum trecho tiver
        pelo menos 2 das 3 informações."""
        self.cerca_auto = None
        pg_ = np.array(self.poligono, np.float32)
        folga = 15.0

        def no_projeto(x, y):
            if len(pg_) >= 3 and cv2.pointPolygonTest(pg_, (float(x), float(y)), True) < -folga:
                return False
            return not (not self.manual and self._fora_da_divisoria(x, y))
        simb_c = [s_ for s_ in simbolos_cerca(self.page, self.caminhos, com_cor=True) if no_projeto(s_[1], s_[2])]
        simb = [q[:4] for q in simb_c]
        cs = [c for c in self.chars if no_projeto((c["l"] + c["r"]) / 2, (c["b"] + c["t"]) / 2)]
        rot = [r_ for r_ in rotulos_fios(cs)]                      # (fios, x, y)
        self._cerca_todos = {"simb": list(simb), "rot": list(rot)}
        # trecho = cada cerca desenhada (linha da cerca, ligada pedaço a pedaço)
        try:
            ids, F, comp = componentes_cerca(self.page, self.caminhos, simb_c)
        except Exception:
            ids, F, comp = [None] * len(simb), np.zeros((0, 4)), np.zeros(0, int)
        trechos, por_cerca = [], {}
        for q, cid in zip(simb, ids):
            if cid is None:
                continue
            if cid not in por_cerca:
                por_cerca[cid] = {"fios": None, "fios_pos": None, "pontos": [], "fios_lista": [],
                                  "linha": [tuple(round(float(v), 1) for v in sg) for sg, c_ in zip(F, comp)
                                            if int(c_) == cid]}
                trechos.append(por_cerca[cid])
            por_cerca[cid]["pontos"].append(q)
        rot_livres = []
        for f_, x, y in rot:
            melhor = None
            if len(F):
                d = np.array([_dist_seg(x, y, sg)[0] for sg in F])
                k = int(np.argmin(d))
                if d[k] <= 40 and int(comp[k]) in por_cerca:
                    melhor = int(comp[k])
            if melhor is None:
                rot_livres.append((f_, x, y))
            else:
                tr = por_cerca[melhor]
                tr["fios_lista"].append(f_)
                if tr["fios_pos"] is None:
                    tr["fios_pos"] = (x, y)
        for tr in trechos:
            if tr["fios_lista"]:
                tr["fios"] = max(set(tr["fios_lista"]), key=tr["fios_lista"].count)
        simb = [q for q, cid in zip(simb, ids) if cid is None]   # figuras fora de cerca achada
        rot = rot_livres
        trechos += [{"fios": f_, "fios_pos": (x, y), "pontos": []} for f_, x, y in rot]
        D = 90.0
        soltos = []
        for t, x, y, r in simb:
            perto = min(((math.hypot(x - tr["fios_pos"][0], y - tr["fios_pos"][1]), k)
                         for k, tr in enumerate(trechos)), default=None)
            if perto and perto[0] <= D:
                trechos[perto[1]]["pontos"].append((t, x, y, r))
            else:
                soltos.append((t, x, y, r))
        # figuras sem "N FIOS" perto: grupos de figuras próximas
        grupos = []
        for pt_ in soltos:
            g = next((g for g in grupos if any(math.hypot(pt_[1] - q[1], pt_[2] - q[2]) <= 45 for q in g)), None)
            if g is None:
                grupos.append([pt_])
            else:
                g.append(pt_)
        trechos += [{"fios": None, "fios_pos": None, "pontos": g} for g in grupos]
        for tr in trechos:
            tr["aterr"] = sum(1 for q in tr["pontos"] if q[0] == "A") or None
            tr["secc"] = sum(1 for q in tr["pontos"] if q[0] == "S") or None
            xs = [q[1] for q in tr["pontos"]] + ([tr["fios_pos"][0]] if tr["fios_pos"] else [])
            ys = [q[2] for q in tr["pontos"]] + ([tr["fios_pos"][1]] if tr["fios_pos"] else [])
            tr["centro"] = (float(np.mean(xs)), float(np.mean(ys)))
            tr["n_info"] = sum(1 for v in (tr["fios"], tr["aterr"], tr["secc"]) if v)
        if not any(tr["n_info"] >= 2 for tr in trechos):
            return
        # de cima para baixo, da esquerda para a direita
        trechos.sort(key=lambda tr: (-round(tr["centro"][1] / 20), tr["centro"][0]))
        self.cerca_auto = {"trechos": trechos}

    def segs_estilo(self):
        """(S, info) de todos os traços da folha (com cache)"""
        if getattr(self, "_segs_cor", None) is None:
            self._segs_cor = segmentos_coloridos(self.page, self.caminhos)
        return self._segs_cor

    def cerca_trechos(self):
        """Trechos da cerca que valem: os conferidos à mão; senão os achados no desenho.
        -> lista de dicts {fios, aterr, secc, pontos, centro, ok, ignorar}"""
        c = self.correcoes.get("cerca")
        auto = getattr(self, "cerca_auto", None)
        # a cerca achada no desenho sempre aparece: conferência guardada de outra versão que
        # ficou sem cerca ("não tem cerca" ou trechos vazios) não esconde a que existe
        if c and auto and any(cerca_valida(t) for t in auto.get("trechos", [])):
            trs_c = [c] if "trechos" not in c else c.get("trechos") or []
            if c.get("nao") or not any(cerca_valida(t) and not t.get("ignorar") for t in trs_c):
                self.correcoes.pop("cerca", None)
                c = None
        if c:
            if c.get("nao"):
                return []
            if "trechos" not in c:                         # formato antigo (um trecho só)
                c = {"trechos": [dict(c)]}
                self.correcoes["cerca"] = c
            # conferido numa versão sem o desenho da cerca: pega a linha do que foi achado
            for tr in c["trechos"]:
                if tr.get("linha") or not auto:
                    continue
                pts = set(tuple(round(v, 1) for v in q[1:3]) for q in tr.get("pontos") or [])
                melhor = None
                for ta in auto["trechos"]:
                    comum = len(pts & set(tuple(round(v, 1) for v in q[1:3]) for q in ta.get("pontos") or []))
                    d = math.dist(tr["centro"], ta["centro"]) if tr.get("centro") and ta.get("centro") else 1e9
                    nota = (comum, -d)
                    if ta.get("linha") and (comum or d <= 80) and (melhor is None or nota > melhor[0]):
                        melhor = (nota, ta)
                if melhor is None and len(auto["trechos"]) == 1 and len(c["trechos"]) == 1:
                    melhor = ((0, 0), auto["trechos"][0])
                if melhor:
                    tr["linha"] = melhor[1]["linha"]
                    if not tr.get("pontos"):
                        tr["pontos"] = melhor[1].get("pontos", [])
                    tr.setdefault("centro", melhor[1].get("centro"))
            return c["trechos"]
        return list(auto["trechos"]) if auto else []

    @staticmethod
    def chave_balao(b):
        x0, y0, x1, y1 = b["bbox_pdf"]
        return f"{(x0 + x1) / 2:.0f},{(y0 + y1) / 2:.0f}"

    def aplicar_correcoes(self):
        if self.baloes is None:
            return
        cor = self.correcoes
        saida = []
        for b in self.baloes:
            if b.get("manual"):
                continue
            if not b.get("tipo") == "material" and balao_ignorado(b["texto"]):
                continue                     # ex.: "PG FANTASMA" (nome de poste, não é material)
            k = self.chave_balao(b)
            if k in cor["excluir"]:
                continue
            if k in cor["texto"]:
                t = cor["texto"][k]
                b.update(texto=t, principal=t, complementos=[], comprimento="", corrigido=True)
            saida.append(b)
        for n in cor["novos"]:
            saida.append({"texto": n["texto"], "principal": n["texto"], "bbox_pdf": tuple(n["bbox"]), "chars": [],
                          "ang": 0, "alt": 2.0, "complementos": [], "comprimento": "", "manual": True})
        self.baloes = saida
        self.marcar_posicao_rede()
        self.marcar_cabo_pb()

    def marcar_cabo_pb(self):
        """Bitola do cabo PB de cada balão: a do próprio balão, ou a do balão de cabo PB
        mais perto (para a alça preformada de distribuição)."""
        pbs = []
        for b in self.baloes or []:
            g = [int(m.group(1)) for m in RE_CABO_PB.finditer(b["texto"].upper())]
            if g:
                x0, y0, x1, y1 = b["bbox_pdf"]
                pbs.append((max(g), (x0 + x1) / 2, (y0 + y1) / 2))
        for b in self.baloes or []:
            g = [int(m.group(1)) for m in RE_CABO_PB.finditer(b["texto"].upper())]
            if g:
                b["cabo_pb"] = max(g)
            elif pbs:
                x0, y0, x1, y1 = b["bbox_pdf"]
                cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                b["cabo_pb"] = min(pbs, key=lambda t: math.hypot(t[1] - cx, t[2] - cy))[0]
            else:
                b["cabo_pb"] = None

    def marcar_posicao_rede(self):
        """FLBIT/FLABIT: o poste está no fim da rede (sem conectores) ou no meio (com os conectores dos materiais extras)?
        Automático pelo desenho; a escolha feita à mão (correcoes["rede"]) vale mais."""
        # fim/meio: FLBIT/FLABIT; cabo de cada lado (alças): os outros balões de estrutura
        alvo = [b for b in self.baloes or [] if RE_FIM_DE_REDE.search(b["texto"].upper()) or
                (b.get("tipo") not in ("cabo", "material") and not RE_CABO_PB.search(b["texto"].upper()))]
        if not alvo:
            return
        rede, solidos = None, None
        try:
            if self._rede_cor is None:
                _, sol = tracos_dos_caminhos(self.caminhos)
                self._rede_cor = (np.array(sol, float).reshape(-1, 4),
                                  np.array(linhas_coloridas(self.page, self.caminhos), float).reshape(-1, 7))
            solidos, G7 = self._rede_cor
            G = G7[:, :4]
            # sem as chamadas e as bordas dos balões
            fora = np.ones(len(G), bool)
            for b in self.baloes:
                x0, y0, x1, y1 = b["bbox_pdf"]
                for e in (0, 2):
                    fora &= ~((G[:, e] >= x0 - 1.5) & (G[:, e] <= x1 + 1.5) &
                              (G[:, e + 1] >= y0 - 1.5) & (G[:, e + 1] <= y1 + 1.5))
            m_ = linhas_de_rede(G[fora], mascara=True)
            rede = G[fora][m_]
            matiz = _matiz(G7[fora][m_][:, 4:7])
            # baixa tensão: a cor das linhas onde encostam as chamadas dos balões de cabo
            # PB (a média tensão que passa no poste não conta para fim/meio)
            mbt = self._matizes_bt(solidos, rede, matiz)
            rede_bt = rede
            if mbt:
                perto = np.zeros(len(rede), bool)
                for h in mbt:
                    dh = np.abs(matiz - h)
                    perto |= np.minimum(dh, 360 - dh) <= 25
                if perto.any():
                    rede_bt = rede[perto]
        except Exception:
            rede, rede_bt = None, None
        manual = self.correcoes.get("rede", {})
        rede_tr = None                     # rede BT + tracejados coloridos (só se precisar)

        def com_tracejados():
            """rede de baixa tensão somando as linhas coloridas tracejadas (ex.: BT verde de
            traços longos e espaçados), com os vãos entre os traços preenchidos. A BT é a cor
            onde encostam as chamadas dos balões de cabo PB (a MT que passa no poste fica fora)."""
            extra, cores_e = [], []
            try:
                tr_, _ = tracos_dos_caminhos(self.caminhos)
                for k_, segs in tr_.items():
                    cor_ = cor_do_objeto(self.page, (k_,), False)
                    if cor_ is None or max(cor_) - min(cor_) < 60:
                        continue
                    S_ = [tuple(float(v) for v in g[:4]) for g in segs]
                    n0 = len(extra)
                    extra += S_
                    for i_, g in enumerate(S_):
                        for e in ((g[0], g[1]), (g[2], g[3])):
                            melhor_ = None
                            for j_, h in enumerate(S_):
                                if j_ == i_:
                                    continue
                                for f in ((h[0], h[1]), (h[2], h[3])):
                                    dd = math.dist(e, f)
                                    if dd <= 25 and (melhor_ is None or dd < melhor_[0]):
                                        melhor_ = (dd, f)
                            if melhor_ and melhor_[0] > 0.5:
                                extra.append((e[0], e[1], melhor_[1][0], melhor_[1][1]))
                    cores_e += [cor_] * (len(extra) - n0)
            except Exception:
                return None
            if not extra:
                return None
            R = np.vstack([rede, np.array(extra, float).reshape(-1, 4)])
            H = np.concatenate([matiz, _matiz(np.array(cores_e, float))])
            hs = []
            for bb_ in self.baloes:
                if not RE_CABO_PB.search(bb_["texto"].upper()):
                    continue
                q_ = ponto_da_chamada(bb_["bbox_pdf"], solidos, R)
                if q_ is None:
                    continue
                dd = np.array([_dist_seg(q_[0], q_[1], g)[0] for g in R])
                k_ = int(np.argmin(dd))
                if dd[k_] <= 3:
                    hs.append(float(H[k_]))
            if not hs:
                return None
            perto = np.zeros(len(R), bool)
            for h in hs:
                dh = np.abs(H - h)
                perto |= np.minimum(dh, 360 - dh) <= 25
            return R[perto] if perto.any() else None
        for b in alvo:
            auto, ponto = None, None
            lados = []
            if rede is not None:
                try:
                    d = analisar_poste(b["bbox_pdf"], solidos, rede_bt)
                    if d["pos"] is None and rede_bt is not rede:
                        d = analisar_poste(b["bbox_pdf"], solidos, rede)
                    # confere pela BT tracejada: acha o poste que ficou sem rede, e o "fim" que
                    # na verdade tem a BT seguindo dos dois lados (meio)
                    if d["pos"] in (None, "fim") and RE_FIM_DE_REDE.search(b["texto"].upper()):
                        if rede_tr is None:
                            rede_tr = com_tracejados()
                            rede_tr = rede_tr if rede_tr is not None else False
                        if rede_tr is not False:
                            d2 = analisar_poste(b["bbox_pdf"], solidos, rede_tr)
                            if (d["pos"] is None and d2["pos"]) or (d["pos"] == "fim" and d2["pos"] == "meio"):
                                d = d2
                    auto, ponto = d["pos"], d["poste"]
                    if d["q"] and d["dirs"]:
                        lados = cabos_de_cada_lado(d["q"], d["dirs"], self._ancoras_pb(solidos, rede))
                except Exception:
                    pass
            if ponto is not None:
                b["poste_ponto"] = tuple(float(v) for v in ponto)
                # balão sem poste novo: estrutura em poste existente; o poste vem da etiqueta
                # do poste no desenho (ex.: "12600D | B3 | CE2  M001347")
                if not any(info_poste(x.strip()) for x in re.split(r"[,;\n]", b["texto"])):
                    pe = self._poste_existente(ponto)
                    if pe:
                        b["poste_existente"] = pe
            if not RE_FIM_DE_REDE.search(b["texto"].upper()):
                b["rede_cabos"] = lados
                continue
            m = manual.get(self.chave_balao(b))
            b.update(rede_auto=auto, rede_ponto=ponto, rede_manual=bool(m), rede_pos=m or auto,
                     rede_cabos=lados)

    def _poste_existente(self, ponto, raio=45.0):
        """Etiqueta de poste existente perto do ponto do poste (texto selecionável fora dos
        balões): '12600D', '11/300'... O mais perto vale. None se não achar."""
        if getattr(self, "_tok_postes", None) is None:
            toks = []
            try:
                tp = self.page.get_textpage()
                n = tp.count_chars()
                txt = tp.get_text_range(0, n)
                for m in re.finditer(r"(?<![\w/])(\d{3,4}/\d{1,2}|\d{4,6})\s?(DT|D|C|CC|FV)?(?![\w/])", txt):
                    p_ = info_poste(m.group(0).replace(" ", ""))
                    if not p_:
                        continue
                    xs, ys = [], []
                    for k in range(m.start(), m.end()):
                        if k < n:
                            l, b_, r, t = tp.get_charbox(k)
                            if r > l:
                                xs += [l, r]
                                ys += [b_, t]
                    if not xs:
                        continue
                    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
                    dentro = any(x0 - 1 <= cx <= x1 + 1 and y0 - 1 <= cy <= y1 + 1
                                 for x0, y0, x1, y1 in (bb["bbox_pdf"] for bb in self.baloes or []))
                    if not dentro:
                        toks.append((min(xs), min(ys), max(xs), max(ys), m.group(0).replace(" ", "")))
            except Exception:
                toks = []
            self._tok_postes = toks
        melhor = None
        for x0, y0, x1, y1, t in self._tok_postes:     # distância até o retângulo do texto
            d = math.hypot(max(x0 - ponto[0], 0, ponto[0] - x1), max(y0 - ponto[1], 0, ponto[1] - y1))
            if d <= raio and (melhor is None or d < melhor[0]):
                melhor = (d, t)
        return melhor[1] if melhor else None

    def _matizes_bt(self, solidos, rede, matiz):
        """matizes das linhas de rede em que encostam as chamadas dos balões de cabo PB"""
        hs = []
        for g, x, y in self._ancoras_pb(solidos, rede):
            P = rede
            cx, cy = (P[:, 0] + P[:, 2]) / 2, (P[:, 1] + P[:, 3]) / 2
            melhor = None
            for i in np.nonzero(np.hypot(cx - x, cy - y) <= 60)[0]:
                dd, _ = _dist_seg(x, y, P[i])
                if melhor is None or dd < melhor[0]:
                    melhor = (dd, i)
            if melhor and melhor[0] <= 3:
                hs.append(float(matiz[melhor[1]]))
        saida = []
        for h in hs:
            if not any(min(abs(h - k), 360 - abs(h - k)) <= 25 for k in saida):
                saida.append(h)
        return saida

    def _ancoras_pb(self, solidos, rede):
        """[(bitola, x, y)]: onde a chamada de cada balão de cabo PB encosta na rede."""
        chave = tuple(self.chave_balao(b) for b in self.baloes)
        if getattr(self, "_cache_pb", (None,))[0] == chave:
            return self._cache_pb[1]
        out = []
        for b in self.baloes:
            g = [int(m.group(1)) for m in RE_CABO_PB.finditer(b["texto"].upper())]
            if not g or RE_FIM_DE_REDE.search(b["texto"].upper()):
                continue
            pt = ponto_da_chamada(b["bbox_pdf"], solidos, rede)
            if pt:
                out.append((max(g), pt[0], pt[1]))
        self._cache_pb = (chave, out)
        return out

    def _processar(self, juntar=True, comprimentos=True):
        xs = [p[0] for p in self.poligono]
        ys = [p[1] for p in self.poligono]
        area = (min(xs), min(ys), max(xs), max(ys))
        self.cabos, self.trechos, self.rede, self.ancoras = {}, [], None, {}
        if self.formato == "empilhado":
            self._processar_empilhado(area, comprimentos)
            return
        # delimitação automática: procura na folha inteira e fica com os balões dentro da área
        # ou perto dela (até ~12% da folha: ponta da rede, balão encostado na moldura). A
        # legenda e o carimbo ficam bem mais longe. A delimitação desenhada à mão vale exata.
        if not self.manual:
            # a área do projeto sai dos balões achados (e da rede que liga eles); o
            # desenho da folha (ruas, fotos, quadros) só entra se não houver balões
            try:
                if self._delimitar_pelos_baloes(juntar):
                    xs = [p[0] for p in self.poligono]
                    ys = [p[1] for p in self.poligono]
                    area = (min(xs), min(ys), max(xs), max(ys))
            except Exception:
                pass
        folga, folga_rede, area_rede = 0.0, 0.0, area
        if not self.manual:
            pl, pb, pr, pt = self.page.get_bbox()
            folga = max(60.0, 0.12 * min(pr - pl, pt - pb))
            folga_rede = 20.0
            area_rede = (area[0] - 20, area[1] - 20, area[2] + 20, area[3] + 20)
            area = (pl, pb, pr, pt)
        if comprimentos:
            # balões de cabo com chamada até o tracejado e metros escritos ao longo
            # do caminho: os metros são do cabo, não do balão do poste mais perto
            bal = detectar_baloes(self.page, area_rede, self.chars, page_desenho=self.desenho,
                                  page_fino=self.fino, poligono=self.poligono, juntar=juntar,
                                  comprimentos=False, so_arredondados=True, poligono_folga=folga_rede)
            if self._cabos_pelo_caminho(bal, area_rede):
                self._tirar_alem_da_divisoria()
                if getattr(self, "texto_traco", False) or self.texto_vetorial:
                    try:
                        self._baloes_das_caixas()
                    except Exception:
                        pass
                self.aviso_formato = any(b.get("quadrado") for b in self.baloes)
                if self.aviso_formato:
                    try:
                        self._cabos_quadrados(area_rede)
                    except Exception:
                        pass
                return
        retos = []
        self.baloes = detectar_baloes(self.page, area, self.chars, page_desenho=self.desenho,
                                      page_fino=self.fino, poligono=self.poligono,
                                      juntar=juntar, ocr_comprimentos=comprimentos,
                                      comprimentos=comprimentos, so_arredondados=True,
                                      poligono_folga=folga, retos=retos)
        self._tirar_alem_da_divisoria()
        # balões em caixa quadrada (fora do formato habitual): avisa para conferir
        if getattr(self, "texto_traco", False) or self.texto_vetorial:
            try:
                self._baloes_das_caixas()
            except Exception:
                pass
        self.aviso_formato = any(b.get("quadrado") for b in self.baloes)
        if self.aviso_formato and comprimentos:
            try:
                self._cabos_quadrados(area_rede)
            except Exception:
                pass

    def _fora_da_divisoria(self, x, y):
        for eixo, pos, menor in getattr(self, "_info_delim", {}).get("cortes", []):
            v = x if eixo == "x" else y
            if (v > pos) if menor else (v < pos):
                return True
        return False

    def _delimitar_pelos_baloes(self, juntar=True):
        """Delimitação automática pelos balões: em volta de todos os balões do projeto (e
        da rede colorida que sai deles), com folga. Fica de fora o que é exemplo da
        legenda e o que está do outro lado da divisória da legenda."""
        pl, pb, pr, pt = self.page.get_bbox()
        W, H = pr - pl, pt - pb
        sem = detectar_baloes(self.page, (pl, pb, pr, pt), self.chars, page_desenho=self.desenho,
                              page_fino=self.fino, juntar=juntar, comprimentos=False, so_arredondados=True)
        sem = [b for b in sem if not perto_de_legenda(b, self.chars)]
        # divisória com o lado do desenho trocado (nenhum balão do lado escolhido pelo
        # desenho da folha): vira para o lado onde estão os balões
        info = getattr(self, "_info_delim", None)
        if info is not None and info.get("cortes") and sem:
            novos = []
            for eixo, pos, menor in info["cortes"]:
                vs = [((b["bbox_pdf"][0] + b["bbox_pdf"][2]) / 2) if eixo == "x" else
                      ((b["bbox_pdf"][1] + b["bbox_pdf"][3]) / 2) for b in sem]
                do_lado = sum(1 for v in vs if (v < pos) == menor)
                novos.append((eixo, pos, menor if do_lado else not menor))
            info["cortes"] = novos
        sem = [b for b in sem if not self._fora_da_divisoria(
            (b["bbox_pdf"][0] + b["bbox_pdf"][2]) / 2, (b["bbox_pdf"][1] + b["bbox_pdf"][3]) / 2)]
        if len(sem) < 2:
            return False
        if self._rede_cor is None:
            _, sol = tracos_dos_caminhos(self.caminhos)
            self._rede_cor = (np.array(sol, float).reshape(-1, 4),
                              np.array(linhas_coloridas(self.page, self.caminhos), float).reshape(-1, 7))
        solidos, G7 = self._rede_cor
        pts = []
        for b in sem:
            x0, y0, x1, y1 = b["bbox_pdf"]
            pts += [(x0, y0), (x1, y0), (x0, y1), (x1, y1)]
            for vert in _chamada_vertices(b["bbox_pdf"], solidos):
                pts += vert[:2]
        P = np.array(pts, float)
        # rede colorida perto dos balões, e o que estiver ligado a ela (dentro de uma folga)
        try:
            mrede = linhas_de_rede(G7[:, :4], mascara=True) if len(G7) else np.zeros(0, bool)
            Ntodas = G7[:, :4][mrede]
            Htodas = _matiz(G7[mrede][:, 4:7]) if len(Ntodas) else np.zeros(0)
        except Exception:
            Ntodas, Htodas = np.zeros((0, 4)), np.zeros(0)
        N, Hn = Ntodas, Htodas
        if len(N):
            m = min(W, H)
            bx0, by0 = P.min(0) - 0.15 * m
            bx1, by1 = P.max(0) + 0.15 * m
            ok_ = ((np.minimum(N[:, 0], N[:, 2]) >= bx0) & (np.maximum(N[:, 0], N[:, 2]) <= bx1) &
                   (np.minimum(N[:, 1], N[:, 3]) >= by0) & (np.maximum(N[:, 1], N[:, 3]) <= by1))
            N, Hn = N[ok_], Hn[ok_]
        self._matizes_projeto = []
        if len(N):
            D = max(40.0, 0.06 * min(W, H))
            mid = (N[:, :2] + N[:, 2:]) / 2
            dist = np.min(np.hypot(mid[:, None, 0] - P[None, :, 0], mid[:, None, 1] - P[None, :, 1]), axis=1)
            dentro = dist <= D
            pontas = np.vstack([N[:, :2], N[:, 2:]])
            for _ in range(200):
                sel = np.vstack([N[dentro, :2], N[dentro, 2:]])
                if not len(sel):
                    break
                novo = dentro.copy()
                for k in np.nonzero(~dentro)[0]:
                    d1 = np.min(np.hypot(sel[:, 0] - N[k, 0], sel[:, 1] - N[k, 1]))
                    d2 = np.min(np.hypot(sel[:, 0] - N[k, 2], sel[:, 1] - N[k, 3]))
                    if min(d1, d2) <= 4.0:
                        novo[k] = True
                if novo.sum() == dentro.sum():
                    break
                dentro = novo
            if dentro.any():
                P = np.vstack([P, N[dentro, :2], N[dentro, 2:]])
                hs = []
                for h in Hn[dentro]:
                    if not any(min(abs(h - k_), 360 - abs(h - k_)) <= 25 for k_ in hs):
                        hs.append(float(h))
                self._matizes_projeto = hs
        # quadros grandes sem nenhum balão (figura de detalhe, "disposição dos alimentadores")
        quadros = []
        cent = [((b["bbox_pdf"][0] + b["bbox_pdf"][2]) / 2, (b["bbox_pdf"][1] + b["bbox_pdf"][3]) / 2) for b in sem]
        for i, fill, st, subs in self.caminhos:
            if not st:
                continue
            for s_ in subs:
                if not 4 <= len(s_) <= 6:
                    continue
                a = np.array(s_)
                x0, y0 = a.min(0)
                x1, y1 = a.max(0)
                w_, h_ = x1 - x0, y1 - y0
                if (w_ > 0.08 * W and h_ > 0.05 * H and w_ * h_ < 0.4 * W * H and
                        all(min(abs(x - x0), abs(x - x1)) < 0.02 * w_ + 0.5 and
                            min(abs(y - y0), abs(y - y1)) < 0.02 * h_ + 0.5 for x, y in a) and
                        not any(x0 <= cx <= x1 and y0 <= cy <= y1 for cx, cy in cent)):
                    quadros.append((x0, y0, x1, y1))
        # máscara: cada grupo de pontos vira um polígono convexo, com folga; grupos ligados
        esc = 1000.0 / max(W, H)
        Hm, Wm = int(H * esc) + 2, int(W * esc) + 2
        px = np.clip(((P[:, 0] - pl) * esc).astype(int), 0, Wm - 1)
        py = np.clip(((pt - P[:, 1]) * esc).astype(int), 0, Hm - 1)
        pontos = np.zeros((Hm, Wm), np.uint8)
        pontos[py, px] = 1
        raio = max(3, int(0.12 * min(Wm, Hm)))
        grupos = cv2.dilate(pontos, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * raio + 1, 2 * raio + 1)))
        n, lab = cv2.connectedComponents(grupos)
        mask = np.zeros_like(pontos)
        for i in range(1, n):
            sel = lab[py, px] == i
            if sel.sum() >= 1:
                q = np.column_stack([px[sel], py[sel]]).astype(np.int32)
                cv2.fillPoly(mask, [cv2.convexHull(q)], 1)
        folga = max(3, int(0.035 * min(Wm, Hm)))
        mask = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * folga + 1, 2 * folga + 1)))
        # + o desenho (ruas, rede) das partes da folha onde estão os balões
        try:
            info2 = {}
            rp = []
            if len(Ntodas) and self._matizes_projeto:
                # só rede da mesma cor da rede que sai dos balões
                perto_h = np.zeros(len(Ntodas), bool)
                for h in self._matizes_projeto:
                    dh = np.abs(Htodas - h)
                    perto_h |= np.minimum(dh, 360 - dh) <= 25
                Nc = Ntodas[perto_h]
                rp = [tuple(q) for q in ((Nc[:, :2] + Nc[:, 2:]) / 2)]
            pol_d = delimitar_automatico(self.desenho, info=info2, sementes=[tuple(q) for q in P], rede_pts=rp,
                                         proibidas=quadros)
            q = np.array([[(x - pl) * esc, (pt - y) * esc] for x, y in pol_d], np.int32)
            if len(q) >= 3:
                cv2.fillPoly(mask, [q], 1)
            if info2.get("cortes") is not None:
                self._info_delim = info2
        except Exception:
            pass
        # não passa da divisória da legenda
        for eixo, pos, menor in getattr(self, "_info_delim", {}).get("cortes", []):
            if eixo == "x":
                c = int((pos - pl) * esc)
                if menor:
                    mask[:, max(c, 0):] = 0
                else:
                    mask[:, :max(c + 1, 0)] = 0
            else:
                r = int((pt - pos) * esc)
                if menor:
                    mask[:max(r + 1, 0), :] = 0
                else:
                    mask[max(r, 0):, :] = 0
        cs, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for X0, Y0, X1, Y1 in quadros:
            mask[max(0, int((pt - Y1) * esc)):int((pt - Y0) * esc) + 1, max(0, int((X0 - pl) * esc)):int((X1 - pl) * esc) + 1] = 0
        cs, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not cs:
            return False
        if len(cs) > 1:                     # liga as partes
            c0 = max(cs, key=cv2.contourArea)
            for o in cs:
                if o is c0:
                    continue
                A, B = c0[:, 0, :].astype(np.float32), o[:, 0, :].astype(np.float32)
                dd = ((A[:, None, :] - B[None, :, :]) ** 2).sum(2)
                a_, b_ = np.unravel_index(int(np.argmin(dd)), dd.shape)
                cv2.line(mask, tuple(int(v) for v in A[a_]), tuple(int(v) for v in B[b_]), 1, max(2, folga))
            cs, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        c = max(cs, key=cv2.contourArea)
        c = cv2.approxPolyDP(c, 2.0, True)[:, 0, :]
        if len(c) < 3:
            return False
        pol = [(pl + float(x) / esc, pt - float(y) / esc) for x, y in c]
        self.poligono = list(pol)
        self.poligono_auto = list(pol)
        return True

    def _tirar_alem_da_divisoria(self):
        """Delimitação automática: balão do outro lado da divisória da legenda (exemplos
        de balão do quadro de componentes) não é do projeto."""
        if self.manual or not self.baloes:
            return
        cortes = getattr(self, "_info_delim", {}).get("cortes", [])
        if not cortes:
            return

        def fica(b):
            x0, y0, x1, y1 = b["bbox_pdf"]
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            for eixo, pos, menor in cortes:          # menor: desenho do lado de valor menor
                v = cx if eixo == "x" else cy
                if (v > pos) if menor else (v < pos):
                    return False
            return True
        self.baloes = [b for b in self.baloes if fica(b)]

    def _ler_comprimentos_rede(self, rede, area, proibido, caixas_cabo, ang, com_traco=False):
        """Comprimentos (ex.: 45m) perto do tracejado: texto do PDF e fonte de traço."""
        pg = np.array(self.poligono, np.float32)
        dentro = lambda x, y: cv2.pointPolygonTest(pg, (float(x), float(y)), False) >= 0
        rot = []

        def soma(v, cx, cy):
            # o mesmo rótulo lido duas vezes (texto do PDF e traço) conta uma vez só
            if not any((v == r[0] and abs(cx - r[1]) < 15 and abs(cy - r[2]) < 15) or
                       (abs(cx - r[1]) < 4 and abs(cy - r[2]) < 4) for r in rot):
                rot.append((v, cx, cy))

        def aceita(cx, cy):
            if not dentro(cx, cy):
                return False
            if any(c[0] + 0.5 <= cx <= c[2] - 0.5 and c[1] + 0.5 <= cy <= c[3] - 0.5 for c in proibido):
                return False
            perto = any(math.hypot(max(b[0] - cx, 0, cx - b[2]), max(b[1] - cy, 0, cy - b[3])) <= 20
                        for b in caixas_cabo)
            return perto or bool(rede.mais_proxima(cx, cy, 30))
        # 1) texto do PDF
        for r in comprimentos_em_texto(self.chars, set(), area):
            bb = r["bbox_pdf"]
            cx, cy = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2
            m = re.match(r"(\d{1,4})", r["texto"])
            if m and aceita(cx, cy):
                soma(int(m.group(1)), cx, cy)
        # 2) fonte de traço do CAD
        texto = TextoTraco(self.caminhos, excluir=(set(rede.obj.tolist()) if len(rede.obj) else set()) |
                           set(getattr(rede, "obj_extra", set())))
        cands = []
        for bb, idx in texto.palavras(ang, area):
            cx, cy = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2
            if max(bb[2] - bb[0], bb[3] - bb[1]) <= 60 and 2 <= len(idx) <= 40 and aceita(cx, cy):
                cands.append((bb, idx, cx, cy))
        if cands:
            s = estimar_inclinacao_traco([texto.imagem(bb, ang, idx=idx) for bb, idx, _, _ in cands[:40]])
            for bb, idx, cx, cy in cands:
                txt, _ = ler_linha_traco(texto.imagem(bb, ang, idx=idx), s)
                for tk in txt.split():
                    m = re.match(r"^[^\w]?(\d{2,4})m", tk)
                    if m:
                        soma(int(m.group(1)), cx, cy)
                        break
        return rot

    def _baloes_das_caixas(self):
        """Balões de poste desenhados como retângulo (com ou sem divisória) e texto de letra
        desenhada: monta pelo retângulo do PDF. Vale o retângulo cuja primeira linha é o
        poste esforço/altura ("400/12"); as linhas de baixo (N1, CE4...) são os materiais.
        Substitui pedaços do mesmo balão achados pela imagem."""
        pg = np.array(self.poligono, np.float32)
        novos, soltas = [], []
        try:
            todas = list(self.caixas) + retangulos_de_linhas(self.caminhos)
        except Exception:
            todas = list(self.caixas)
        for c in sorted(todas, key=lambda c: -(c[2] - c[0]) * (c[3] - c[1])):
            cx, cy = (c[0] + c[2]) / 2, (c[1] + c[3]) / 2
            # caixa cortada pela delimitação (metade para fora) ainda vale
            if len(pg) >= 3 and cv2.pointPolygonTest(pg, (float(cx), float(cy)), True) < -15:
                continue
            if any(n["bbox_pdf"][0] - 0.5 <= cx <= n["bbox_pdf"][2] + 0.5 and
                   n["bbox_pdf"][1] - 0.5 <= cy <= n["bbox_pdf"][3] + 0.5 for n in novos):
                continue                                   # já faz parte de um retângulo maior
            cs = [ch for ch in self.chars if c[0] - 0.3 <= (ch["l"] + ch["r"]) / 2 <= c[2] + 0.3
                  and c[1] - 0.3 <= (ch["b"] + ch["t"]) / 2 <= c[3] + 0.3]
            if not cs:
                # caixa pequena sem texto lido (letra de traço fino, ex.: "N4" embaixo do
                # poste existente): lê a caixa pela imagem; vale só código de estrutura
                w_c, h_c = c[2] - c[0], c[3] - c[1]
                if 8 <= w_c <= 60 and 5 <= h_c <= 15:
                    t_r, n_r = "", 0.0
                    for alt_px_ in (60.0, 80.0, 48.0):    # outra escala se a 1ª leitura não fechar
                        try:
                            t_, n_ = ler_caixa_raster(self.page, tuple(c), alt_px_)
                        except Exception:
                            continue
                        t_ = t_.strip()
                        if n_ > n_r:
                            t_r, n_r = t_, n_
                        if (RE_COD_ESTRUT.match(t_) or RE_POSTE_ESF_ALT.match(t_.replace(" ", ""))) and n_ >= 0.6:
                            t_r, n_r = t_, n_
                            break
                    if n_r >= 0.7 and len(t_r) >= 2 and RE_COD_ESTRUT.match(t_r):
                        soltas.append({"bbox": tuple(c), "linhas": [t_r], "chars": [], "alt": 0.6 * h_c})
                    elif n_r >= 0.6 and RE_POSTE_ESF_ALT.match(t_r.replace(" ", "")):
                        # caixa do poste ("400/12") lida pela imagem; a de baixo (N1) junta depois
                        t_r = t_r.replace(" ", "")
                        novos.append({"texto": t_r, "principal": t_r, "complementos": [], "comprimento": "",
                                      "bbox_pdf": tuple(c), "chars": [], "ang": 0.0, "alt": 0.6 * h_c,
                                      "arredondado": False, "quadrado": True})
                continue
            txt = montar_texto(cs).strip()
            linhas = [l_.strip() for l_ in txt.split("\n") if l_.strip()]
            if not linhas or RE_TEXTO_CERCA.search(txt.upper()):
                continue
            alt = float(np.median([(ch["t"] - ch["b"]) for ch in cs]))
            if not RE_POSTE_ESF_ALT.match(linhas[0]):
                # caixa só com estrutura/material (ex.: "CE3-CE3", ou "CE2", "N3", "PR" em
                # caixas empilhadas) = troca em poste existente: junta depois por pilha
                if all(RE_COD_ESTRUT.match(l_) and len(l_) >= 2 for l_ in linhas):
                    soltas.append({"bbox": tuple(c), "linhas": linhas, "chars": cs, "alt": alt})
                continue
            novos.append({"texto": "\n".join(linhas), "principal": "\n".join(linhas), "complementos": [],
                          "comprimento": "", "bbox_pdf": tuple(c), "chars": cs, "ang": 0.0, "alt": alt,
                          "arredondado": False, "quadrado": True})

        # caixas de código soltas: as que estão alinhadas e coladas uma embaixo da outra são
        # um balão só; se a pilha encosta embaixo de um balão de poste, entra nele
        def dentro_novo(b):
            cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
            return any(n["bbox_pdf"][0] - 0.5 <= cx <= n["bbox_pdf"][2] + 0.5 and
                       n["bbox_pdf"][1] - 0.5 <= cy <= n["bbox_pdf"][3] + 0.5 for n in novos)
        soltas = [s for s in soltas if not dentro_novo(s["bbox"])]
        uniq = []
        for s in soltas:                                   # mesmo retângulo achado 2 vezes
            if not any(max(abs(a - b) for a, b in zip(s["bbox"], u["bbox"])) < 0.6 for u in uniq):
                uniq.append(s)

        def empilha(a, b):
            if abs(a[0] - b[0]) > 1.5 or abs(a[2] - b[2]) > 1.5:
                return False
            folga = max(a[1], b[1]) - min(a[3], b[3])
            return folga < 0.6 * max(a[3] - a[1], b[3] - b[1])
        grupos = []
        for s in sorted(uniq, key=lambda s: -s["bbox"][3]):
            g = next((g for g in grupos if any(empilha(s["bbox"], o["bbox"]) for o in g)), None)
            if g is None:
                grupos.append([s])
            else:
                g.append(s)
        for g in grupos:
            g.sort(key=lambda s: -s["bbox"][3])
            linhas = [l_ for s in g for l_ in s["linhas"]]
            cs = [ch for s in g for ch in s["chars"]]
            bb = (min(s["bbox"][0] for s in g), min(s["bbox"][1] for s in g),
                  max(s["bbox"][2] for s in g), max(s["bbox"][3] for s in g))
            dono = next((n for n in novos if empilha(bb, n["bbox_pdf"]) and n["bbox_pdf"][1] >= bb[3] - 0.5), None)
            if dono is not None:
                dono["texto"] = dono["principal"] = dono["texto"] + "\n" + "\n".join(linhas)
                dono["chars"] = list(dono["chars"]) + cs
                x0, y0, x1, y1 = dono["bbox_pdf"]
                dono["bbox_pdf"] = (min(x0, bb[0]), min(y0, bb[1]), max(x1, bb[2]), max(y1, bb[3]))
                continue
            novos.append({"texto": "\n".join(linhas), "principal": "\n".join(linhas), "complementos": [],
                          "comprimento": "", "bbox_pdf": bb, "chars": cs, "ang": 0.0,
                          "alt": float(np.median([s["alt"] for s in g])),
                          "arredondado": False, "quadrado": True})
        if not novos:
            return 0

        def dentro_de(b, n):
            x0, y0, x1, y1 = b["bbox_pdf"]
            a0, b0, a1, b1 = n["bbox_pdf"]
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            return a0 - 0.5 <= cx <= a1 + 0.5 and b0 - 0.5 <= cy <= b1 + 0.5
        self.baloes = [b for b in self.baloes if not any(dentro_de(b, n) for n in novos)] + novos
        self.baloes.sort(key=lambda b: (-round(b["bbox_pdf"][3]), b["bbox_pdf"][0]))
        return len(novos)

    def _cabos_quadrados(self, area):
        """Projeto de balões quadrados: os balões de cabo são caixas com o texto em traço
        simples (ex.: "3#185mm²2-XLPE") encostadas no tracejado do cabo, e os metros estão
        escritos vão a vão ao longo do caminho. Soma os metros de cada cabo."""
        pg = np.array(self.poligono, np.float32)
        dentro = lambda x, y: len(pg) < 3 or cv2.pointPolygonTest(pg, (float(x), float(y)), True) >= -20

        def sobrepoe(a, b):
            return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])
        ja = [b["bbox_pdf"] for b in self.baloes]
        # balões de cabo já achados (ex.: "3#4CAA" com chamada) entram na mesma conta
        antigos = [b for b in self.baloes if b.get("tipo") == "cabo"]
        # balão (arredondado) que é só um cabo ("3#4CAA") ligado a um ramal do mesmo
        # tracejado: vira balão de cabo e os metros dele saem do caminho também
        for b in self.baloes:
            t_ = RE_METROS.sub(" ", (b.get("principal") or b["texto"])).strip()
            cabo_q = b.get("quadrado") and RE_CABO_TEXTO.match(t_.replace("\n", " ").strip())
            # balão arredondado que é só o cabo: "3#4CAA" ou "3xS4/0-13,8kV"
            so_cabo = not b.get("quadrado") and (re.fullmatch(r"\d+\s*#\s*\S+", t_) or
                                                 RE_CABO_TEXTO.match(t_.replace("\n", " ").strip()))
            if b.get("tipo") is None and (cabo_q or so_cabo):
                b["tipo"] = "cabo"
                b["texto"] = b["principal"] = t_
                b["comprimento"] = ""
                antigos.append(b)
        cabos = []
        for c in self.caixas:
            w, h = c[2] - c[0], c[3] - c[1]
            if max(w, h) < 3 * min(w, h) or any(sobrepoe(c, b) for b in ja):
                continue                                  # caixa de cabo: comprida, uma linha
            if not dentro((c[0] + c[2]) / 2, (c[1] + c[3]) / 2):
                continue
            if any(c[0] <= (ch["l"] + ch["r"]) / 2 <= c[2] and c[1] <= (ch["b"] + ch["t"]) / 2 <= c[3]
                   and not ch.get("traco") for ch in self.chars):
                continue                                  # tem texto do PDF: não é desta forma
            txt, nota = ler_caixa_raster(self.page, c)
            txt = txt.strip()
            if nota < 0.45 or len(txt) < 4 or not re.search(r"\d", txt) or not re.search(r"[A-Za-z]", txt):
                continue
            if any(sobrepoe(c, q["bbox_pdf"]) for q in cabos):
                continue
            cabos.append({"texto": txt, "principal": txt, "complementos": [], "comprimento": "",
                          "bbox_pdf": tuple(c), "chars": [], "ang": 0.0, "alt": 1.0, "tipo": "cabo",
                          "quadrado": True})
        novos = list(cabos)
        cabos = cabos + antigos
        tr, sol = tracos_dos_caminhos(self.caminhos)
        cores_tr = {}
        soltos, usados_obj = tracejados_soltos(self.page, self.caminhos, cores=cores_tr)
        for k_ in tr:
            cores_tr[k_] = cor_do_objeto(self.page, (k_,), False)
        pecas_soltas = set()
        if soltos:
            tr = dict(tr)
            tr.update(soltos)
            pecas = set(tuple(g) for v in soltos.values() for g in v)
            pecas_soltas = pecas
            sol = [g for g in sol if tuple(g) not in pecas]
        if not tr:
            return False
        rede = Rede(tr, area)
        rede.obj_extra = usados_obj
        if not len(rede.P):
            return False

        def mesma_cor(a, b):
            return a is not None and b is not None and max(abs(x - y) for x, y in zip(a, b)) <= 40
        # cabo escrito como texto (caixa arredondada inclinada, ou sem caixa) ao lado do
        # tracejado da MESMA cor: "3xS4/0-13,8kV", "3#185mm²2-XLPE", "1#4CAA"
        anc_txt = []
        ja_cabo = [q["bbox_pdf"] for q in cabos]
        S_risco, info_risco = self.segs_estilo()
        cores_risco = [i_[0] for i_ in info_risco]
        for txt, bb, cor, cs in palavras_de_texto(self.chars):
            t_ = txt.strip()
            if os.environ.get("DBG_CABO") and re.search(r"kV|S4|#", t_):
                print("palavra", repr(t_), [round(v) for v in bb], cor, "re", bool(RE_CABO_TEXTO.match(t_)),
                      "riscada", palavra_riscada(cs, S_risco, cores_risco, cor), "sobrepoe", any(sobrepoe(bb, b) for b in ja + ja_cabo))
            if not RE_CABO_TEXTO.match(t_) or cor is None:
                continue
            if cor[1] >= 150 and cor[0] < 100 and cor[2] < 100:
                continue                          # verde = rede existente (não entra)
            if palavra_riscada(cs, S_risco, cores_risco, cor):
                continue                          # cabo riscado: existente, a retirar
            # dentro de outro balão (mais da metade do texto): é dele; só encostar não conta
            # (o rótulo inclinado do cabo ao lado da caixa do poste)
            def _cobre(a_, b_):
                ix = min(a_[2], b_[2]) - max(a_[0], b_[0])
                iy = min(a_[3], b_[3]) - max(a_[1], b_[1])
                ar = max((a_[2] - a_[0]) * (a_[3] - a_[1]), 1e-6)
                return ix > 0 and iy > 0 and ix * iy > 0.5 * ar
            if any(_cobre(bb, b) for b in ja + ja_cabo):
                continue
            cx_, cy_ = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2
            if not dentro(cx_, cy_):
                continue
            perto = [(d, i) for d, i in rede.mais_proxima(cx_, cy_, 30) if mesma_cor(cores_tr.get(rede.obj[i]), cor)]
            if not perto and max(cor) < 80:
                # texto preto do cabo (balão preto em cima do traço vermelho): vale o
                # traço colado nele, de qualquer cor menos o verde (rede existente)
                def _verde(c_):
                    return c_ is not None and c_[1] >= 150 and c_[0] < 100 and c_[2] < 100
                perto = [(d, i) for d, i in rede.mais_proxima(cx_, cy_, 15)
                         if cores_tr.get(rede.obj[i]) is not None and not _verde(cores_tr.get(rede.obj[i]))]
            if os.environ.get("DBG_CABO"):
                print("cabo texto", t_, [round(v) for v in bb], cor, "perto", perto[:2],
                      [(round(d, 1), rede.obj[i], cores_tr.get(rede.obj[i])) for d, i in rede.mais_proxima(cx_, cy_, 30)][:3])
            q = {"texto": t_, "principal": t_, "complementos": [], "comprimento": "", "bbox_pdf": tuple(bb),
                 "chars": cs, "ang": 0.0, "alt": 1.0, "tipo": "cabo", "quadrado": True}
            cabos.append(q)
            novos.append(q)
            ja_cabo.append(tuple(bb))
            if perto:
                anc_txt.append((len(cabos) - 1, perto[0][1]))
            # sem tracejado perto: fica pendente; pode estar na linha contínua do cabo
            # (ligada mais abaixo) e só entra se achar a linha dele
        if not cabos:
            return False
        # trecho do cabo desenhado em linha contínua (da mesma cor do tracejado do cabo):
        # cada reta comprida vira uma "linha" a mais do cabo
        cores_com_cabo = {cores_tr.get(rede.obj[p_]) for _, p_ in anc_txt}
        cores_com_cabo.discard(None)
        if cores_com_cabo:
            S_c, info_c = self.segs_estilo()
            caixas_c = [tuple(c) for c in self.caixas] + [tuple(b) for b in ja]
            extra, k_ex = {}, -100000
            for g, (cor_g, _) in zip(S_c, info_c):
                if cor_g not in cores_com_cabo or math.hypot(g[2] - g[0], g[3] - g[1]) < 20:
                    continue
                if any(c[0] - 1 <= min(g[0], g[2]) and max(g[0], g[2]) <= c[2] + 1 and
                       c[1] - 1 <= min(g[1], g[3]) and max(g[1], g[3]) <= c[3] + 1 for c in caixas_c):
                    continue
                if tuple(g) in pecas_soltas:
                    continue
                extra[k_ex] = [tuple(g)]
                cores_tr[k_ex] = cor_g
                k_ex -= 1
            if extra:
                tr = dict(tr)
                tr.update(extra)
                antes = {k: (rede.obj[p_], tuple(rede.P[p_])) for k, p_ in anc_txt}
                rede = Rede(tr, area)
                rede.obj_extra = usados_obj
                idx_n = {(o_, tuple(P_)): i for i, (o_, P_) in enumerate(zip(rede.obj, rede.P))}
                # a ligação com o tracejado continua; a linha contínua só para quem não tinha
                anc_txt = [(k, idx_n[v_]) for k, v_ in antes.items() if v_ in idx_n]
                com_anc = {k for k, _ in anc_txt}
                for k, q in enumerate(cabos):
                    if not q.get("chars") or q.get("tipo") != "cabo" or q not in novos or k in com_anc:
                        continue
                    bb = q["bbox_pdf"]
                    cx_, cy_ = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2
                    cor_q = q["chars"][0].get("cor")
                    perto = [(d, i) for d, i in rede.mais_proxima(cx_, cy_, 30)
                             if mesma_cor(cores_tr.get(rede.obj[i]), cor_q)]
                    if perto:
                        anc_txt.append((k, perto[0][1]))
        # cabo escrito sem a linha da mesma cor por perto (ex.: azul ao lado da rede preta)
        # não se liga pela proximidade
        pend = {k for k, q in enumerate(cabos) if q.get("chars") and q in novos} - {k for k, _ in anc_txt}
        anc = [a_ for a_ in ancoras_de_cabo(rede, cabos, sol, sem_chamada=True)
               if a_[0] not in {k for k, _ in anc_txt} and a_[0] not in pend] + anc_txt
        if not anc:
            return False
        traco = float(np.median(np.hypot(rede.P[:, 2] - rede.P[:, 0], rede.P[:, 3] - rede.P[:, 1])))
        cabo_obj = _cabo_de_cada_linha(rede, {p_: cabos[k]["texto"] for k, p_ in anc},
                                       lim=max(38.0, 4.5 * traco), cores=cores_tr)
        if os.environ.get("DBG_CABO"):
            print("traco", round(traco, 2), "lim", round(max(38.0, 4.5 * traco), 1))
        if os.environ.get("DBG_CABO"):
            for k, p_ in anc:
                print("ancora", cabos[k]["texto"], [round(v) for v in cabos[k]["bbox_pdf"]], "linha", rede.obj[p_],
                      [round(v) for v in rede.P[p_]])
            print("linhas com cabo", cabo_obj)
        # só as linhas que têm cabo (a metragem de outras linhas, como a rede existente,
        # não entra)
        pecas_antes = {p_: (rede.obj[p_], tuple(rede.P[p_])) for _, p_ in anc}
        rede = Rede({k_: v for k_, v in tr.items() if k_ in cabo_obj}, area)
        rede.obj_extra = usados_obj
        if not len(rede.P):
            return False
        idx_novo = {(o_, tuple(P_)): i for i, (o_, P_) in enumerate(zip(rede.obj, rede.P))}
        anc = [(k, idx_novo[(pecas_antes[p_][0], pecas_antes[p_][1])]) for k, p_ in anc
               if (pecas_antes[p_][0], pecas_antes[p_][1]) in idx_novo]
        # área proibida para metros: os balões, as caixas dos cabos e, no cabo lido do texto
        # inclinado, só as letras (o retângulo em volta do texto inclinado é grande demais)
        proibido = ja + [q["bbox_pdf"] for q in cabos if not q.get("chars")] + \
            [(c["l"], c["b"], c["r"], c["t"]) for q in cabos if q.get("chars") for c in q["chars"]]
        angs = [round(math.degrees(c["ang"]) / 90) % 4 * 90 for c in self.chars]
        ang = max(set(angs), key=angs.count) if angs else 0
        rot = self._ler_comprimentos_rede(rede, area, proibido, [q["bbox_pdf"] for q in cabos], ang,
                                          com_traco=True)
        # metro escrito numa linha contínua (ex.: a rede existente) e não no tracejado: fica
        # de fora. Só contam linhas longas (vão de rede), sem bordas de caixas, chamadas e símbolos.
        caixas_ = [tuple(c) for c in self.caixas] + [tuple(b) for b in proibido]
        # só linha contínua de outra cor que a do cabo (a ligação vermelha de um
        # equipamento, por ex., não tira o metro do cabo vermelho)
        S_cor, info_cor = self.segs_estilo()
        cores_cabo = set()
        for o_ in set(rede.obj.tolist()):
            for g in tr.get(o_, [])[:3]:
                d_ = np.hypot(S_cor[:, 0] - g[0], S_cor[:, 1] - g[1]) + np.hypot(S_cor[:, 2] - g[2], S_cor[:, 3] - g[3])
                if len(d_) and d_.min() < 0.5:
                    cores_cabo.add(info_cor[int(np.argmin(d_))][0])
        cor_de = {}
        for k_, g in enumerate(S_cor):
            cor_de[tuple(np.round(g, 2))] = info_cor[k_][0]
        # só linha colorida (rede existente verde, por ex.); cinza e preto são estrada,
        # contorno e cerca, e o metro do cabo costuma estar escrito em cima delas
        def colorida(c_):
            return c_ is not None and max(c_) - min(c_) >= 60
        sol = [g for g in sol if cor_de.get(tuple(np.round(g, 2))) not in cores_cabo
               and colorida(cor_de.get(tuple(np.round(g, 2))))]
        longas = [g for g in sol if math.hypot(g[2] - g[0], g[3] - g[1]) >= 40 and not any(
            c[0] - 1 <= min(g[0], g[2]) and max(g[0], g[2]) <= c[2] + 1 and
            c[1] - 1 <= min(g[1], g[3]) and max(g[1], g[3]) <= c[3] + 1 for c in caixas_)]
        if longas:
            L_ = np.array(longas, float)

            def d_solida(x, y):
                perto = np.nonzero((np.minimum(L_[:, 0], L_[:, 2]) <= x + 40) & (np.maximum(L_[:, 0], L_[:, 2]) >= x - 40) &
                                   (np.minimum(L_[:, 1], L_[:, 3]) <= y + 40) & (np.maximum(L_[:, 1], L_[:, 3]) >= y - 40))[0]
                return min((_dist_seg(x, y, L_[k])[0] for k in perto), default=1e9)
            fica = []
            for r_ in rot:
                dt = rede.mais_proxima(r_[1], r_[2], 45)
                dt = dt[0][0] if dt else 1e9
                if d_solida(r_[1], r_[2]) < 0.7 * dt:
                    if os.environ.get("DBG_METRO"):
                        print("metro na linha contínua", r_, round(d_solida(r_[1], r_[2]), 1), round(dt, 1))
                    continue
                # linha colorida de outra cor passando ENTRE o metro e o cabo: o metro é dela
                # (ex.: "40m" do lado de lá da rede azul existente, com o "32m" do cabo do outro lado)
                cand_ = rede.mais_proxima(r_[1], r_[2], 45)
                if cand_ and d_solida(r_[1], r_[2]) <= 20:
                    g_ = rede.P[cand_[0][1]]
                    vx, vy = g_[2] - g_[0], g_[3] - g_[1]
                    t_ = ((r_[1] - g_[0]) * vx + (r_[2] - g_[1]) * vy) / max(vx * vx + vy * vy, 1e-9)
                    t_ = min(1.0, max(0.0, t_))
                    px, py = g_[0] + t_ * vx, g_[1] + t_ * vy
                    raio = (r_[1], r_[2], px, py)
                    if any(_cruza_seg(raio, L_[k], 0.5) for k in range(len(L_))):
                        if os.environ.get("DBG_METRO"):
                            print("metro atrás de outra linha", r_, round(d_solida(r_[1], r_[2]), 1), round(dt, 1))
                        continue
                fica.append(r_)
            rot = fica
        # metro escrito paralelo a uma linha colorida de outra cor (rede existente) e
        # atravessado ao cabo: é da outra linha (ex.: "10m" ao longo do verde, ao lado do cabo)
        if rot and sol:
            Sg = np.array([g for g in sol if math.hypot(g[2] - g[0], g[3] - g[1]) >= 10], float).reshape(-1, 4)
            pals = [(t_, bb_, cs_) for t_, bb_, _, cs_ in palavras_de_texto(self.chars)
                    if re.fullmatch(r"\d{1,4}\s*[mM]", t_.strip()) and len(cs_) >= 3]

            def ang_seg(g):
                return math.degrees(math.atan2(g[3] - g[1], g[2] - g[0])) % 180

            def dif(a, b):
                d_ = abs(a - b) % 180
                return min(d_, 180 - d_)
            fica = []
            for r_ in rot:
                x, y = r_[1], r_[2]
                pal = next((p_ for p_ in pals if p_[1][0] - 2 <= x <= p_[1][2] + 2 and p_[1][1] - 2 <= y <= p_[1][3] + 2), None)
                cand = rede.mais_proxima(x, y, 45)
                if pal is None or not cand or not len(Sg):
                    fica.append(r_)
                    continue
                pts = np.array([((c["l"] + c["r"]) / 2, (c["b"] + c["t"]) / 2) for c in pal[2]])
                _, _, vt = np.linalg.svd(pts - pts.mean(0), full_matrices=False)
                a_txt = math.degrees(math.atan2(vt[0][1], vt[0][0])) % 180
                a_cabo = ang_seg(rede.P[cand[0][1]])
                ds = [(_dist_seg(x, y, g)[0], g) for g in Sg]
                d_o, g_o = min(ds, key=lambda t: t[0])
                # só texto inclinado (escrito ao longo de uma linha); texto deitado ou em pé é
                # o jeito normal de escrever o metro e não diz de qual linha ele é
                inclinado = dif(a_txt, 0) > 12 and dif(a_txt, 90) > 12
                if inclinado and d_o <= 20 and dif(a_txt, ang_seg(g_o)) < 15 and dif(a_txt, a_cabo) > 30:
                    if os.environ.get("DBG_METRO"):
                        print("metro paralelo a outra linha", r_, round(a_txt), round(ang_seg(g_o)), round(a_cabo))
                    continue
                fica.append(r_)
            rot = fica
        ancp = {p: cabos[k]["texto"] for k, p in anc}
        # cada metro vai para o cabo escrito logo ao lado dele (desenho com a caixa do cabo
        # em todo vão); se não houver, para o cabo da linha do tracejado mais perto
        txt_cabos = [q for q in cabos if q.get("chars") and q.get("tipo") == "cabo"]
        # cabos de cada linha (uma linha tracejada pode levar dois cabos: o 3xS4/0 até o
        # poste e o 3#185 dali em diante) -> o metro fica com o cabo escrito mais perto
        anc_linha = {}
        for k, p_a in anc:
            bb_ = cabos[k]["bbox_pdf"]
            anc_linha.setdefault(rede.obj[p_a], []).append(
                (cabos[k]["texto"], ((bb_[0] + bb_[2]) / 2, (bb_[1] + bb_[3]) / 2)))
        # cabo riscado (existente, a retirar): o metro colado nele é da rede existente
        riscados = []
        for t_r, bb_r, cor_r, cs_r in palavras_de_texto(self.chars):
            if RE_CABO_TEXTO.match(t_r.strip()) and palavra_riscada(cs_r, S_risco, cores_risco, cor_r):
                riscados.append(cs_r)
        tot, det = {}, []
        for v, x, y in rot:
            cand = rede.mais_proxima(x, y, 45)
            if not cand:
                continue
            p_ = cand[0][1]
            nome = cabo_obj.get(rede.obj[p_])
            nomes_l = anc_linha.get(rede.obj[p_], [])
            if len({n_ for n_, _ in nomes_l}) > 1:
                nome = min(nomes_l, key=lambda t: math.hypot(t[1][0] - x, t[1][1] - y))[0]
            d_risc = min((min(math.hypot(max(c["l"] - x, 0, x - c["r"]), max(c["b"] - y, 0, y - c["t"])) for c in cs_r)
                          for cs_r in riscados), default=1e9)
            perto_txt = []
            for q in txt_cabos:
                d_ = min(math.hypot(max(c["l"] - x, 0, x - c["r"]), max(c["b"] - y, 0, y - c["t"])) for c in q["chars"])
                if d_ <= 13:
                    perto_txt.append((d_, q["texto"]))
            if perto_txt:
                nome = min(perto_txt)[1]
            if d_risc <= 8 and (not perto_txt or d_risc < min(perto_txt)[0]):
                if os.environ.get("DBG_CABO"):
                    print("metro do cabo riscado (existente)", v, round(x), round(y), round(d_risc, 1))
                continue
            if os.environ.get("DBG_CABO"):
                print("metro", v, round(x), round(y), "->", nome, "linha", rede.obj[p_], sorted(perto_txt)[:2])
            if not nome:
                continue
            tot[nome] = tot.get(nome, 0) + v
            det.append((v, x, y, [(nome, p_)]))
        self.cabos, self.trechos, self.rede, self.ancoras = tot, det, rede, ancp
        usados = {id(cabos[k]) for k, _ in anc}
        self.baloes = sorted(self.baloes + [q for q in novos if id(q) in usados],
                             key=lambda b: (-round(b["bbox_pdf"][3]), b["bbox_pdf"][0]))
        return True

    def _cabos_pelo_caminho(self, baloes, area):
        """Projetos com balões (vírgula) em que o cabo tem balão próprio com chamada
        até a linha tracejada e os metros estão escritos vão a vão."""
        tr, sol = tracos_dos_caminhos(self.caminhos)
        if not tr:
            return False
        rede = Rede(tr, area)
        if not len(rede.P):
            return False
        # cabo = balão de um item só cuja chamada termina em cima do tracejado
        # (código de cabo tem número: PB35, 1xS04-7,9kV, RAMA25; IBIT, por ex., é do poste)
        simples = [b for b in baloes if not b.get("complementos") and re.search(r"\d", b["texto"])
                   and len([i for i in RE_SEPARA.split(RE_METROS.sub(" ", b["texto"])) if _limpa(i)]) == 1]
        traco = float(np.median(np.hypot(rede.P[:, 2] - rede.P[:, 0], rede.P[:, 3] - rede.P[:, 1])))
        anc = ancoras_de_cabo(rede, simples, sol, raio=max(2.5, 0.6 * traco), sem_chamada=False)
        if len(anc) < 2:
            return False
        # a maioria dos balões de cabo tem que ter a chamada até o tracejado; senão cada
        # balão de cabo fica com os metros escritos do lado dele (ex.: "1xS04-7,9kV" e "80m")
        de_cabo = [b for b in simples if bitolas_do_cabo(b["texto"]) or _familia(b["texto"]) == "MT"
                   or re.search(r"\d\s*[xX]\s*[A-Z0-9]", b["texto"])]
        if len(anc) < 0.7 * len(de_cabo):
            return False
        # a metragem já está nos balões de cabo ("PB70 40M"): vale a do balão; os metros
        # escritos no desenho são de outra rede (ex.: "80m"/"90m" da rede existente)
        com_metros = sum(1 for k, _ in anc if RE_METROS.search(simples[k]["texto"]))
        if com_metros >= 0.5 * len(anc):
            return False
        idx_cabo = {id(simples[k]) for k, _ in anc}
        angs = [round(math.degrees(c["ang"]) / 90) % 4 * 90 for c in self.chars]
        ang = max(set(angs), key=angs.count) if angs else 0
        proibido = [b["bbox_pdf"] for b in baloes]
        caixas_cabo = [b["bbox_pdf"] for b in baloes if id(b) in idx_cabo]
        rot = self._ler_comprimentos_rede(rede, area, proibido, caixas_cabo, ang)
        if not rot:
            return False
        ancp = {p: simples[k]["texto"].replace("\n", " ").strip() for k, p in anc}
        tot, det = distribuir_comprimentos(rede, rot, ancp,
                                           [(simples[k]["texto"], simples[k]["bbox_pdf"]) for k, _ in anc],
                                           lim_viz=max(12.0, 2.5 * traco))
        if not tot:
            return False
        for b in baloes:
            b["tipo"] = "cabo" if id(b) in idx_cabo else None
            b["comprimento"] = ""
            b["texto"] = b["texto"].replace("\n", " ").strip()
        self.cabos, self.trechos, self.rede, self.ancoras = tot, det, rede, ancp
        self.baloes = baloes
        return True

    def _angulo_texto(self, caixas, texto):
        """Direção do texto de traço: a do texto real da página, ou a que lê melhor."""
        angs = [round(math.degrees(c["ang"]) / 90) % 4 * 90 for c in self.chars]
        if angs:
            a = max(set(angs), key=angs.count)
            return a
        vert = sum((c[3] - c[1]) > (c[2] - c[0]) for c in caixas) > len(caixas) / 2
        opcoes = (90, 270) if vert else (0, 180)
        amostra = caixas[:15]
        notas = []
        for a in opcoes:
            ims = [texto.imagem(c, a) for c in amostra]
            sl = estimar_inclinacao_traco(ims)
            notas.append(np.mean([ler_linha_traco(im, sl)[1] for im in ims]) if ims else -9)
        return opcoes[int(np.argmax(notas))]

    def _processar_empilhado(self, area, comprimentos=True):
        """Caixas empilhadas = materiais (1 unidade cada); balões com chamada até
        o tracejado = cabos, com os metros somados ao longo do caminho."""
        pg = np.array(self.poligono, np.float32)
        dentro = lambda x, y: cv2.pointPolygonTest(pg, (float(x), float(y)), False) >= 0
        reais = detectar_baloes(self.page, area, self.chars, page_desenho=self.desenho, page_fino=self.fino,
                                poligono=self.poligono, juntar=False, comprimentos=False)
        tr, sol = tracos_dos_caminhos(self.caminhos)
        rede = Rede(tr, area)
        caixas = [c for c in self.caixas if dentro((c[0] + c[2]) / 2, (c[1] + c[3]) / 2)]

        def sobrepoe(a, b):
            ix = min(a[2], b[2]) - max(a[0], b[0])
            iy = min(a[3], b[3]) - max(a[1], b[1])
            return ix > 0 and iy > 0 and ix * iy > 0.5 * (a[2] - a[0]) * (a[3] - a[1])
        caixas = [c for c in caixas if not any(sobrepoe(c, b["bbox_pdf"]) for b in reais)]
        texto = TextoTraco(self.caminhos, excluir=set(tr))
        ang = self._angulo_texto(caixas, texto)
        imgs = [texto.imagem(c, ang) for c in caixas]
        s = estimar_inclinacao_traco(imgs)
        materiais = []
        pilha = pilhas_de_caixas(caixas)
        for c, im, p in zip(caixas, imgs, pilha):
            txt, nota = ler_linha_traco(im, s)
            txt = txt.strip()
            if txt and nota > 0.3 and re.search(r"[A-Za-z0-9]", txt):
                materiais.append({"texto": txt, "principal": txt, "complementos": [], "bbox_pdf": c,
                                  "comprimento": "", "chars": [], "ang": ang, "alt": 1.0, "tipo": "material",
                                  "pilha": p})
        # cabos: balões de texto real com chamada (ou encostados) no tracejado
        anc = ancoras_de_cabo(rede, reais, sol)
        idx_cabo = {k for k, _ in anc}
        for k, b in enumerate(reais):
            b["texto"] = b["texto"].replace("\n", " ").strip()
            b["principal"] = b["texto"]
            b["tipo"] = "cabo" if k in idx_cabo else "material"
        ancp = {p: reais[k]["texto"] for k, p in anc}
        rot = []
        if comprimentos and ancp:
            proibido = caixas + [b["bbox_pdf"] for b in reais]
            proibido_c = proibido
            caixas_cabo = [reais[k]["bbox_pdf"] for k in idx_cabo]
            for bb, idx in texto.palavras(ang, area):
                cx, cy = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2
                if not dentro(cx, cy) or max(bb[2] - bb[0], bb[3] - bb[1]) > 60:
                    continue
                if any(c[0] + 0.5 <= cx <= c[2] - 0.5 and c[1] + 0.5 <= cy <= c[3] - 0.5 for c in proibido):
                    continue
                perto_balao = any(math.hypot(max(b[0] - cx, 0, cx - b[2]), max(b[1] - cy, 0, cy - b[3])) <= 20
                                  for b in caixas_cabo)
                if not perto_balao and not rede.mais_proxima(cx, cy, 30):
                    continue
                tentativas = [idx]
                # sem pedaços de contorno de balão/caixa e sem traços grandes (chamadas, símbolos)
                Bi = texto.B[idx]
                fora = np.ones(len(idx), bool)
                for c in proibido:
                    fora &= ~((Bi[:, 2] >= c[0] - 1) & (Bi[:, 0] <= c[2] + 1) & (Bi[:, 3] >= c[1] - 1) & (Bi[:, 1] <= c[3] + 1))
                if fora.sum() >= 2 and fora.sum() < len(idx):
                    tentativas.append(idx[fora])
                tam = np.maximum(Bi[:, 2] - Bi[:, 0], Bi[:, 3] - Bi[:, 1])
                if len(idx) > 2:
                    tentativas.append(idx[(tam <= 1.5 * np.median(tam)) & fora])
                for ix in tentativas:
                    achou = False
                    txt, _ = ler_linha_traco(texto.imagem(bb, ang, idx=ix), s)
                    for tk in txt.split():
                        m = re.match(r"^[^\w]?(\d{2,4})m", tk)
                        if m:
                            v = int(m.group(1))
                            if not any(v == r[0] and abs(cx - r[1]) < 15 and abs(cy - r[2]) < 15 for r in rot):
                                rot.append((v, cx, cy))
                            achou = True
                            break
                    if achou:
                        break
        tot, det = distribuir_comprimentos(rede, rot, ancp,
                                           [(reais[k]["texto"], reais[k]["bbox_pdf"]) for k in idx_cabo])
        self.cabos, self.trechos, self.rede, self.ancoras = tot, det, rede, ancp
        todos = materiais + reais
        todos.sort(key=lambda b: (-round(b["bbox_pdf"][3]), b["bbox_pdf"][0]))
        self.baloes = todos


class Arquivo:
    def __init__(self, caminho):
        self.caminho = caminho
        self.nome = os.path.splitext(os.path.basename(caminho))[0]
        self.doc = pdfium.PdfDocument(caminho)
        self.doc_desenho = pdfium.PdfDocument(caminho)   # cópia sem textos e imagens
        self.doc_fino = pdfium.PdfDocument(caminho)      # cópia sem textos e com traço fino
        self.n = len(self.doc)
        self._paginas = {}
        self.formato = "auto"            # auto | virgula | empilhado
        # ajustes feitos à mão na Página inicial (valem para este projeto e ficam guardados)
        self.ajustes = {"remover": set(), "qtd": {}, "add": [], "trocar": {}}
        try:
            mem = PROJETOS.ler(caminho)
            a = mem.get("ajustes", {})
            self.ajustes = {"remover": {tuple(k) for k in a.get("remover", [])},
                            "qtd": {(k0, k1): q for k0, k1, q in a.get("qtd", [])},
                            "add": list(a.get("add", [])),
                            "trocar": {(k0, k1): v for k0, k1, v in a.get("trocar", [])}}
            self._corr_salvas = mem.get("paginas", {})
        except Exception:
            self._corr_salvas = {}

    def pagina(self, idx):
        if idx not in self._paginas:
            pg = Pagina(self, idx)
            c = getattr(self, "_corr_salvas", {}).get(str(idx))
            if c:
                pg.correcoes = {"excluir": list(c.get("excluir", [])), "texto": dict(c.get("texto", {})),
                                "novos": [dict(n) for n in c.get("novos", [])],
                                "rede": dict(c.get("rede", {}))}
                if c.get("cerca"):
                    pg.correcoes["cerca"] = dict(c["cerca"])
            self._paginas[idx] = pg
        return self._paginas[idx]

    def processado(self):
        return all(i in self._paginas and self._paginas[i].baloes is not None for i in range(self.n))

    def relatorio(self):
        itens, extras = [], []
        for i in range(self.n):
            pg = self._paginas.get(i)
            if pg and pg.baloes:
                itens += [((i, k), b) for k, b in enumerate(pg.baloes)]
            if pg and pg.baloes is not None:
                kc = kit_cerca()
                for kt, c in enumerate(pg.cerca_trechos()):
                    if cerca_valida(c) and kc and not c.get("ignorar"):
                        cc = {k_: int(c[k_]) for k_ in ("fios", "aterr", "secc")}
                        itens.append((("cerca", i, kt), {"texto": kc["nome"], "principal": kc["nome"],
                                                         "complementos": [], "comprimento": "",
                                                         "bbox_pdf": (0, 0, 0, 0), "cerca": cc}))
            if pg and pg.baloes is not None:
                for cabo, m in pg.cabos.items():
                    extras.append((cabo, "M", m, ("cabo", i, cabo)))
                sem = sum(m for m, x, y, u in pg.trechos if not u)
                if sem:
                    extras.append(("(METRAGEM SEM CABO IDENTIFICADO)", "M", sem, ("sem", i, None)))
        ctx = {i: contexto_pagina(pg) for i, pg in self._paginas.items() if pg.baloes is not None}
        return aplicar_ajustes(montar_relatorio(itens, extras, contextos=ctx), self.ajustes)
