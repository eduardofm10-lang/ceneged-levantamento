"""Janela principal do programa.

Parte do programa Levantamento de Materiais (Ceneged)."""

import math
import os
import re
import time
import tkinter as tk
from tkinter import filedialog
from tkinter import messagebox
from tkinter import ttk
import numpy as np
from PIL import ImageTk

from ceneged.comum.texto import (_und, chave_nome, formata_num, formata_qtd)
from ceneged.leitura_pdf.deteccao import montar_texto
from ceneged.leitura_pdf.rede import (RE_FIM_DE_REDE, _dist_seg)
from ceneged.dados.cadastro import CADASTRO
from ceneged.dados.composicoes import (COMPOSICOES, _num)
from ceneged.dados.equipes import PROJETOS
from ceneged.dominio.materiais import (contexto_pagina, itens_do_kit)
from ceneged.dominio.cerca import (caixa_do_trecho, cerca_valida, encadear, itens_do_kit_cerca,
    kit_cerca, rotulos_fios)
from ceneged.dominio.relatorio import (agrupar_baloes, chave_linha, materiais_resolvidos)
from ceneged.servicos.exportar import (salvar_relatorio_neo, salvar_relatorio_todos)
from ceneged.servicos.projeto import (Arquivo, MAX_ARQUIVOS, Pagina)
from ceneged.servicos.pdf_corrigido import (baloes_alterados, imagem_pagina_corrigida,
    salvar_pdf_corrigido)
from ceneged.interface.tema import (AZUL, AZUL_CLARO, AZUL_ESC, AZUL_MENU, BORDA, BRANCO,
    CINZA, FONTE, FUNDO, TEXTO, VERMELHO, VERM_ESC, _ICONE_PNG, _LOGO_G_PNG, _LOGO_PNG,
    _imagem, amostra, aplicar_tema, cartao, desenhar_icone, dica_na_tabela, secao, tabela)
from ceneged.interface.dialogos import (EscolherMaterial, JanelaCerca)
from ceneged.interface.tela_cadastro import TelaCadastro
from ceneged.interface.tela_extras import TelaExtras
from ceneged.interface.telas_cadastros import (TelaCarteira, TelaConstantes, TelaEquipes)
from ceneged.interface.login import (TelaUsuarios, TrocarSenha)

class App:
    COR_DELIM = "#e00000"
    FORMATOS = {"Automático": "auto",
                "Balões com vírgula (padrão antigo)": "virgula",
                "Caixas empilhadas + cabos pelo caminho": "empilhado"}
    CORES_CABO = ["#d62728", "#1f77b4", "#2ca02c", "#ff7f0e", "#9467bd", "#8c564b", "#e377c2", "#17becf"]
    TELAS = [("inicio", "Página inicial", "Balões dos projetos elétricos e prévia do relatório"),
             ("cadastro", "Cadastro de materiais", "Nome verdadeiro de cada material"),
             ("extras", "Materiais extras", "Materiais que obrigatoriamente vêm junto"),
             ("constantes", "Constantes (m → KG)", "Materiais em metros que saem em quilos"),
             ("equipes", "Cadastro de equipe", "Supervisores, encarregados, colaboradores e equipes"),
             ("carteira", "Carteira de obra", "Lançamentos e acompanhamento das obras")]
    LARG_MENU = 260

    def __init__(self, root, usuario=None, ao_sair=None):
        self.root = root
        self.usuario = usuario or {"login": "", "nome": "", "admin": True, "editar": True}
        self.pode_editar = bool(self.usuario.get("admin") or self.usuario.get("editar"))
        self.ao_sair = ao_sair
        self.TELAS = list(App.TELAS)
        if self.usuario.get("admin") and ao_sair is not None:
            self.TELAS.append(("usuarios", "Usuários", "Quem pode acessar o programa"))
        root.title("Ceneged · Levantamento de materiais")
        root.minsize(1100, 650)
        aplicar_tema(root)
        self._img_icone = _imagem(_ICONE_PNG)
        if self._img_icone:
            try:
                root.iconphoto(True, self._img_icone)
            except tk.TclError:
                pass
        self._img_logo = _imagem(_LOGO_PNG)
        self._img_logo_g = _imagem(_LOGO_G_PNG)
        self.arquivos = []
        self.arq = None          # arquivo atual
        self.idx = 0             # página atual
        self.zoom = 1.0
        self.giro_extra = 0
        self.modo = None         # None | "ret" | "pol"
        self.pts_pol = []
        self._cache_img = None
        self.rel = []
        self.tela = "inicio"

        # ---------------- cabeçalho
        topo = tk.Frame(root, bg=BRANCO, height=74)
        topo.pack(fill="x")
        topo.pack_propagate(False)
        self.bt_menu = tk.Canvas(topo, width=46, height=46, bg=BRANCO, highlightthickness=0, cursor="hand2")
        self.bt_menu.pack(side="left", padx=(12, 6))
        desenhar_icone(self.bt_menu, "menu", AZUL, 46)
        self.bt_menu.bind("<Button-1>", lambda e: self.alternar_menu())
        self.bt_menu.bind("<Enter>", lambda e: self.bt_menu.config(bg=AZUL_CLARO))
        self.bt_menu.bind("<Leave>", lambda e: self.bt_menu.config(bg=BRANCO))
        if self._img_logo:
            tk.Label(topo, image=self._img_logo, bg=BRANCO).pack(side="left", padx=(6, 0))
        else:
            tk.Label(topo, text="Ceneged", fg=AZUL, bg=BRANCO, font=(FONTE, 20, "bold")).pack(side="left")
        tk.Frame(topo, bg=BORDA, width=1).pack(side="left", fill="y", pady=16, padx=16)
        tit = tk.Frame(topo, bg=BRANCO)
        tit.pack(side="left")
        tk.Label(tit, text="Levantamento de Materiais", fg=AZUL, bg=BRANCO,
                 font=(FONTE, 15, "bold")).pack(anchor="w")
        self.lbl_tela = tk.Label(tit, text="", fg=CINZA, bg=BRANCO, font=(FONTE, 9))
        self.lbl_tela.pack(anchor="w")
        if ao_sair is not None:
            ttk.Button(topo, text="Sair", command=self.sair).pack(side="right", padx=(8, 18))
            nome = self.usuario.get("nome", "")
            av = tk.Canvas(topo, width=38, height=38, bg=BRANCO, highlightthickness=0)
            av.pack(side="right")
            av.create_oval(1, 1, 37, 37, fill=AZUL, outline=AZUL)
            av.create_text(19, 19, text=(nome.strip()[:1] or "?").upper(), fill=BRANCO, font=(FONTE, 13, "bold"))
            caixa = tk.Frame(topo, bg=BRANCO)
            caixa.pack(side="right", padx=(0, 10))
            tk.Label(caixa, text=nome, bg=BRANCO, fg=TEXTO, font=(FONTE, 10, "bold"), anchor="e").pack(anchor="e")
            tk.Label(caixa, text="Administrador" if self.usuario.get("admin") else "Usuário", bg=BRANCO, fg=CINZA,
                     font=(FONTE, 8), anchor="e").pack(anchor="e")
        else:
            tk.Label(topo, text="energia positiva", fg=VERM_ESC, bg=BRANCO,
                     font=(FONTE, 10, "italic")).pack(side="right", padx=20)
        tk.Frame(root, bg=VERMELHO, height=3).pack(fill="x")

        # ---------------- telas
        self.corpo = tk.Frame(root, bg=FUNDO)
        self.corpo.pack(fill="both", expand=True)
        self.tela_inicio = tk.Frame(self.corpo, bg=FUNDO)
        self._montar_inicio(self.tela_inicio)
        self.tela_cadastro = TelaCadastro(self.corpo, self)
        self.tela_extras = TelaExtras(self.corpo, self)
        self.tela_constantes = TelaConstantes(self.corpo, self)
        self.tela_equipes = TelaEquipes(self.corpo, self)
        self.tela_carteira = TelaCarteira(self.corpo, self)
        self.telas = {"inicio": self.tela_inicio, "cadastro": self.tela_cadastro, "extras": self.tela_extras,
                      "equipes": self.tela_equipes, "carteira": self.tela_carteira,
                      "constantes": self.tela_constantes}
        if any(c == "usuarios" for c, _, _ in self.TELAS):
            self.telas["usuarios"] = TelaUsuarios(self.corpo, self)
        self.tela_cadastro.aplicar_permissao(self.pode_editar)
        self.tela_extras.aplicar_permissao(self.pode_editar)
        self.tela_equipes.aplicar_permissao(self.pode_editar)
        self.tela_constantes.aplicar_permissao(self.pode_editar)
        self.tela_carteira.aplicar_permissao(self.pode_editar)
        for t in self.telas.values():
            t.place(x=0, y=0, relwidth=1, relheight=1)
        self._montar_menu()
        self.mostrar("inicio")
        root.bind("<Escape>", self._esc)

    # ---------------- menu lateral
    def _montar_menu(self):
        m = tk.Frame(self.corpo, bg=AZUL_MENU)
        self.menu = m
        self.menu_aberto = False
        card = tk.Frame(m, bg=BRANCO)
        card.pack(fill="x", padx=16, pady=(18, 10))
        if self._img_logo_g:
            tk.Label(card, image=self._img_logo_g, bg=BRANCO).pack(pady=12)
        tk.Label(m, text="MENU", bg=AZUL_MENU, fg="#A9C2E6", font=(FONTE, 8, "bold"),
                 anchor="w").pack(fill="x", padx=22, pady=(14, 6))
        self.itens_menu = {}
        for chave, titulo, _ in self.TELAS:
            it = tk.Frame(m, bg=AZUL_MENU, cursor="hand2")
            it.pack(fill="x", pady=1)
            barra = tk.Frame(it, bg=AZUL_MENU, width=5)
            barra.pack(side="left", fill="y")
            ic = tk.Canvas(it, width=22, height=22, bg=AZUL_MENU, highlightthickness=0)
            ic.pack(side="left", padx=(16, 12), pady=12)
            desenhar_icone(ic, chave, BRANCO)
            tx = tk.Label(it, text=titulo, bg=AZUL_MENU, fg=BRANCO, font=(FONTE, 11), anchor="w")
            tx.pack(side="left", fill="x", expand=True)
            partes = (it, ic, tx)
            for w in partes:
                w.bind("<Button-1>", lambda e, c=chave: self.mostrar(c))
                w.bind("<Enter>", lambda e, c=chave: self._pinta_item(c, True))
                w.bind("<Leave>", lambda e, c=chave: self._pinta_item(c, False))
            self.itens_menu[chave] = (barra, partes)
        if self.ao_sair is not None:
            tk.Label(m, text="MINHA CONTA", bg=AZUL_MENU, fg="#A9C2E6", font=(FONTE, 8, "bold"),
                     anchor="w").pack(fill="x", padx=22, pady=(18, 6))
            for icone, titulo, acao in (("senha", "Trocar minha senha", self.trocar_senha),
                                        ("sair", "Sair", self.sair)):
                it = tk.Frame(m, bg=AZUL_MENU, cursor="hand2")
                it.pack(fill="x", pady=1)
                tk.Frame(it, bg=AZUL_MENU, width=5).pack(side="left", fill="y")
                ic = tk.Canvas(it, width=22, height=22, bg=AZUL_MENU, highlightthickness=0)
                ic.pack(side="left", padx=(16, 12), pady=12)
                desenhar_icone(ic, icone, BRANCO)
                tx = tk.Label(it, text=titulo, bg=AZUL_MENU, fg=BRANCO, font=(FONTE, 11), anchor="w")
                tx.pack(side="left", fill="x", expand=True)
                for w in (it, ic, tx):
                    w.bind("<Button-1>", lambda e, f=acao: (self.alternar_menu(False), f()))
                    w.bind("<Enter>", lambda e, ws=(it, ic, tx): [x.config(bg=AZUL_ESC) for x in ws])
                    w.bind("<Leave>", lambda e, ws=(it, ic, tx): [x.config(bg=AZUL_MENU) for x in ws])
        tk.Label(m, text="Ceneged · energia positiva", bg=AZUL_MENU, fg="#A9C2E6",
                 font=(FONTE, 9, "italic")).pack(side="bottom", pady=14)
        tk.Frame(m, bg=VERMELHO, width=3).place(relx=1, x=-3, y=0, relheight=1, width=3)

    def _pinta_item(self, chave, sobre=False):
        barra, partes = self.itens_menu[chave]
        ativo = chave == self.tela
        bg = AZUL_ESC if (ativo or sobre) else AZUL_MENU
        barra.config(bg=VERMELHO if ativo else bg)
        for w in partes:
            w.config(bg=bg)
        partes[2].config(font=(FONTE, 11, "bold" if ativo else "normal"))

    def alternar_menu(self, abrir=None):
        abrir = (not self.menu_aberto) if abrir is None else abrir
        if abrir == self.menu_aberto:
            return
        self.menu_aberto = abrir
        L = self.LARG_MENU
        passos = [-L + L * (1 - (1 - k / 8) ** 2) for k in range(1, 9)]
        if not abrir:
            passos = [-L * (k / 8) ** 2 for k in range(1, 9)]
        self.menu.place(x=passos[0] if abrir else 0, y=0, relheight=1, width=L)
        self.menu.lift()

        def passo(i=0):
            if not self.menu.winfo_exists():       # janela refeita (saiu do programa)
                return
            if i >= len(passos):
                if not abrir:
                    self.menu.place_forget()
                return
            self.menu.place_configure(x=int(passos[i]))
            self.root.after(14, passo, i + 1)
        passo()

    def _esc(self, _=None):
        if self.menu_aberto:
            self.alternar_menu(False)
        else:
            self.set_modo(None)

    def sair(self):
        if self.ao_sair and messagebox.askyesno("Sair", "Sair do programa e voltar para a tela de login?"):
            self.ao_sair()

    def trocar_senha(self):
        if self.usuario.get("login"):
            TrocarSenha(self.root, self.usuario["login"])

    def mostrar(self, chave):
        if CADASTRO.recarregar_se_mudou():      # outra pessoa alterou o cadastro na pasta compartilhada
            if self.arq:
                self.atualizar_tabelas()
        self.tela = chave
        for c in self.itens_menu:
            self._pinta_item(c)
        tela = self.telas[chave]
        tela.tkraise()
        self.lbl_tela.config(text=next(s for c, _, s in self.TELAS if c == chave))
        if chave == "inicio":
            if self.arq:
                self.atualizar_tabelas()
        else:
            tela.atualizar()
        if self.menu_aberto:
            self.menu.lift()
            self.alternar_menu(False)

    def cadastro_mudou(self):
        """Cadastro ou regras mudaram: refaz nomes, prévia e listas."""
        CADASTRO.mudou()
        COMPOSICOES.mudou()
        if self.arq:
            self.atualizar_tabelas()
        if self.tela == "cadastro":
            self.tela_cadastro.atualizar()
        elif self.tela == "extras":
            self.tela_extras.atualizar()

    def nomes_dos_projetos(self):
        """Nomes de material como vieram nos PDFs abertos (já processados)."""
        nomes = set()
        for a in self.arquivos:
            for pg in a._paginas.values():
                if not pg.baloes:
                    continue
                for o in materiais_resolvidos([((0, k), b) for k, b in enumerate(pg.baloes)], CADASTRO):
                    if o["origem"] in ("projeto", "cabo"):
                        nomes.add(o["original"])
                nomes.update(pg.cabos)
        return nomes

    def nomes_soltos(self):
        """Nomes do projeto sem material principal e sem código no cadastro."""
        return {n for n in self.nomes_dos_projetos()
                if not COMPOSICOES.achar(n) and not CADASTRO.codigo_de(CADASTRO.nome_real(n))}

    # ---------------- página inicial
    def _montar_inicio(self, tela):
        bar = tk.Frame(tela, bg=FUNDO)
        bar.pack(fill="x", padx=10, pady=(10, 0))
        ttk.Button(bar, text="Adicionar PDFs", style="Azul.TButton", command=self.adicionar).pack(side="left")
        ttk.Button(bar, text="Remover", command=self.remover).pack(side="left", padx=(4, 0))
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=10)
        ttk.Button(bar, text="◀", width=3, style="Peq.TButton", command=lambda: self.ir(-1)).pack(side="left")
        self.lbl_pag = ttk.Label(bar, text="-/-", width=7, anchor="center")
        self.lbl_pag.pack(side="left")
        ttk.Button(bar, text="▶", width=3, style="Peq.TButton", command=lambda: self.ir(1)).pack(side="left")
        ttk.Button(bar, text="−", width=3, style="Peq.TButton",
                   command=lambda: self.set_zoom(self.zoom / 1.25)).pack(side="left", padx=(8, 0))
        ttk.Button(bar, text="+", width=3, style="Peq.TButton",
                   command=lambda: self.set_zoom(self.zoom * 1.25)).pack(side="left", padx=(2, 0))
        ttk.Button(bar, text="Ajustar", command=self.ajustar_zoom).pack(side="left", padx=(4, 0))
        ttk.Button(bar, text="Girar 90°", command=self.girar).pack(side="left", padx=(4, 0))
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=10)
        ttk.Label(bar, text="Delimitação:", style="SecaoF.TLabel").pack(side="left")
        ttk.Button(bar, text="Automática", command=self.delim_auto).pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="Retângulo", command=lambda: self.set_modo("ret")).pack(side="left", padx=(4, 0))
        ttk.Button(bar, text="Polígono", command=lambda: self.set_modo("pol")).pack(side="left", padx=(4, 0))
        ttk.Button(bar, text="Exportar relatório", style="Verm.TButton",
                   command=self.exportar).pack(side="right")
        ttk.Button(bar, text="Processar todos", style="Azul.TButton",
                   command=self.processar_todos).pack(side="right", padx=(0, 6))

        bar2 = tk.Frame(tela, bg=FUNDO)
        bar2.pack(fill="x", padx=10, pady=(8, 6))
        self.v_juntar = tk.BooleanVar(value=True)
        self.v_comp = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar2, text="Juntar balões empilhados", variable=self.v_juntar,
                        command=self.reprocessar).pack(side="left")
        ttk.Checkbutton(bar2, text="Comprimentos fora do balão (ex.: 45m)", variable=self.v_comp,
                        command=self.reprocessar).pack(side="left", padx=(12, 0))
        ttk.Label(bar2, text="Tipo de projeto:").pack(side="left", padx=(18, 4))
        self.v_formato = tk.StringVar(value="Automático")
        cb = ttk.Combobox(bar2, textvariable=self.v_formato, state="readonly", width=36,
                          values=list(self.FORMATOS))
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", self.trocar_formato)
        self.status = ttk.Label(bar2, text="Adicione até 10 PDFs.", style="Status.TLabel")
        self.status.pack(side="left", padx=18)

        # ---------------- área principal
        pan = ttk.PanedWindow(tela, orient="horizontal")
        pan.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        esq = cartao(pan)
        secao(esq, f"Arquivos (máx. {MAX_ARQUIVOS})").pack(anchor="w", padx=10, pady=(10, 6))
        self.lst = tk.Listbox(esq, exportselection=False, activestyle="none", width=28, bg=BRANCO, fg=TEXTO,
                              selectbackground=AZUL, selectforeground=BRANCO, relief="flat", bd=0,
                              highlightthickness=0, font=(FONTE, 10))
        self.lst.pack(fill="both", expand=True, padx=8)
        self.lst.bind("<<ListboxSelect>>", self.trocar_arquivo)
        tk.Label(esq, text="✓ = processado", bg=BRANCO, fg=CINZA, font=(FONTE, 8)).pack(anchor="w", padx=10, pady=6)
        pan.add(esq, weight=0)

        frm = cartao(pan)
        self.cv = tk.Canvas(frm, bg="#8B95A7", cursor="fleur", highlightthickness=0)
        sx = ttk.Scrollbar(frm, orient="horizontal", command=self.cv.xview)
        sy = ttk.Scrollbar(frm, orient="vertical", command=self.cv.yview)
        self.cv.configure(xscrollcommand=sx.set, yscrollcommand=sy.set)
        self.cv.grid(row=0, column=0, sticky="nsew")
        sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew")
        frm.rowconfigure(0, weight=1)
        frm.columnconfigure(0, weight=1)
        pan.add(frm, weight=4)

        dir_ = ttk.PanedWindow(pan, orient="vertical")
        cima = cartao(dir_)
        secao(cima, "Balões encontrados (conferência)").pack(anchor="w", padx=10, pady=(10, 6))
        bb = tk.Frame(cima, bg=BRANCO)
        bb.pack(fill="x", padx=10, pady=(0, 6))
        ttk.Button(bb, text="+ Marcar balão", style="Azul.TButton",
                   command=lambda: self.set_modo("balao")).pack(side="left")
        ttk.Button(bb, text="Não é balão", command=self.bal_tirar).pack(side="left", padx=4)
        ttk.Button(bb, text="Corrigir texto", command=self.bal_editar).pack(side="left")
        ttk.Button(bb, text="Fim / meio de rede", command=self.bal_rede).pack(side="left", padx=4)
        ttk.Button(bb, text="Cerca", command=lambda: self.cerca_janela()).pack(side="left")
        ttk.Button(bb, text="Desfazer correções", command=self.bal_desfazer).pack(side="right")
        self.tree = tabela(cima, [("n", "#", 40), ("txt", "Conteúdo do balão", 230),
                                  ("rel", "No relatório (cadastro + extras)", 300)], altura=5)
        self.tree.quadro.pack(fill="both", expand=True, padx=10)
        dica_na_tabela(self.tree, self._dica_balao, largura=640)
        self.lbl_det = tk.Label(cima, text="Clique num balão para ver o que ele leva para o relatório.",
                                bg=BRANCO, fg=CINZA, font=(FONTE, 9), justify="left", anchor="w", wraplength=600)
        self.lbl_det.pack(fill="x", padx=10, pady=(4, 8))
        cima.bind("<Configure>", lambda e: self.lbl_det.config(wraplength=max(e.width - 30, 200)))
        self.tree.tag_configure("extra", background="#FFF6E6")
        self.tree.tag_configure("pend", foreground=VERM_ESC)
        self.tree.bind("<Double-1>", lambda e: self.janela_balao())
        self.tree.bind("<Delete>", lambda e: self.bal_tirar())
        menu_b = tk.Menu(self.root, tearoff=0)
        menu_b.add_command(label="Corrigir texto", command=self.bal_editar)
        menu_b.add_command(label="Não é balão", command=self.bal_tirar)
        menu_b.add_separator()
        menu_b.add_command(label="FLBIT/FLABIT no FIM da rede",
                           command=lambda: self.bal_rede("fim"))
        menu_b.add_command(label="FLBIT/FLABIT no MEIO da rede",
                           command=lambda: self.bal_rede("meio"))
        menu_b.add_command(label="Fim/meio de rede automático (pelo desenho)",
                           command=lambda: self.bal_rede("auto"))
        menu_b.add_separator()
        menu_b.add_command(label="Ver todos os materiais", command=self.janela_balao)

        def menu_bal(e):
            iid = self.tree.identify_row(e.y)
            if iid:
                self.tree.selection_set(iid)
                menu_b.tk_popup(e.x_root, e.y_root)
        self.tree.bind("<Button-3>", menu_bal)
        self.tree.tag_configure("cabo", foreground=AZUL)
        self.tree.bind("<<TreeviewSelect>>", self.sel_balao)
        dir_.add(cima, weight=1)
        baixo = cartao(dir_)
        self.sec_rel = secao(baixo, "Prévia do relatório")
        self.sec_rel.pack(anchor="w", padx=10, pady=(10, 6))
        bts = tk.Frame(baixo, bg=BRANCO)
        bts.pack(fill="x", padx=10, pady=(0, 6))
        ttk.Button(bts, text="+ Adicionar material", style="Azul.TButton",
                   command=self.ajuste_adicionar).pack(side="left")
        ttk.Button(bts, text="Alterar quantidade", command=self.ajuste_qtd).pack(side="left", padx=4)
        ttk.Button(bts, text="Trocar material", command=self.ajuste_trocar).pack(side="left")
        ttk.Button(bts, text="Tirar do relatório", command=self.ajuste_remover).pack(side="left", padx=4)
        ttk.Button(bts, text="Desfazer ajustes", command=self.ajuste_desfazer).pack(side="right")
        leg = tk.Frame(baixo, bg=BRANCO)
        leg.pack(side="bottom", fill="x", padx=10, pady=6)
        amostra(leg, "#F5C77E", "veio de material principal")
        amostra(leg, "#A5D6A7", "ajustado à mão")
        amostra(leg, VERM_ESC, "sem código (dois cliques para dizer o que é)")
        amostra(leg, "#FFC83D", "do balão selecionado")
        self.tree_rel = tabela(baixo, [("cod", "Código", 80), ("mat", "Material", 280), ("qtd", "Quantidade", 90)],
                               altura=5)
        self.tree_rel.quadro.pack(fill="both", expand=True, padx=10)
        dica_na_tabela(self.tree_rel, self._dica_rel)
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Alterar quantidade", command=self.ajuste_qtd)
        menu.add_command(label="Tirar do relatório", command=self.ajuste_remover)
        menu.add_command(label="Trocar material (neste projeto)", command=self.ajuste_trocar)
        menu.add_command(label="Ligar o nome do projeto a um material do cadastro (vale para todos)",
                         command=self.trocar_material)
        menu.add_separator()
        menu.add_command(label="+ Adicionar material", command=self.ajuste_adicionar)
        menu.add_command(label="Desfazer ajustes", command=self.ajuste_desfazer)

        def menu_rel(e):
            iid = self.tree_rel.identify_row(e.y)
            if iid and iid not in self.tree_rel.selection():
                self.tree_rel.selection_set(iid)
            menu.tk_popup(e.x_root, e.y_root)
        self.tree_rel.bind("<Button-3>", menu_rel)
        self.tree_rel.tag_configure("sem_cad", foreground=VERM_ESC)
        self.tree_rel.tag_configure("extra", background="#FFF6E6")
        self.tree_rel.bind("<<TreeviewSelect>>", self.sel_material)
        self.tree_rel.bind("<Double-1>", lambda e: self.resolver_linha())
        self.tree_rel.bind("<Delete>", lambda e: self.ajuste_remover())
        self.tree_rel.tag_configure("manual", background="#E8F5E9")
        self.tree_rel.tag_configure("do_balao", background="#FFC83D", foreground="#1F2937")
        dir_.add(baixo, weight=1)
        pan.add(dir_, weight=2)

        # ---------------- eventos do desenho
        self.cv.bind("<ButtonPress-1>", self.m_press)
        self.cv.bind("<B1-Motion>", self.m_drag)
        self.cv.bind("<ButtonRelease-1>", self.m_release)
        self.cv.bind("<Double-Button-1>", self.m_duplo)
        self.cv.bind("<Button-3>", self.m_duplo)
        self.cv.bind("<Motion>", self.m_move)
        self.cv.bind("<MouseWheel>", self.roda)
        self.cv.bind("<Button-4>", lambda e: self.roda(e, 120))
        self.cv.bind("<Button-5>", lambda e: self.roda(e, -120))

    def msg(self, texto):
        self.status.config(text=texto)
        self.root.update_idletasks()

    # ---------------- arquivos
    def adicionar(self):
        caminhos = filedialog.askopenfilenames(filetypes=[("PDF", "*.pdf")])
        if not caminhos:
            return
        livres = MAX_ARQUIVOS - len(self.arquivos)
        if len(caminhos) > livres:
            messagebox.showwarning("Limite", f"O limite é {MAX_ARQUIVOS} arquivos. "
                                   f"Serão adicionados só {max(livres, 0)}.")
            caminhos = caminhos[:max(livres, 0)]
        ja = {a.caminho for a in self.arquivos}
        for c in caminhos:
            if c in ja:
                continue
            try:
                self.arquivos.append(Arquivo(c))
            except Exception as ex:
                messagebox.showerror("Erro", f"Não consegui abrir {os.path.basename(c)}:\n{ex}")
        self.atualizar_lista()
        if self.arquivos and self.arq is None:
            self.lst.selection_set(0)
            self.trocar_arquivo()

    def remover(self):
        if self.arq is None:
            return
        i = self.arquivos.index(self.arq)
        self.arquivos.pop(i)
        self.arq = None
        self.atualizar_lista()
        self.cv.delete("all")
        self._limpar_tabelas()
        if self.arquivos:
            self.lst.selection_set(min(i, len(self.arquivos) - 1))
            self.trocar_arquivo()

    def atualizar_lista(self):
        sel = self.lst.curselection()
        self.lst.delete(0, "end")
        for a in self.arquivos:
            self.lst.insert("end", ("✓ " if a.processado() else "   ") + a.nome)
        if sel and sel[0] < len(self.arquivos):
            self.lst.selection_set(sel[0])

    def trocar_arquivo(self, _=None):
        sel = self.lst.curselection()
        if not sel:
            return
        self.arq = self.arquivos[sel[0]]
        inv = {v: k for k, v in self.FORMATOS.items()}
        self.v_formato.set(inv.get(self.arq.formato, "Automático"))
        self.idx = 0
        self.carregar_pagina(ajustar=True)

    def ir(self, d):
        if self.arq and 0 <= self.idx + d < self.arq.n:
            self.idx += d
            self.carregar_pagina()

    @property
    def pg(self):
        return self.arq.pagina(self.idx) if self.arq else None

    def carregar_pagina(self, ajustar=False):
        self.set_modo(None)
        self.msg(f"Abrindo {self.arq.nome} (página {self.idx + 1})...")
        pg = self.pg
        self.lbl_pag.config(text=f"{self.idx + 1}/{self.arq.n}")
        if ajustar:
            angs = [round(math.degrees(c["ang"]) / 90) % 4 * 90 for c in pg.chars]
            a = max(set(angs), key=angs.count) if angs else 0
            # texto escrito "para baixo" (90) ou "para cima" (270): gira a vista
            self.giro_extra = ({90: 270, 270: 90, 180: 180}.get(a, 0) - pg.rot) % 360
            self._cache_img = None
            self.ajustar_zoom(redesenhar=False)
        if pg.baloes is None:
            self.processar_pagina(pg, f"{self.arq.nome} (pág. {self.idx + 1})")
        self.atualizar_tabelas()
        self.desenhar()
        # cerca no desenho e ainda não conferida: janela pequena ao lado para conferir
        if getattr(pg, "cerca_auto", None) and not pg.correcoes.get("cerca") and \
                not getattr(pg, "_cerca_perguntada", False):
            pg._cerca_perguntada = True
            self.root.after(300, lambda: self.cerca_janela(pg))
        if not pg.chars:
            aviso = "  ATENÇÃO: página sem texto (só imagem?)."
        elif pg.texto_vetorial:
            aviso = "  (texto lido dos contornos das letras - confira)"
        else:
            aviso = ""
        if pg.formato == "empilhado":
            sem = sum(1 for m, x, y, u in pg.trechos if not u)
            extra = f" {len(pg.trechos)} comprimento(s) lidos no caminho dos cabos" + \
                (f", {sem} sem cabo (marcados '?')" if sem else "") + "."
            self.msg(f"[Caixas empilhadas] {len(pg.baloes)} caixa(s)/balão(ões).{extra} "
                     "Cada cor = um cabo." + aviso)
        else:
            self.msg(f"{len(pg.baloes)} balão(ões) em {self.arq.nome}. "
                     "Confira a delimitação em vermelho." + aviso)

    def processar_pagina(self, pg, nome):
        self.msg(f"Procurando balões em {nome}...")
        self.root.config(cursor="watch")
        self.root.update()
        try:
            pg.processar(self.v_juntar.get(), self.v_comp.get())
        except Exception as ex:
            pg.baloes = []
            messagebox.showerror("Erro", f"Falha ao processar {nome}:\n{ex}")
        finally:
            self.root.config(cursor="")
        self.atualizar_lista()
        if getattr(pg, "aviso_formato", False):
            self.msg(f"{nome}: balões quadrados (fora do formato habitual). "
                     f"Confira a lista; o que faltar, use \"+ Marcar balão\".")

    def trocar_formato(self, _=None):
        if not self.arq:
            return
        self.arq.formato = self.FORMATOS[self.v_formato.get()]
        for p in self.arq._paginas.values():
            p.baloes = None
        self.carregar_pagina()

    def reprocessar(self):
        """Opções mudaram: tudo precisa ser refeito."""
        for a in self.arquivos:
            for p in a._paginas.values():
                p.baloes = None
        if self.arq:
            self.carregar_pagina()

    def processar_todos(self, arquivos=None):
        for a in (arquivos or self.arquivos):
            for i in range(a.n):
                p = a.pagina(i)
                if p.baloes is None:
                    self.processar_pagina(p, f"{a.nome} (pág. {i + 1})")
        self.atualizar_lista()
        if self.arq:
            self.atualizar_tabelas()
            self.desenhar()
        self.msg("Todos os arquivos processados.")

    # ---------------- tabelas da direita
    def _limpar_tabelas(self):
        self.tree.delete(*self.tree.get_children())
        self.tree_rel.delete(*self.tree_rel.get_children())

    def atualizar_tabelas(self):
        self._limpar_tabelas()
        if not self.arq:
            return
        baloes = self.pg.baloes or []
        ctx = contexto_pagina(self.pg)
        # o que cada balão leva para o relatório (cadastro + materiais extras)
        no_rel = {}
        for grupo in agrupar_baloes([((self.idx, k), b) for k, b in enumerate(baloes)]):
            for o in materiais_resolvidos(grupo, ctx=ctx):
                no_rel.setdefault(o["ref"][1], []).append(o)
        self._detalhe = {}
        for i, b in enumerate(baloes):
            t = b["texto"] + ("   [cabo]" if b.get("tipo") == "cabo" else "")
            if b.get("poste_existente"):
                t += f"   [poste existente {b['poste_existente']}]"
            if RE_FIM_DE_REDE.search(b["texto"].upper()):
                pos = b.get("rede_pos")
                t += ("   [FIM de rede" if pos == "fim" else "   [MEIO de rede" if pos == "meio"
                      else "   [meio de rede?") + (" - à mão]" if b.get("rede_manual") else "]")
            partes, det = [], []
            os_ = no_rel.get(i, [])
            for o in os_:
                cod = f"[{o['codigo']}] " if o.get("codigo") else ""
                q = formata_num(o["qtd"]) + (f" {o['un']}" if o["un"] in ("M", "KG") else "")
                if o["origem"] == "coberto":
                    partes.append(f"{o['original']} (já vem no {o['de']})")
                    continue
                if o["origem"] == "est":
                    n = sum(1 for x in os_ if x["origem"] == "estrutura" and o["nome"] in (x.get("de") or ""))
                    partes.append(f"{o['original']} → {o['nome']} ({n} mat.)")
                elif o["origem"] == "estrutura":
                    det.append(f"{cod}{o['nome']} ×{q}" + (f"  ⚠ {o['pendente']}" if o.get("pendente") else ""))
                elif o["origem"] == "extra":
                    partes.append(f"+ {o['nome']}" + (f" ×{q}" if o["qtd"] != 1 else ""))
                elif o["origem"] == "cabo":
                    partes.append(f"{cod}{o['nome']} (metros do caminho)")
                else:
                    partes.append(f"{cod}{o['nome']}" + (f" {q}" if o["un"] == "M" else ""))
            tags = []
            if any(o["origem"] in ("extra", "estrutura") for o in os_):
                tags.append("extra")
            if any(o.get("pendente") for o in os_):
                tags.append("pend")
            if b.get("tipo") == "cabo":
                tags.append("cabo")
            self._detalhe[i] = ";  ".join(partes) + ("   (dois cliques: ver todos os materiais)" if det else "")
            self._mat_balao = getattr(self, "_mat_balao", {})
            self._mat_balao[i] = os_
            self.tree.insert("", "end", iid=str(i), values=(i + 1, t, ";  ".join(partes)), tags=tags)
        self.rel = self.arq.relatorio()
        for i, lin in enumerate(self.rel):
            tags = []
            if lin.get("pendente") or not lin.get("cadastrado", True):
                tags.append("sem_cad")
            if "manual" in lin.get("origens", set()):
                tags.append("manual")
            elif lin.get("origens", set()) & {"extra", "estrutura"}:
                tags.append("extra")
            nome = lin["material"] + (f"   ⚠ {lin['pendente']}" if lin.get("pendente") else "")
            self.tree_rel.insert("", "end", iid=str(i), values=(lin.get("codigo") or "", nome, formata_qtd(lin)),
                                 tags=tags)
        falta = "" if self.arq.processado() else "  (há páginas não processadas)"
        pend = sum(1 for l in self.rel if l.get("pendente"))
        aj = self.arq.ajustes
        n_aj = len(aj["remover"]) + len(aj["qtd"]) + len(aj["add"]) + len(aj.get("trocar", {}))
        self.sec_rel.rotulo.config(text=f"Prévia do relatório — {self.arq.nome}{falta}" +
                                   (f"   ·   {pend} pendência(s)" if pend else "") +
                                   (f"   ·   {n_aj} ajuste(s) à mão" if n_aj else ""))
        if self.tree.selection():
            self.destacar_materiais_do_balao()

    def _dica_rel(self, iid):
        """Texto do balão de dica de uma linha da prévia do relatório."""
        lin = (getattr(self, "rel", None) or [])[int(iid)]
        t = f"{lin.get('codigo') or '(sem código)'}  —  {lin['material']}\nQuantidade: {formata_qtd(lin)}"
        partes = lin.get("partes") or {}
        if partes:
            t += "\nVeio de: " + ", ".join(f"{k} ({formata_num(v)})" for k, v in partes.items())
        if lin.get("pendente"):
            t += f"\n\n⚠ {lin['pendente']}"
            t += ("\n\nO que fazer: botão direito > \"Trocar material\" para escolher o código certo, ou "
                  "\"Tirar do relatório\" se não se aplica.")
        return t

    def _dica_balao(self, iid):
        """Texto do balão de dica de uma linha da lista de balões."""
        i = int(iid)
        b = self.pg.baloes[i]
        t = f"Balão {i + 1}:  {b['texto']}"
        if b.get("poste_existente"):
            t += f"\nPoste existente (etiqueta do desenho): {b['poste_existente']}"
        det = getattr(self, "_detalhe", {}).get(i)
        if det:
            det = det.replace("   (dois cliques: ver todos os materiais)", "")
            t += "\n\nNo relatório:\n• " + "\n• ".join(x for x in det.split(";  ") if x.strip())
        pend = [o for o in getattr(self, "_mat_balao", {}).get(i, []) if o.get("pendente")]
        if pend:
            t += "\n\nPendências:\n" + "\n".join(f"⚠ {o['nome']}: {o['pendente']}" for o in pend)
        t += "\n\n(dois cliques: ver todos os materiais do balão)"
        return t

    def resolver_linha(self):
        """Dois cliques numa linha do relatório: sem código -> dizer o que é; com código -> quantidade."""
        s_ = self.tree_rel.selection()
        if not s_ or not getattr(self, "rel", None):
            return
        lin = self.rel[int(s_[0])]
        if not lin.get("codigo") and not lin["material"].startswith("(") and "manual" not in lin["origens"] \
                and not lin.get("de"):
            self.ligar_nome(lin)
            return
        self.ajuste_qtd()

    def ligar_nome(self, lin):
        """Nome do balão: liga a um material principal (vira os materiais dele) ou a um
        material (com código). Fica guardado para os próximos projetos."""
        nomes = sorted(lin.get("originais") or {lin["material"]}) if isinstance(lin, dict) else [lin]
        nome = ", ".join(nomes)
        if not self.pode_editar:
            messagebox.showinfo("Sem código", f"\"{nome}\" não tem código. Só quem pode alterar o cadastro "
                                              "liga este nome a um material. Fale com o administrador.")
            return
        r = EscolherMaterial(self.root, f"O que é \"{nome}\" no balão?", com_kits=True, com_qtd=False).resultado
        if not r:
            return
        CADASTRO.recarregar_se_mudou()
        COMPOSICOES.recarregar_se_mudou()
        if r["kit"]:
            alvo = next((k for k in COMPOSICOES.kits if k is r["kit"] or
                         (k["id"], k["nome"]) == (r["kit"]["id"], r["kit"]["nome"])), None)
            if alvo is None:
                return
            for n in nomes:
                if chave_nome(n) not in {chave_nome(a) for a in alvo["apelidos"]}:
                    alvo["apelidos"].append(n)
                CADASTRO.de_para.pop(chave_nome(n), None)
            COMPOSICOES.salvar()
            CADASTRO.salvar()
            self.msg(f"\"{nome}\" agora usa os materiais de {alvo['nome']}.")
        else:
            real = r["nome"]
            k = chave_nome(real)
            if k not in {chave_nome(m) for m in CADASTRO.materiais}:
                CADASTRO.materiais.append(real)
            if r["codigo"]:
                CADASTRO.codigos[k] = r["codigo"]
            for n in nomes:
                CADASTRO.de_para[chave_nome(n)] = real
                for kit in COMPOSICOES.kits:                 # deixa de ser apelido de principal
                    kit["apelidos"] = [a for a in kit["apelidos"] if chave_nome(a) != chave_nome(n)]
            CADASTRO.salvar()
            COMPOSICOES.salvar()
            self.msg(f"\"{nome}\" agora é {r['codigo'] or ''} {real}.")
        self.cadastro_mudou()

    def _guardar(self):
        """Guarda as correções e ajustes deste PDF (voltam quando ele for aberto de novo)."""
        if self.arq:
            try:
                PROJETOS.gravar(self.arq)
            except Exception:
                pass

    def trocar_material(self):
        ls = self._linhas_sel()
        if not ls:
            return
        lin = ls[0]
        if not lin.get("originais"):
            messagebox.showinfo("Trocar material", "Este material não veio direto de um balão (veio de um "
                                                   "material principal ou foi adicionado à mão).\n\nPara mudar, "
                                                   "use Materiais extras ou Tirar do relatório.")
            return
        self.ligar_nome(lin)

    # ---------------- ajustes à mão no relatório do projeto
    def _linhas_sel(self):
        s_ = self.tree_rel.selection()
        if not self.arq or not s_ or not getattr(self, "rel", None):
            messagebox.showinfo("Relatório", "Selecione um material na prévia do relatório.")
            return []
        return [self.rel[int(i)] for i in s_]

    def ajuste_adicionar(self):
        if not self.arq:
            messagebox.showinfo("Adicionar material", "Abra um PDF primeiro.")
            return
        r = EscolherMaterial(self.root, f"Adicionar material — {self.arq.nome}", com_kits=True).resultado
        if not r:
            return
        aj = self.arq.ajustes
        kc = kit_cerca()
        if r["kit"] and kc and r["kit"]["nome"] == kc["nome"]:
            # SIT. 01: as quantidades dependem de fios, aterramentos e seccionamentos
            def ok(vals, kit=r["kit"]):
                if not vals:
                    return
                for o in itens_do_kit_cerca(kit, vals, None):
                    a = {"codigo": o["codigo"], "nome": o["nome"], "und": o["un"], "qtd": o["qtd"],
                         "mov": o.get("mov")}
                    k = chave_linha({"codigo": a["codigo"], "material": a["nome"], "unidade": _und(a["und"])})
                    aj["remover"].discard(k)
                    aj["add"].append(a)
                self.atualizar_tabelas()
                self._guardar()
                self.msg(f"Adicionado: {kit['nome']} ({vals['fios']} fios, {vals['aterr']} aterr., "
                         f"{vals['secc']} secc.)")
            JanelaCerca(self.root, {}, None, ok, titulo="Adicionar SIT. 01", com_nao=False)
            return
        novos = itens_do_kit(r["kit"], r["qtd"], None) if r["kit"] else \
            [{"codigo": r["codigo"], "nome": r["nome"], "un": r["und"], "qtd": r["qtd"]}]
        for o in novos:
            a = {"codigo": o["codigo"], "nome": o["nome"], "und": o["un"], "qtd": o["qtd"], "mov": o.get("mov")}
            k = chave_linha({"codigo": a["codigo"], "material": a["nome"], "unidade": _und(a["und"])})
            aj["remover"].discard(k)
            aj["add"].append(a)
        self.atualizar_tabelas()
        self._guardar()
        self.msg(f"Adicionado: {r['nome']}" + (f" ({len(novos)} materiais)" if r["kit"] else ""))

    def ajuste_qtd(self):
        ls = self._linhas_sel()
        if not ls:
            return
        lin = ls[0]
        from tkinter import simpledialog
        v = simpledialog.askstring("Alterar quantidade", f"{lin['material']}\n\nQuantidade ({lin['unidade']}):",
                                   initialvalue=formata_num(lin["qtd"]), parent=self.root)
        if v is None:
            return
        q = _num(v)
        if q is None or q < 0:
            messagebox.showinfo("Alterar quantidade", "Quantidade inválida.")
            return
        k = chave_linha(lin)
        if q == 0:
            self.arq.ajustes["remover"].add(k)
        else:
            self.arq.ajustes["qtd"][k] = q
        self.atualizar_tabelas()
        self._guardar()

    def ajuste_trocar(self):
        """Troca o material de uma linha por outro, com a mesma quantidade (ex.: 5 alças de
        35 mm -> 5 alças de 50 mm). Vale para este projeto e fica guardado."""
        ls = self._linhas_sel()
        if not ls:
            return
        lin = ls[0]
        r = EscolherMaterial(self.root, f"Trocar {formata_qtd(lin)} {lin['unidade']} de \"{lin['material']}\" por",
                             com_kits=False, com_qtd=False).resultado
        if not r:
            return
        aj = self.arq.ajustes
        k = chave_linha(lin)
        # se a linha já era uma troca, troca de novo a partir do material original
        orig = next((ko for ko, v in aj.get("trocar", {}).items()
                     if chave_linha({"codigo": v.get("codigo"), "material": v["nome"],
                                     "unidade": _und(v.get("und") or lin["unidade"])}) == k), k)
        aj.setdefault("trocar", {})[orig] = {"codigo": r["codigo"], "nome": r["nome"],
                                            "und": r.get("und") or lin["unidade"]}
        novo = chave_linha({"codigo": r["codigo"], "material": r["nome"],
                            "unidade": _und(r.get("und") or lin["unidade"])})
        if k in aj["qtd"]:                     # quantidade ajustada vai junto
            aj["qtd"][novo] = aj["qtd"].pop(k)
        self.atualizar_tabelas()
        self._guardar()
        self.msg(f"{lin['material']} trocado por {r['nome']} ({formata_qtd(lin)}). \"Desfazer ajustes\" volta.")

    def ajuste_remover(self):
        ls = self._linhas_sel()
        if not ls:
            return
        aj = self.arq.ajustes
        for lin in ls:
            k = chave_linha(lin)
            aj["remover"].add(k)
            aj["qtd"].pop(k, None)
            aj["add"] = [a for a in aj["add"] if chave_linha({"codigo": a["codigo"], "material": a["nome"],
                                                              "unidade": _und(a["und"])}) != k]
        self.atualizar_tabelas()
        self._guardar()
        self.msg(f"{len(ls)} material(is) tirado(s) do relatório. \"Desfazer ajustes\" volta tudo.")

    def ajuste_desfazer(self):
        if not self.arq:
            return
        aj = self.arq.ajustes
        if not (aj["remover"] or aj["qtd"] or aj["add"] or aj.get("trocar")):
            messagebox.showinfo("Desfazer ajustes", "Não há ajustes à mão neste projeto.")
            return
        if messagebox.askyesno("Desfazer ajustes", "Desfazer todos os ajustes à mão (materiais tirados, "
                                                    "materiais trocados, quantidades e materiais adicionados) deste projeto?"):
            self.arq.ajustes = {"remover": set(), "qtd": {}, "add": [], "trocar": {}}
            self.atualizar_tabelas()
            self._guardar()

    def janela_balao(self):
        """Todos os materiais que o balão leva para o relatório."""
        s_ = self.tree.selection()
        if not s_:
            return
        i = int(s_[0])
        os_ = getattr(self, "_mat_balao", {}).get(i, [])
        w = tk.Toplevel(self.root)
        w.title(f"Balão {i + 1}")
        w.configure(bg=BRANCO)
        w.transient(self.root)
        tk.Frame(w, bg=VERMELHO, height=3).pack(fill="x")
        tk.Label(w, text=f"Balão {i + 1}:  {self.pg.baloes[i]['texto']}", bg=BRANCO, fg=AZUL,
                 font=(FONTE, 12, "bold")).pack(anchor="w", padx=14, pady=(10, 4))
        t = tabela(w, [("cod", "Código", 80), ("mat", "Material", 300), ("q", "Qtd", 60),
                       ("de", "Veio de", 170), ("p", "Pendência", 260)], altura=14)
        t.quadro.pack(fill="both", expand=True, padx=14, pady=(0, 12))
        t.tag_configure("pend", foreground=VERM_ESC)
        t.tag_configure("est", foreground=AZUL)
        dica_na_tabela(t, lambda iid: "\n".join(f"{h}: {v}" for h, v in zip(
            ("Código", "Material", "Qtd", "Veio de", "Pendência"), t.item(iid, "values")) if str(v).strip()))
        for o in os_:
            q = formata_num(o["qtd"]) + (f" {o['un']}" if o["un"] in ("M", "KG") else "")
            if o["origem"] == "coberto":
                t.insert("", "end", values=("", f"{o['original']} — não entra: já vem no {o['de']}", "",
                                            "", ""), tags=("est",))
                continue
            if o["origem"] == "est":
                t.insert("", "end", values=("", f"{o['original']} = material principal {o['nome']}", "",
                                            o["de"], ""),
                         tags=("est",))
                continue
            de = {"projeto": "balão", "cabo": "balão (metros do caminho)",
                  "estrutura": f"principal {o.get('de')}"}.get(o["origem"], "")
            t.insert("", "end", values=(o.get("codigo") or "", o["nome"], "" if o["origem"] == "cabo" else q, de,
                                        o.get("pendente") or ""), tags=("pend",) if o.get("pendente") else ())
        ttk.Button(w, text="Fechar", command=w.destroy).pack(anchor="e", padx=14, pady=(0, 12))
        w.bind("<Escape>", lambda e: w.destroy())

    def sel_balao(self, _=None):
        self.cv.itemconfig("bal", outline="#00b050", width=1)
        for iid in self.tree.selection():
            v = self.tree.item(iid)["values"]
            self.lbl_det.config(text=f"Balão {v[0]}:  {getattr(self, '_detalhe', {}).get(int(iid), v[2])}", fg=TEXTO)
            self.cv.itemconfig(f"b{iid}", outline="#0050ff", width=4)
            self.centralizar(self.pg.baloes[int(iid)]["bbox_pdf"])
        self.destacar_materiais_do_balao()

    def destacar_materiais_do_balao(self):
        """Pinta na prévia do relatório os materiais que vieram dos balões selecionados."""
        sel = {(self.idx, int(i)) for i in self.tree.selection()}
        primeiro = None
        for iid in self.tree_rel.get_children():
            tags = [t for t in self.tree_rel.item(iid, "tags") if t != "do_balao"]
            try:
                lin = self.rel[int(iid)]
            except (AttributeError, IndexError, ValueError):
                continue
            if sel and any(tuple(r) in sel for r in lin.get("refs", []) if len(r) == 2 and r[0] != "cabo"):
                tags = ["do_balao"] + [t for t in tags if t not in ("extra", "manual")]
                primeiro = primeiro or iid
            self.tree_rel.item(iid, tags=tags)
        if primeiro:
            self.tree_rel.see(primeiro)

    def sel_material(self, _=None):
        s_ = self.tree_rel.selection()
        if s_ and getattr(self, "rel", None):
            lin = self.rel[int(s_[0])]
            u = lambda q: formata_num(q) + (f" {lin['unidade']}" if lin["unidade"] in ("M", "KG") else "")
            partes = [(d_, q_) for d_, q_ in lin.get("partes", {}).items() if abs(q_) > 1e-9]
            txt = f"{lin['material']}:  {u(lin['qtd'])}"
            if partes:
                txt += "  =  " + "".join(("" if i == 0 and q_ > 0 else ("  −  " if q_ < 0 else "  +  ")) +
                                         f"{d_} {u(abs(q_))}" for i, (d_, q_) in enumerate(partes))
            self.lbl_det.config(text=txt, fg=AZUL)
        self.cv.itemconfig("bal", outline="#00b050", width=2)
        self.cv.itemconfig("cabo", width=4)
        primeiro = None
        for iid in self.tree_rel.selection():
            for ref in self.rel[int(iid)]["refs"]:
                if ref[0] == "cabo":
                    if ref[1] == self.idx:
                        tag = "cab_" + re.sub(r"\W", "_", ref[2])
                        self.cv.itemconfig(tag, width=9)
                        self.cv.tag_raise(tag)
                    continue
                if ref[0] in ("sem", "cerca"):
                    continue
                pag, k = ref
                if pag == self.idx:
                    self.cv.itemconfig(f"b{k}", outline="#ff8c00", width=4)
                    primeiro = primeiro or self.pg.baloes[k]["bbox_pdf"]
        if primeiro:
            self.centralizar(primeiro)

    def centralizar(self, bbox):
        x0, y0, x1, y1 = self.ret_tela(bbox)
        sr = [float(v) for v in str(self.cv.cget("scrollregion")).split()]
        if len(sr) < 4 or sr[2] <= 0:
            return
        self.cv.xview_moveto(max((x0 + x1) / 2 - self.cv.winfo_width() / 2, 0) / sr[2])
        self.cv.yview_moveto(max((y0 + y1) / 2 - self.cv.winfo_height() / 2, 0) / sr[3])

    # ---------------- zoom / giro / coordenadas
    def girar(self):
        self.giro_extra = (self.giro_extra + 90) % 360
        self._cache_img = None
        self.desenhar()

    def set_zoom(self, z):
        self.zoom = min(max(z, 0.1), 6)
        self.desenhar()

    def ajustar_zoom(self, redesenhar=True):
        if not self.arq:
            return
        self.root.update_idletasks()
        pl, pb, pr, pt = self.pg.page.get_bbox()
        W, H = pr - pl, pt - pb
        if self.giro in (90, 270):
            W, H = H, W
        cw, ch = max(self.cv.winfo_width(), 200), max(self.cv.winfo_height(), 200)
        self.zoom = min(cw / W, ch / H) * 0.98
        if redesenhar:
            self.desenhar()

    def roda(self, e, delta=None):
        delta = delta if delta is not None else e.delta
        if e.state & 0x0004:            # Ctrl + roda = zoom
            self.set_zoom(self.zoom * (1.15 if delta > 0 else 1 / 1.15))
        elif e.state & 0x0001:          # Shift + roda = horizontal
            self.cv.xview_scroll(-1 if delta > 0 else 1, "units")
        else:
            self.cv.yview_scroll(-1 if delta > 0 else 1, "units")

    @property
    def giro(self):
        return (self.pg.rot + self.giro_extra) % 360

    def pdf2tela(self, x, y):
        pl, pb, pr, pt = self.pg.page.get_bbox()
        u, v = (x - pl) * self.zoom, (pt - y) * self.zoom
        W, H = (pr - pl) * self.zoom, (pt - pb) * self.zoom
        g = self.giro
        if g == 90:
            return H - v, u
        if g == 180:
            return W - u, H - v
        if g == 270:
            return v, W - u
        return u, v

    def tela2pdf(self, X, Y):
        pl, pb, pr, pt = self.pg.page.get_bbox()
        W, H = (pr - pl) * self.zoom, (pt - pb) * self.zoom
        g = self.giro
        if g == 90:
            u, v = Y, H - X
        elif g == 180:
            u, v = W - X, H - Y
        elif g == 270:
            u, v = W - Y, X
        else:
            u, v = X, Y
        return pl + u / self.zoom, pt - v / self.zoom

    def ret_tela(self, bbox):
        a = self.pdf2tela(bbox[0], bbox[1])
        b = self.pdf2tela(bbox[2], bbox[3])
        return min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])

    # ---------------- desenho
    def desenhar(self):
        if not self.arq:
            return
        pg = self.pg
        # balões com texto corrigido: a tela mostra o desenho já com o texto novo (igual ao PDF
        # corrigido que sai junto com o relatório)
        alterados = tuple((b.get("texto"), tuple(b["bbox_pdf"])) for b in baloes_alterados(pg)) \
            if pg.baloes is not None else ()
        chave = (id(pg), round(self.zoom, 4), self.giro, alterados)
        if not self._cache_img or self._cache_img[0] != chave:
            img = None
            if alterados:
                try:
                    img = imagem_pagina_corrigida(self.arq, self.idx, pg, self.zoom)
                except Exception:
                    img = None
            if img is None:
                img = pg.page.render(scale=self.zoom).to_pil()
            if self.giro:
                img = img.rotate(-self.giro, expand=True)
            self._cache_img = (chave, ImageTk.PhotoImage(img), img.size)
        _, foto, (w, h) = self._cache_img
        self.cv.delete("all")
        self.cv.create_image(0, 0, image=foto, anchor="nw")
        self.cv.config(scrollregion=(0, 0, w, h))
        # delimitação
        if pg.poligono:
            pts = [c for p in pg.poligono for c in self.pdf2tela(*p)]
            self.cv.create_polygon(*pts, outline=self.COR_DELIM, fill="", width=3, tags="delim")
        # cabos (projetos empilhados): cada vão colorido pelo cabo + comprimento lido
        if pg.rede is not None:
            self.cor_cabo = {}
            for c in sorted(pg.cabos):
                self.cor_cabo[c] = self.CORES_CABO[len(self.cor_cabo) % len(self.CORES_CABO)]
            for m, x, y, u in pg.trechos:
                for c, i in u:
                    if i < 0:
                        continue
                    P = pg.rede.P[i]
                    a, b = self.pdf2tela(P[0], P[1]), self.pdf2tela(P[2], P[3])
                    cor = self.cor_cabo.get(c, "#000")
                    self.cv.create_line(*a, *b, fill=cor, width=4,
                                        tags=("cabo", "cab_" + re.sub(r"\W", "_", c)))
                X, Y = self.pdf2tela(x, y)
                cor = self.cor_cabo.get(u[0][0], "#000") if u else "#ff00ff"
                self.cv.create_text(X, Y, text=f"{m}" + ("" if u else "?"), fill=cor,
                                    font=("Arial", 9, "bold"), tags="rotulo")
            for p_i, c in pg.ancoras.items():
                P = pg.rede.P[p_i]
                X, Y = self.pdf2tela((P[0] + P[2]) / 2, (P[1] + P[3]) / 2)
                self.cv.create_oval(X - 6, Y - 6, X + 6, Y + 6, outline=self.cor_cabo.get(c, "#000"), width=2)
        self._desenhar_cerca()
        # balões
        muitos = pg.formato == "empilhado"
        for i, b in enumerate(pg.baloes or []):
            cabo = b.get("tipo") == "cabo"
            self.cv.create_rectangle(*self.ret_tela(b["bbox_pdf"]), outline="#00b050",
                                     width=2 if (cabo or not muitos) else 1, tags=("bal", f"b{i}"))
            if cabo or not muitos:
                x, y, _, _ = self.ret_tela(b["bbox_pdf"])
                self.cv.create_text(x, y - 2, text=str(i + 1), anchor="sw",
                                    fill="#00a040", font=("Arial", 9, "bold"))
            if b.get("rede_ponto") and b.get("rede_pos"):
                # poste do FLBIT/FLABIT: laranja = fim de rede, azul = meio de rede
                X, Y = self.pdf2tela(*b["rede_ponto"])
                cor = "#ff7a00" if b["rede_pos"] == "fim" else "#0050ff"
                self.cv.create_oval(X - 9, Y - 9, X + 9, Y + 9, outline=cor, width=3, tags="rede_pos")
                self.cv.create_text(X + 11, Y, text="FIM" if b["rede_pos"] == "fim" else "MEIO", anchor="w",
                                    fill=cor, font=("Arial", 8, "bold"), tags="rede_pos")

    def _desenhar_cerca(self):
        ses = getattr(self, "_cerca", None)
        if ses and ses["pg"] is self.pg:
            trechos, atual = ses["trechos"], ses["i"]
        else:
            trechos, atual = self.pg.cerca_trechos(), None
        for k, tr in enumerate(trechos):
            if tr.get("ignorar"):
                continue
            cor = "#FF00FF" if k == atual else "#8B00FF"
            for sg in (tr.get("linha") or []):
                a_, b_ = self.pdf2tela(sg[0], sg[1]), self.pdf2tela(sg[2], sg[3])
                self.cv.create_line(*a_, *b_, fill=cor, width=5 if k == atual else 3, tags="cerca")
            for t, x, y, r in tr.get("pontos", []):
                X, Y = self.pdf2tela(x, y)
                R_ = max(8, r * self.zoom * 1.6)
                self.cv.create_oval(X - R_, Y - R_, X + R_, Y + R_, outline=cor, width=2, tags="cerca")
                self.cv.create_text(X + R_ + 2, Y - R_, text=("ATERR" if t == "A" else "SECC") + f" T{k + 1}",
                                    anchor="w", fill=cor, font=("Arial", 8, "bold"), tags="cerca")
            if tr.get("fios_pos"):
                X, Y = self.pdf2tela(*tr["fios_pos"])
                self.cv.create_text(X, Y - 12, text=f"T{k + 1}: {tr.get('fios') or '?'} fios", fill=cor,
                                    font=("Arial", 9, "bold"), tags="cerca")

    # ---------------- delimitação manual
    def set_modo(self, modo):
        if modo and not self.arq:
            return
        self.modo = modo
        self.pts_pol = []
        self.cv.delete("tmp")
        self.cv.config(cursor="crosshair" if modo else "fleur")
        if modo == "ret":
            self.msg("Arraste para desenhar o retângulo da área do projeto. (Esc cancela)")
        elif modo == "pol":
            self.msg("Clique nos pontos em volta do projeto; duplo clique ou botão direito "
                     "fecha o polígono. (Esc cancela)")
        elif modo == "balao":
            self.msg("Arraste um retângulo em volta do balão que o programa não pegou. (Esc cancela)")

    def _xy(self, e):
        return self.cv.canvasx(e.x), self.cv.canvasy(e.y)

    def m_press(self, e):
        if not self.arq:
            return
        if self.modo == "cerca_dim":
            self.p0 = self._xy(e)
            self.cv.delete("tmp")
            self.cv.create_rectangle(*self.p0, *self.p0, outline="#FF6A00", width=2, dash=(6, 3), tags="tmp")
            return
        if self.modo == "cerca_aum":
            self._cerca_aumentar(*self.tela2pdf(*self._xy(e)))
            return
        if self.modo and str(self.modo).startswith("cerca_"):
            self._cerca_clique(e)
            return
        if self.modo is None:
            self.cv.scan_mark(e.x, e.y)               # arrastar = mover o desenho
        elif self.modo in ("ret", "balao"):
            self.p0 = self._xy(e)
            self.cv.delete("tmp")
            self.cv.create_rectangle(*self.p0, *self.p0, outline=self.COR_DELIM if self.modo == "ret" else "#0050ff",
                                     width=3, dash=(6, 3), tags="tmp")
        elif self.modo == "pol":
            p = self._xy(e)
            if self.pts_pol and math.dist(p, self.pts_pol[-1]) < 4:
                return
            self.pts_pol.append(p)
            self._desenha_pol()

    def m_drag(self, e):
        if self.modo is None and self.arq:
            self.cv.scan_dragto(e.x, e.y, gain=1)
        elif self.modo in ("ret", "balao", "cerca_dim"):
            self.cv.coords("tmp", *self.p0, *self._xy(e))

    def m_release(self, e):
        if self.modo == "cerca_dim":
            p1 = self._xy(e)
            if abs(p1[0] - self.p0[0]) > 4 and abs(p1[1] - self.p0[1]) > 4:
                self._cerca_diminuir(self.p0, p1)
            return
        if self.modo == "balao":
            p1 = self._xy(e)
            if abs(p1[0] - self.p0[0]) > 4 and abs(p1[1] - self.p0[1]) > 4:
                self.bal_marcar(self.p0, p1)
            return
        if self.modo == "ret":
            p1 = self._xy(e)
            if abs(p1[0] - self.p0[0]) > 5 and abs(p1[1] - self.p0[1]) > 5:
                (x0, y0), (x1, y1) = self.p0, p1
                self.finalizar_delim([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])

    def m_move(self, e):
        if self.modo == "pol" and self.pts_pol:
            self.cv.delete("elastico")
            self.cv.create_line(*self.pts_pol[-1], *self._xy(e), fill=self.COR_DELIM,
                                width=2, dash=(4, 3), tags=("tmp", "elastico"))

    def m_duplo(self, e):
        if self.modo == "pol" and len(self.pts_pol) >= 3:
            self.finalizar_delim(self.pts_pol)

    def _desenha_pol(self):
        self.cv.delete("tmp")
        if len(self.pts_pol) > 1:
            self.cv.create_line(*[c for p in self.pts_pol for c in p], fill=self.COR_DELIM,
                                width=3, tags="tmp")
        for x, y in self.pts_pol:
            self.cv.create_oval(x - 3, y - 3, x + 3, y + 3, fill=self.COR_DELIM, outline="", tags="tmp")

    # ---------------- correções de balões feitas à mão
    def _bal_sel(self):
        s_ = self.tree.selection()
        if not self.arq or not s_ or not self.pg.baloes:
            messagebox.showinfo("Balões", "Selecione um balão na lista \"Balões encontrados\".")
            return None
        return self.pg.baloes[int(s_[0])]

    def _bal_refazer(self, msg):
        self.pg.aplicar_correcoes()
        self.atualizar_tabelas()
        self._guardar()
        self.desenhar()
        self.msg(msg)

    def bal_marcar(self, p0, p1):
        self.set_modo(None)
        self.cv.delete("tmp")
        xa, ya = self.tela2pdf(*p0)
        xb, yb = self.tela2pdf(*p1)
        bb = (min(xa, xb), min(ya, yb), max(xa, xb), max(ya, yb))
        cs = [c for c in self.pg.chars if bb[0] <= (c["l"] + c["r"]) / 2 <= bb[2] and
              bb[1] <= (c["b"] + c["t"]) / 2 <= bb[3]]
        txt = montar_texto(cs).replace("\n", ", ").replace(",,", ",") if cs else ""
        from tkinter import simpledialog
        t = simpledialog.askstring("Marcar balão", "Texto do balão (separe os materiais por vírgula; "
                                                   "metros como 80m):", initialvalue=txt, parent=self.root)
        if not t or not t.strip():
            self.desenhar()
            return
        self.pg.correcoes["novos"].append({"texto": t.strip(), "bbox": bb})
        self._bal_refazer(f"Balão marcado: {t.strip()}")

    def bal_tirar(self):
        b = self._bal_sel()
        if not b:
            return
        cor = self.pg.correcoes
        if b.get("manual"):
            cor["novos"] = [n for n in cor["novos"] if tuple(n["bbox"]) != tuple(b["bbox_pdf"])]
        else:
            cor["excluir"].append(Pagina.chave_balao(b))
        self._bal_refazer(f"\"{b['texto'][:40]}\" não é mais balão. (\"Desfazer correções\" volta)")

    def bal_editar(self):
        b = self._bal_sel()
        if not b:
            return
        from tkinter import simpledialog
        t = simpledialog.askstring("Corrigir texto", "Texto do balão (separe os materiais por vírgula; "
                                                     "metros como 80m):", initialvalue=b["texto"], parent=self.root)
        if t is None or not t.strip() or t.strip() == b["texto"]:
            return
        cor = self.pg.correcoes
        if b.get("manual"):
            for n in cor["novos"]:
                if tuple(n["bbox"]) == tuple(b["bbox_pdf"]):
                    n["texto"] = t.strip()
        else:
            cor["texto"][Pagina.chave_balao(b)] = t.strip()
        self._bal_refazer(f"Texto corrigido: {t.strip()}")

    def bal_rede(self, valor=None):
        """FLBIT/FLABIT: marca à mão se o poste é fim de rede (sem conectores) ou meio (com conectores)."""
        b = self._bal_sel()
        if not b:
            return
        if not RE_FIM_DE_REDE.search(b["texto"].upper()):
            messagebox.showinfo("Fim / meio de rede", "Isso vale só para balões com FLBIT ou FLABIT.\n\n"
                                "Com IT-R/ITF-R no mesmo balão: no meio da rede somam os conectores dos dois; "
                                "no fim da rede ficam só os do IT-R/ITF-R. FLBIT/FLABIT sozinho leva os "
                                "conectores dele (materiais extras) no fim ou no meio.")
            return
        if valor is None:                       # botão: alterna fim <-> meio
            valor = "meio" if b.get("rede_pos") == "fim" else "fim"
        cor = self.pg.correcoes.setdefault("rede", {})
        k = Pagina.chave_balao(b)
        if valor == "auto":
            cor.pop(k, None)
        else:
            cor[k] = valor
        auto = {"fim": "fim de rede", "meio": "meio de rede"}.get(b.get("rede_auto"), "não identificado")
        txt = {"fim": "FIM de rede: com IT-R/ITF-R, só os conectores deles",
               "meio": "MEIO de rede: conectores do FLBIT/FLABIT + IT-R/ITF-R",
               "auto": f"automático (pelo desenho: {auto})"}[valor]
        self._bal_refazer(f"\"{b['texto'][:40]}\": {txt}.")

    def cerca_janela(self, pg=None):
        """Conferir / digitar a cerca trecho por trecho (uma janela por trecho)."""
        if not self.arq:
            return
        pg = pg or self.pg
        self._cerca_fechar_janela()
        trechos = [dict(t) for t in pg.cerca_trechos()]
        if not trechos:
            trechos = [{"fios": None, "aterr": None, "secc": None, "pontos": [], "fios_pos": None,
                        "centro": None}]
        for t in trechos:
            t["pontos"] = [tuple(q) for q in t.get("pontos", [])]
        self._cerca = {"pg": pg, "trechos": trechos, "i": 0}
        self._cerca_abrir()

    def _cerca_fechar_janela(self):
        j = getattr(self, "_jan_cerca", None)
        self._jan_cerca = None
        if j is not None:
            try:
                j.destroy()
            except Exception:
                pass
        if self.modo and str(self.modo).startswith("cerca_"):
            self.set_modo(None)

    def _cerca_abrir(self):
        ses = self._cerca
        tr, i, n = ses["trechos"][ses["i"]], ses["i"], len(ses["trechos"])
        auto = {k: tr.get(k) for k in ("fios", "aterr", "secc")}
        self._zoom_no_trecho(tr)
        img = None

        def ok(vals):
            self._jan_cerca = None
            self.set_modo(None)
            if vals is None:                                   # não tem cerca
                ses["pg"].correcoes["cerca"] = {"nao": True}
                return self._cerca_salvar(fim=True)
            tr.update(vals, ok=True, ignorar=False)
            self._cerca_proximo()

        def ignorar():
            self._jan_cerca = None
            self.set_modo(None)
            tr["ignorar"] = True
            self._cerca_proximo()

        def novo():
            ses["trechos"].append({"fios": None, "aterr": None, "secc": None, "pontos": [], "fios_pos": None,
                                   "centro": None})
            self.msg(f"Trecho {len(ses['trechos'])} criado: ele abre depois deste.")
            try:
                self._jan_cerca.title(f"Cerca - trecho {i + 1} de {len(ses['trechos'])}")
            except Exception:
                pass

        def fechar():
            self._jan_cerca = None
            self.set_modo(None)
            self._cerca = None
            self.desenhar()
        self._jan_cerca = JanelaCerca(self.root, tr, auto, ok, titulo=f"Cerca - trecho {i + 1} de {n}",
                                      marcar=self._cerca_marcar, ao_ignorar=ignorar, ao_novo=novo,
                                      ao_fechar=fechar, imagem=img, editar=self._cerca_editar)

    def _cerca_editar(self, acao):
        """Aumentar (clique numa linha: junta o traçado dela), diminuir (arraste um
        retângulo: tira o que estiver dentro) ou apagar a linha da cerca do trecho."""
        ses = getattr(self, "_cerca", None)
        if not ses:
            return
        tr = ses["trechos"][ses["i"]]
        if acao == "apagar":
            tr["linha"] = []
            self._cerca_reatribuir(tr)
            self.desenhar()
            self.msg("Linha da cerca apagada (as figuras e os números continuam). Use Aumentar para marcar outra.")
            return
        self.set_modo("cerca_" + acao)
        self.msg("Clique numa linha da cerca no desenho para juntar ela (segue o tracejado). Esc termina."
                 if acao == "aum" else
                 "Arraste um retângulo sobre a parte da cerca rosa que não é deste trecho. Esc termina.")

    def _cerca_aumentar(self, x, y):
        ses = self._cerca
        tr = ses["trechos"][ses["i"]]
        S, info = ses["pg"].segs_estilo()
        if not len(S):
            return
        tol = max(4.0, 10.0 / max(self.zoom, 0.1))
        mid = (S[:, :2] + S[:, 2:]) / 2
        L = np.hypot(S[:, 2] - S[:, 0], S[:, 3] - S[:, 1])
        perto = np.nonzero(np.hypot(mid[:, 0] - x, mid[:, 1] - y) <= tol + L / 2)[0]
        melhor = min(((_dist_seg(x, y, S[k])[0], k) for k in perto), default=None)
        if not melhor or melhor[0] > tol:
            self.msg("Nenhuma linha aí. Clique em cima da linha da cerca.")
            return
        est = info[melhor[1]]
        idx = np.array([k for k in range(len(S)) if info[k] == est])
        F = S[idx]
        comp = encadear(F)
        alvo = comp[list(idx).index(melhor[1])]
        novos = [tuple(round(float(v), 1) for v in sg) for sg, c_ in zip(F, comp) if c_ == alvo]
        ja = set(map(tuple, tr.get("linha") or []))
        tr["linha"] = [tuple(sg) for sg in (tr.get("linha") or [])] + [sg for sg in novos if sg not in ja]
        self._cerca_reatribuir(tr)
        self.desenhar()

    def _cerca_diminuir(self, p0, p1):
        ses = self._cerca
        tr = ses["trechos"][ses["i"]]
        (xa, ya), (xb, yb) = self.tela2pdf(*p0), self.tela2pdf(*p1)
        x0, x1, y0, y1 = min(xa, xb), max(xa, xb), min(ya, yb), max(ya, yb)
        antes = len(tr.get("linha") or [])
        tr["linha"] = [sg for sg in (tr.get("linha") or [])
                       if not (x0 <= (sg[0] + sg[2]) / 2 <= x1 and y0 <= (sg[1] + sg[3]) / 2 <= y1)]
        if len(tr["linha"]) != antes:
            self._cerca_reatribuir(tr)
        self.cv.delete("tmp")
        self.desenhar()

    def _cerca_reatribuir(self, tr):
        """Depois de mudar a linha da cerca: as figuras e o "N FIOS" que ficam nela."""
        pg = self._cerca["pg"]
        todos = getattr(pg, "_cerca_todos", None) or {"simb": [], "rot": []}
        linha = np.array(tr.get("linha") or [], float).reshape(-1, 4)
        auto = set(tuple(q) for q in todos["simb"])
        manuais = [tuple(q) for q in tr.get("pontos", []) if tuple(q) not in auto]
        if not len(linha):
            return                      # sem linha: as figuras ficam como estão
        pts = []
        if len(linha):
            for q in todos["simb"]:
                d = min(_dist_seg(q[1], q[2], sg)[0] for sg in linha)
                if d <= (1.6 if q[0] == "S" else 4.5) * q[3]:
                    pts.append(tuple(q))
            fios = [(f_, x, y) for f_, x, y in todos["rot"]
                    if min(_dist_seg(x, y, sg)[0] for sg in linha) <= 40]
            if fios:
                vs = [f_ for f_, _, _ in fios]
                tr["fios"] = max(set(vs), key=vs.count)
                tr["fios_pos"] = (fios[0][1], fios[0][2])
        tr["pontos"] = pts + manuais
        for k, t_ in (("aterr", "A"), ("secc", "S")):
            tr[k] = sum(1 for q in tr["pontos"] if q[0] == t_) or None
        if self._jan_cerca:
            for k in ("fios", "aterr", "secc"):
                self._jan_cerca.set_valor(k, tr.get(k))

    def _zoom_no_trecho(self, tr):
        """Mostra a cerca do trecho no desenho: zoom para caber e centraliza."""
        bb = caixa_do_trecho(tr, folga=40.0)
        if bb is None:
            self.desenhar()
            return
        self.root.update_idletasks()
        W, H = bb[2] - bb[0], bb[3] - bb[1]
        if self.giro in (90, 270):
            W, H = H, W
        cw, ch = max(self.cv.winfo_width(), 200), max(self.cv.winfo_height(), 200)
        self.zoom = min(max(min(cw / max(W, 1), ch / max(H, 1)) * 0.9, 0.1), 6)
        self.desenhar()
        self.root.update_idletasks()
        self.centralizar(bb)

    def _cerca_proximo(self):
        ses = self._cerca
        ses["i"] += 1
        if ses["i"] < len(ses["trechos"]):
            self._cerca_abrir()
        else:
            ses["pg"].correcoes["cerca"] = {"trechos": ses["trechos"]}
            self._cerca_salvar()

    def _cerca_salvar(self, fim=True):
        ses = self._cerca
        self._cerca = None
        self.atualizar_tabelas()
        self._guardar()
        self.desenhar()
        trs = ses["pg"].cerca_trechos()
        validos = [t for t in trs if cerca_valida(t) and not t.get("ignorar")]
        if validos and not kit_cerca():
            messagebox.showinfo("Cerca", "Não achei \"SIT. 01 - SECCIONAMENTO + ATERRAMENTOS\" em "
                                         "Materiais extras: cadastre lá para os materiais entrarem.")
        self.msg("Cerca: " + ("; ".join(f"trecho {k + 1}: {t['fios']} fios, {t['aterr']} aterr., {t['secc']} secc."
                                        for k, t in enumerate(trs) if t in validos) or "sem cerca."))

    def _cerca_marcar(self, tipo):
        """tipo: fios | aterr | secc -> cliques no desenho."""
        if not getattr(self, "_cerca", None):
            return
        self.set_modo("cerca_" + tipo)
        self.msg({"fios": "Clique no texto \"N FIOS\" deste trecho.",
                  "aterr": "Clique em cada figura de aterramento de cerca deste trecho (de novo tira). Esc termina.",
                  "secc": "Clique em cada seccionamento deste trecho (de novo tira). Esc termina."}[tipo])

    def _cerca_clique(self, e):
        ses = getattr(self, "_cerca", None)
        if not ses:
            return
        tipo = self.modo[len("cerca_"):]
        x, y = self.tela2pdf(*self._xy(e))
        tr = ses["trechos"][ses["i"]]
        if tipo == "fios":
            perto = [c for c in ses["pg"].chars if math.hypot((c["l"] + c["r"]) / 2 - x, (c["b"] + c["t"]) / 2 - y) <= 30]
            r_ = sorted(rotulos_fios(perto), key=lambda t: math.hypot(t[1] - x, t[2] - y))
            n = r_[0][0] if r_ else None
            if n is None:
                from tkinter import simpledialog
                n = simpledialog.askinteger("Nº de fios", "Quantos fios tem a cerca neste trecho?",
                                            parent=self.root, minvalue=1, maxvalue=99)
            if n:
                tr["fios"], tr["fios_pos"] = n, (x, y)
                if self._jan_cerca:
                    self._jan_cerca.set_valor("fios", n)
            self.set_modo(None)
        else:
            t_ = "A" if tipo == "aterr" else "S"
            tol = 8.0 / max(self.zoom, 0.1)
            perto = [q for q in tr["pontos"] if q[0] == t_ and math.hypot(q[1] - x, q[2] - y) <= max(tol, 3)]
            if perto:
                tr["pontos"].remove(perto[0])
            else:
                tr["pontos"].append((t_, x, y, 2.5))
            n = sum(1 for q in tr["pontos"] if q[0] == t_)
            tr[tipo] = n or None
            if self._jan_cerca:
                self._jan_cerca.set_valor(tipo, n)
        if not tr.get("centro"):
            tr["centro"] = (x, y)
        self.desenhar()

    def bal_desfazer(self):
        if not self.arq:
            return
        cor = self.pg.correcoes
        if not (cor["excluir"] or cor["texto"] or cor["novos"] or cor.get("rede")):
            messagebox.showinfo("Balões", "Não há correções de balões nesta página.")
            return
        if messagebox.askyesno("Balões", "Desfazer as correções de balões desta página (balões tirados, "
                                         "textos corrigidos, balões marcados e fim/meio de rede)?"):
            self.pg.correcoes = {"excluir": [], "texto": {}, "novos": [], "rede": {}}
            self.processar_pagina(self.pg, self.arq.nome)
            self.atualizar_tabelas()
            self._guardar()
            self.desenhar()

    def finalizar_delim(self, pts_tela):
        pg = self.pg
        pg.poligono = [self.tela2pdf(x, y) for x, y in pts_tela]
        pg.manual = True
        self.set_modo(None)
        self.processar_pagina(pg, f"{self.arq.nome} (pág. {self.idx + 1})")
        self.atualizar_tabelas()
        self.desenhar()
        self.msg(f"Delimitação alterada: {len(pg.baloes)} balão(ões).")

    def delim_auto(self):
        if not self.arq:
            return
        pg = self.pg
        pg.poligono = list(pg.poligono_auto)
        pg.manual = False
        self.set_modo(None)
        self.processar_pagina(pg, f"{self.arq.nome} (pág. {self.idx + 1})")
        self.atualizar_tabelas()
        self.desenhar()
        self.msg(f"Delimitação automática: {len(pg.baloes)} balão(ões).")

    # ---------------- exportar
    def exportar(self):
        if not self.arquivos:
            messagebox.showinfo("Exportar", "Adicione pelo menos um PDF.")
            return
        dlg = tk.Toplevel(self.root)
        dlg.title("Exportar relatório")
        dlg.transient(self.root)
        dlg.configure(bg=FUNDO)
        dlg.grab_set()
        tk.Frame(dlg, bg=VERMELHO, height=3).pack(fill="x")
        ttk.Label(dlg, text="Quais arquivos entram no relatório?", style="SecaoF.TLabel",
                  padding=(16, 12, 16, 2)).pack(anchor="w")
        ttk.Label(dlg, text="Formato da Neoenergia: Codigo_Material | Material | Quantidade | … | Situacao (NV).",
                  style="Sub.TLabel", padding=(16, 0, 16, 6)).pack(anchor="w")
        vars_ = []
        fr = ttk.Frame(dlg, padding=(16, 0))
        fr.pack(fill="both", expand=True)
        for a in self.arquivos:
            v = tk.BooleanVar(value=True)
            ttk.Checkbutton(fr, text=a.nome, variable=v).pack(anchor="w")
            vars_.append(v)
        v_modo = tk.StringVar(value="um" if len(self.arquivos) > 1 else "cada")
        fm = ttk.Frame(dlg, padding=(16, 10, 16, 0))
        fm.pack(fill="x")
        ttk.Radiobutton(fm, text="Um arquivo só, com uma aba para cada projeto e a aba TOTAL (soma de todos)",
                        value="um", variable=v_modo).pack(anchor="w")
        ttk.Radiobutton(fm, text="Um arquivo para cada projeto", value="cada", variable=v_modo).pack(anchor="w")
        v_conf = tk.BooleanVar(value=True)
        ttk.Checkbutton(dlg, text="Incluir a aba Conferência (descrição, de onde veio cada material e pendências: "
                                  "é para conferir, não para enviar)",
                        variable=v_conf, padding=(16, 10, 16, 0)).pack(anchor="w")
        v_pdf = tk.BooleanVar(value=True)
        ttk.Checkbutton(dlg, text="Salvar também o projeto em PDF com os balões corrigidos (texto novo no lugar "
                                  "do antigo e contorno vermelho nos balões alterados)",
                        variable=v_pdf, padding=(16, 6, 16, 0)).pack(anchor="w")
        bts = ttk.Frame(dlg, padding=(16, 12))
        bts.pack(fill="x")
        ttk.Button(bts, text="Marcar todos", command=lambda: [v.set(True) for v in vars_]).pack(side="left")
        ttk.Button(bts, text="Desmarcar", command=lambda: [v.set(False) for v in vars_]).pack(side="left", padx=4)

        def ok():
            escolhidos = [a for a, v in zip(self.arquivos, vars_) if v.get()]
            conf = v_conf.get()
            modo = v_modo.get()
            com_pdf = v_pdf.get()
            dlg.destroy()
            if escolhidos:
                self._exportar(escolhidos, conf, modo, com_pdf)

        ttk.Button(bts, text="Exportar", style="Verm.TButton", command=ok).pack(side="right")
        ttk.Button(bts, text="Cancelar", command=dlg.destroy).pack(side="right", padx=4)

    def _pdfs_corrigidos(self, arquivos, pasta):
        """Salva, na pasta do relatório, o PDF de cada projeto com os balões corrigidos.
        -> texto para a mensagem final."""
        salvos, sem, erros = [], [], []
        for a in arquivos:
            if not any(pg.baloes and baloes_alterados(pg) for pg in a._paginas.values()):
                sem.append(a.nome)
                continue
            nome = re.sub(r'[\\/:*?"<>|]', "_", os.path.splitext(a.nome)[0]) + " - baloes corrigidos.pdf"
            cam = os.path.join(pasta, nome)
            try:
                n = salvar_pdf_corrigido(a, cam)
                salvos.append(f"{cam}  ({n} balão(ões) alterado(s))")
            except Exception as ex:
                erros.append(f"{a.nome}: {ex}")
        partes = []
        if salvos:
            partes.append("PDF com os balões corrigidos:\n" + "\n".join(salvos))
        if sem:
            partes.append("Sem balão corrigido (PDF não gerado): " + ", ".join(sem))
        if erros:
            partes.append("Não consegui gerar o PDF de: " + "; ".join(erros) +
                          " (se o PDF estiver aberto, feche e exporte de novo)")
        return "\n\n".join(partes)

    def _exportar(self, arquivos, conferencia=True, modo="cada", com_pdf=True):
        try:
            import openpyxl  # noqa: F401
        except Exception:
            messagebox.showerror("Exportar", "Falta a biblioteca openpyxl (pip install openpyxl).")
            return
        if modo == "um" and len(arquivos) > 1:
            cam = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")],
                                               initialfile=f"Relatorio_{len(arquivos)}_projetos_"
                                                           f"{time.strftime('%Y-%m-%d')}.xlsx")
            if not cam:
                return
            self.processar_todos(arquivos)
            projetos = [(a.nome, a.relatorio()) for a in arquivos]
            pend = sum(1 for _, ls in projetos for l in ls if not l.get("codigo"))
            try:
                salvar_relatorio_todos(cam, projetos, conferencia)
            except Exception as ex:
                messagebox.showerror("Erro ao salvar", f"{ex}\n\nSe a planilha estiver aberta no Excel, feche e "
                                                       "tente de novo.")
                return
            self.msg(f"Relatório salvo: {cam}")
            extra = ("\n\n" + self._pdfs_corrigidos(arquivos, os.path.dirname(cam))) if com_pdf else ""
            messagebox.showinfo("Relatório", f"Planilha salva:\n{cam}\n\n{len(projetos)} projetos (uma aba cada)"
                                             " + aba TOTAL" + (" + aba Conferência" if conferencia else "") + "." +
                                (f"\n\n{pend} linha(s) sem código (em vermelho)." if pend else "") + extra)
            return
        if len(arquivos) == 1:
            cam = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")],
                                               initialfile=arquivos[0].nome + ".xlsx")
            if not cam:
                return
            destinos = {arquivos[0]: cam}
        else:
            pasta = filedialog.askdirectory(title="Pasta onde salvar as planilhas (uma por projeto)")
            if not pasta:
                return
            destinos = {a: os.path.join(pasta, re.sub(r'[\\/:*?"<>|]', "_", a.nome) + ".xlsx") for a in arquivos}
        self.processar_todos(arquivos)              # garante que tudo foi lido
        rels = {a: a.relatorio() for a in arquivos}
        pend = [(a.nome, l) for a in arquivos for l in rels[a] if not l.get("codigo")]
        salvos = []
        try:
            for a, cam in destinos.items():
                salvar_relatorio_neo(cam, rels[a], a.nome if conferencia else None)
                salvos.append(cam)
        except Exception as ex:
            messagebox.showerror("Erro ao salvar", f"{ex}\n\nSe a planilha estiver aberta no Excel, feche e tente de novo.")
            return
        self.msg(f"Relatório salvo: {salvos[0]}")
        extra = ("\n\n" + self._pdfs_corrigidos(arquivos, os.path.dirname(salvos[0]))) if com_pdf else ""
        messagebox.showinfo("Relatório", "Planilha(s) salva(s):\n" + "\n".join(salvos) +
                            (f"\n\n{len(pend)} material(is) sem código (linhas em vermelho na planilha)."
                             if pend else "") + extra)
