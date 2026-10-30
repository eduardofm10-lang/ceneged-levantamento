"""Tela de materiais extras (composições).

Parte do programa Levantamento de Materiais (Ceneged)."""

import re
import tkinter as tk
from tkinter import filedialog
from tkinter import messagebox
from tkinter import ttk

from ceneged.comum.texto import (_sem_acento, _und, chave_nome, formata_num, info_poste,
    normaliza_codigo)
from ceneged.dados.cadastro import CADASTRO
from ceneged.dados.composicoes import (COMPOSICOES, MOVIMENTOS, _RE_COND_POSTE, _num,
    kit_limpo, poste_do_kit, titulo_kit)
from ceneged.dados.planilhas import (UNIDADES, ler_planilha_composicoes,
    salvar_planilha_composicoes)
from ceneged.dados.normativos import (ESTRUTURAS_NORMA, TABELAS_NORMA)
from ceneged.dominio.postes import _linhas_postes
from ceneged.dominio.normativo import (EXPLICA_ESCOLHA, origem_no_normativo)
from ceneged.servicos.normativos import carregar_planilha_normativos
from ceneged.dados.planilhas_normativos import (salvar_modelo_composicoes,
    salvar_modelo_normativos)
from ceneged.interface.tema import (AZUL, BORDA, BRANCO, CINZA, FONTE, FUNDO, LARANJA, TEXTO,
    VERM_ESC, amostra, cartao, secao, tabela)
from ceneged.interface.dialogos import EscolherMaterial
from ceneged.interface.tabelas_norma import JanelaTabelasNorma

class TelaExtras(tk.Frame):
    """Materiais extras: cada material principal (FLBIT, 9600FV, CE3…) e os materiais
    que vêm junto, vindos da planilha 'materiais interligados' e editáveis aqui."""

    # ---- permissão: quem não pode editar só consulta
    def _ed(self, w):
        self.__dict__.setdefault("edicao", []).append(w)
        return w

    def aplicar_permissao(self, pode):
        self.pode = pode
        for w in getattr(self, "edicao", []):
            w.state(["!disabled"] if pode else ["disabled"])
        if not pode and not hasattr(self, "_aviso_leitura"):
            self._aviso_leitura = tk.Label(self, text="Você pode consultar, mas não alterar. "
                                                      "Fale com o administrador.",
                                           bg="#FFF4D6", fg="#7A5600", font=(FONTE, 9), anchor="w", padx=10, pady=6)
            self._aviso_leitura.pack(fill="x", padx=20, pady=(0, 8), after=self.winfo_children()[0])

    def __init__(self, pai, app):
        super().__init__(pai, bg=FUNDO)
        self.app = app
        self.pode = True
        self.atual = None                 # (id, categoria, nome) do principal em edição; None = novo
        self.itens = []
        self.item_sel = None
        cab = tk.Frame(self, bg=FUNDO)
        cab.pack(fill="x", padx=20, pady=(16, 6))
        ttk.Label(cab, text="Materiais extras", style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(cab, style="Sub.TLabel", wraplength=1150, justify="left",
                  text="Quando um material principal aparece no balão (FLBIT, IT-R, 9600FV, PB35…), ele vira os "
                       "materiais que vêm junto, multiplicados pela quantidade lançada (cabos: por metro). "
                       "O que já veio no balão não é repetido.").pack(anchor="w")
        leg = tk.Frame(cab, bg=FUNDO)
        leg.pack(anchor="w", pady=(6, 0))
        amostra(leg, "#00A000", "verde = classificação")
        amostra(leg, "#9DC3E6", "azul claro = material principal")
        amostra(leg, "#C9CED6", "branco = materiais que vêm junto")

        bar = cartao(self)
        bar.pack(fill="x", padx=20, pady=(6, 10))
        b = tk.Frame(bar, bg=BRANCO)
        b.pack(fill="x", padx=12, pady=10)
        self._ed(ttk.Button(b, text="Carregar planilha", style="Azul.TButton",
                            command=self.carregar)).pack(side="left")
        ttk.Button(b, text="Baixar planilha (com as alterações)", command=self.baixar).pack(side="left", padx=6)
        ttk.Button(b, text="Baixar modelo", command=lambda: self.baixar_modelo("composicoes")).pack(side="left")
        self.lbl_info = tk.Label(b, text="", bg=BRANCO, fg=CINZA, font=(FONTE, 9))
        self.lbl_info.pack(side="left", padx=10)
        # 2ª linha: estruturas dos normativos (DIS-NOR-013/014/016/018 + postes DIS-ETE-011)
        tk.Frame(bar, bg=BORDA, height=1).pack(fill="x", padx=12)
        b2 = tk.Frame(bar, bg=BRANCO)
        b2.pack(fill="x", padx=12, pady=10)
        tk.Label(b2, text="Normativos:", bg=BRANCO, fg=TEXTO, font=(FONTE, 9, "bold")).pack(side="left")
        self._ed(ttk.Button(b2, text="Carregar planilha dos normativos",
                            command=self.carregar_normativos)).pack(side="left", padx=6)
        ttk.Button(b2, text="Ver / editar tabelas", command=lambda: self.ver_tabelas()).pack(side="left")
        ttk.Button(b2, text="Baixar modelo", command=lambda: self.baixar_modelo("normativos")).pack(side="left",
                                                                                                   padx=6)
        self.lbl_norma = tk.Label(b2, text="", bg=BRANCO, fg=CINZA, font=(FONTE, 9))
        self.lbl_norma.pack(side="left", padx=6)
        self.v_norma = tk.BooleanVar(value=CADASTRO.config.get("estruturas_normativo", True))
        self._ed(ttk.Checkbutton(b2, text="Usar estruturas dos normativos no relatório", variable=self.v_norma,
                                 command=self.salvar_norma)).pack(side="left", padx=14)
        # poste sem D/DT/C no balão: decide a tabela de postes (DIS-ETE-011); o que ela não
        # resolver usa CADASTRO.config["poste_padrao"] (circular), sem opção na tela

        corpo = tk.Frame(self, bg=FUNDO)
        corpo.pack(fill="both", expand=True, padx=20, pady=(0, 16))
        corpo.columnconfigure(0, weight=2, uniform="x")
        corpo.columnconfigure(1, weight=3, uniform="x")
        corpo.rowconfigure(0, weight=1)

        # ---------------- lista de principais
        esq = cartao(corpo)
        esq.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.sec_lista = secao(esq, "Materiais principais")
        self.sec_lista.pack(anchor="w", padx=14, pady=(12, 6))
        lb = tk.Frame(esq, bg=BRANCO)
        lb.pack(fill="x", padx=14)
        tk.Label(lb, text="Procurar:", bg=BRANCO, fg=CINZA, font=(FONTE, 9)).pack(side="left")
        self.v_busca = tk.StringVar()
        ttk.Entry(lb, textvariable=self.v_busca).pack(side="left", fill="x", expand=True, padx=(6, 0))
        self.v_busca.trace_add("write", lambda *a: self.mostrar_lista())
        fr = tk.Frame(esq, bg=BRANCO)
        fr.pack(fill="both", expand=True, padx=14, pady=(6, 0))
        self.tree = ttk.Treeview(fr, columns=("n",), show="tree headings", height=5)
        self.tree.heading("#0", text="Classificação / principal", anchor="w")
        self.tree.heading("n", text="Materiais")
        self.tree.column("#0", width=300, stretch=True)
        self.tree.column("n", width=80, stretch=False, anchor="center")
        sb = ttk.Scrollbar(fr, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.tag_configure("cat", foreground=BRANCO, background="#1E8E3E", font=(FONTE, 9, "bold"))
        self.tree.tag_configure("manual", foreground=CINZA)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.abrir())
        self.tree.bind("<Double-1>", self._duplo_lista)
        b = tk.Frame(esq, bg=BRANCO)
        b.pack(fill="x", padx=14, pady=8, before=fr)
        self._ed(ttk.Button(b, text="Novo principal", style="Azul.TButton", command=self.novo)).pack(side="left")
        self._ed(ttk.Button(b, text="Duplicar", command=self.duplicar)).pack(side="left", padx=4)
        self._ed(ttk.Button(b, text="Excluir", command=self.excluir)).pack(side="left")
        self._ed(ttk.Button(b, text="Renomear classificação", command=self.renomear_cat)).pack(side="right")

        fs = tk.Frame(esq, bg=BRANCO)
        fs.pack(side="bottom", fill="x", padx=14, pady=(4, 12), before=fr)
        tk.Label(esq, text="Selecione um nome e um principal acima para que esse nome passe a usar os "
                           "materiais dele.", bg=BRANCO, fg=CINZA, font=(FONTE, 8), justify="left",
                 anchor="w", wraplength=420).pack(side="bottom", fill="x", padx=14, before=fr)
        secao(esq, "Nomes dos projetos abertos sem material principal").pack(side="bottom", anchor="w", padx=14,
                                                                            pady=(6, 4), before=fr)
        b.pack_configure(side="bottom", before=fr)
        self.lst_soltos = tk.Listbox(fs, height=3, bg=BRANCO, fg=TEXTO, selectbackground=AZUL,
                                     selectforeground=BRANCO, relief="flat", highlightthickness=1,
                                     highlightbackground=BORDA, font=(FONTE, 9), exportselection=False)
        self.lst_soltos.pack(side="left", fill="x", expand=True)
        self._ed(ttk.Button(fs, text="Ligar ao principal",
                            command=self.ligar_solto)).pack(side="left", padx=(6, 0))

        # ---------------- edição
        ed = cartao(corpo)
        ed.grid(row=0, column=1, sticky="nsew")
        self.sec_ed = secao(ed, "Novo material principal")
        self.sec_ed.pack(anchor="w", padx=14, pady=(12, 8))
        f = tk.Frame(ed, bg=BRANCO)
        f.pack(fill="x", padx=14)
        self.v_id, self.v_nome, self.v_cat = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.v_apel, self.v_auto = tk.StringVar(), tk.BooleanVar(value=True)
        for col, (rot, w) in enumerate((("Código (ex.: RES-0190)", 14), ("Nome do material principal", 30),
                                        ("Classificação", 26))):
            tk.Label(f, text=rot, bg=BRANCO, fg=TEXTO, font=(FONTE, 9, "bold")).grid(row=0, column=col,
                                                                                   sticky="w", padx=(0, 8))
        self._ed(ttk.Entry(f, textvariable=self.v_id, width=14)).grid(row=1, column=0, sticky="we", padx=(0, 8))
        self._ed(ttk.Entry(f, textvariable=self.v_nome)).grid(row=1, column=1, sticky="we", padx=(0, 8))
        self.cb_cat = self._ed(ttk.Combobox(f, textvariable=self.v_cat, width=26))
        self.cb_cat.grid(row=1, column=2, sticky="we")
        f.columnconfigure(1, weight=2)
        f.columnconfigure(2, weight=1)
        tk.Label(f, text="Outros nomes usados nos projetos (separe por vírgula)", bg=BRANCO, fg=TEXTO,
                 font=(FONTE, 9, "bold")).grid(row=2, column=0, columnspan=3, sticky="w", pady=(8, 0))
        self._ed(ttk.Entry(f, textvariable=self.v_apel)).grid(row=3, column=0, columnspan=2, sticky="we",
                                                               padx=(0, 8))
        self._ed(ttk.Checkbutton(f, text="Usar automaticamente nos balões", variable=self.v_auto)).grid(
            row=3, column=2, sticky="w")
        self.lbl_casa = tk.Label(ed, text="", bg=BRANCO, fg=CINZA, font=(FONTE, 8), anchor="w", justify="left",
                                 wraplength=640)
        self.lbl_casa.pack(fill="x", padx=14, pady=(4, 0))
        ed.bind("<Configure>", lambda e: self.lbl_casa.config(wraplength=max(e.width - 30, 200)))

        tk.Label(ed, text="Materiais que vêm junto (quantidade por unidade lançada do principal)", bg=BRANCO,
                 fg=TEXTO, font=(FONTE, 9, "bold")).pack(anchor="w", padx=14, pady=(10, 2))
        self.tree_itens = tabela(ed, [("m", "Material", 280), ("c", "Código", 80), ("u", "UND", 50),
                                      ("q", "Qtd por unid.", 95), ("mv", "Movimento", 140)], altura=4)
        self.tree_itens.quadro.pack(fill="both", expand=True, padx=14)
        self.tree_itens.tag_configure("ret", foreground=LARANJA)
        self.tree_itens.tag_configure("semcod", foreground=VERM_ESC)
        self.tree_itens.bind("<<TreeviewSelect>>", lambda e: self.sel_item())

        fi = tk.Frame(ed, bg=BRANCO)
        self.vi_nome, self.vi_cod = tk.StringVar(), tk.StringVar()
        self.vi_und, self.vi_qtd, self.vi_mov = tk.StringVar(value="CDA"), tk.StringVar(value="1"), \
            tk.StringVar(value=MOVIMENTOS[0])
        for col, rot in enumerate(("Material", "Código", "UND", "Qtd", "Movimento")):
            tk.Label(fi, text=rot, bg=BRANCO, fg=CINZA, font=(FONTE, 8)).grid(row=0, column=col, sticky="w",
                                                                            padx=(0, 6))
        self._ed(ttk.Entry(fi, textvariable=self.vi_nome)).grid(row=1, column=0, sticky="we", padx=(0, 6))
        self._ed(ttk.Entry(fi, textvariable=self.vi_cod, width=11)).grid(row=1, column=1, padx=(0, 6))
        self._ed(ttk.Combobox(fi, textvariable=self.vi_und, values=UNIDADES, width=5)).grid(row=1, column=2,
                                                                                         padx=(0, 6))
        self._ed(ttk.Entry(fi, textvariable=self.vi_qtd, width=8)).grid(row=1, column=3, padx=(0, 6))
        self._ed(ttk.Combobox(fi, textvariable=self.vi_mov, values=MOVIMENTOS, width=19)).grid(row=1, column=4)
        fi.columnconfigure(0, weight=1)
        bi = tk.Frame(ed, bg=BRANCO)
        self._ed(ttk.Button(bi, text="Procurar material…", command=self.procurar_item)).pack(side="left")
        self._ed(ttk.Button(bi, text="Adicionar item", command=self.add_item)).pack(side="left", padx=4)
        self._ed(ttk.Button(bi, text="Atualizar item", command=self.upd_item)).pack(side="left")
        self._ed(ttk.Button(bi, text="Remover item", command=self.del_item)).pack(side="left", padx=4)
        self._ed(ttk.Button(bi, text="Subir", width=6, style="Peq.TButton",
                            command=lambda: self.mover_item(-1))).pack(side="left", padx=(8, 2))
        self._ed(ttk.Button(bi, text="Descer", width=6, style="Peq.TButton",
                            command=lambda: self.mover_item(1))).pack(side="left")
        ttk.Button(bi, text="Tabelas dos normativos", command=self.ver_tabelas).pack(side="right")
        bs = tk.Frame(ed, bg=BRANCO)
        q = self.tree_itens.quadro
        bs.pack(side="bottom", fill="x", padx=14, pady=10, before=q)
        self.fr_orig = tk.Frame(ed, bg="#FFF4D6")
        self.lbl_orig = tk.Label(self.fr_orig, text="", bg="#FFF4D6", fg="#7A5600", font=(FONTE, 9), anchor="w",
                                 justify="left", wraplength=560)
        self.lbl_orig.pack(side="left", fill="x", expand=True, padx=8, pady=5)
        self.bt_orig = ttk.Button(self.fr_orig, text="Ver tabela", command=self.ver_tabela_item)
        self.bt_orig.pack(side="right", padx=6, pady=4)
        self._tab_item = None
        bi.pack(side="bottom", fill="x", padx=14, pady=(6, 0), before=q)
        fi.pack(side="bottom", fill="x", padx=14, pady=(6, 0), before=q)
        self._antes_orig = fi
        self._ed(ttk.Button(bs, text="Salvar alterações", style="Verm.TButton",
                            command=self.salvar)).pack(side="right")
        ttk.Button(bs, text="Desfazer", command=self.desfazer).pack(side="right", padx=6)
        tk.Label(bs, text="Testar nome do balão:", bg=BRANCO, fg=CINZA, font=(FONTE, 9)).pack(side="left")
        self.v_teste = tk.StringVar()
        ttk.Entry(bs, textvariable=self.v_teste, width=14).pack(side="left", padx=4)
        self.lbl_teste = tk.Label(bs, text="", bg=BRANCO, fg=AZUL, font=(FONTE, 9), anchor="w")
        self.lbl_teste.pack(side="left", fill="x", expand=True)
        self.v_teste.trace_add("write", lambda *a: self.testar())
        for v in (self.v_nome, self.v_apel, self.v_auto, self.v_cat):
            v.trace_add("write", lambda *a: self._mostra_casa())
        self.novo(limpar_sel=False)

    # ---------------------------------------------------------------- lista
    def atualizar(self):
        COMPOSICOES.recarregar_se_mudou()
        CADASTRO.recarregar_se_mudou()
        n = len(COMPOSICOES.kits)
        if n:
            self.lbl_info.config(text=f"{n} materiais principais" +
                                 (f"  ·  planilha {COMPOSICOES.arquivo}" if COMPOSICOES.arquivo else "") +
                                 (f"  ·  {COMPOSICOES.carregado}" if COMPOSICOES.carregado else ""), fg=CINZA)
        else:
            self.lbl_info.config(text="Nenhuma planilha carregada: clique em \"Carregar planilha\".",
                                 fg=VERM_ESC)
        self.v_norma.set(CADASTRO.config.get("estruturas_normativo", True))
        self.mostrar_norma()
        self.cb_cat.configure(values=COMPOSICOES.categorias())
        self.mostrar_lista()
        self.mostrar_soltos()

    def _confere(self, k, busca):
        if not busca:
            return True
        txt = chave_nome(" ".join([k["id"], k["nome"], k["categoria"]] + k["apelidos"] +
                                  [i["nome"] + " " + i["codigo"] for i in k["itens"]]))
        return busca in txt

    def mostrar_lista(self):
        aberto = {self.tree.item(i, "text") for i in self.tree.get_children() if self.tree.item(i, "open")}
        self.tree.delete(*self.tree.get_children())
        busca = chave_nome(self.v_busca.get())
        cats = {}
        sel = None
        for idx, k in enumerate(COMPOSICOES.kits):
            if not self._confere(k, busca):
                continue
            c = k["categoria"]
            if c not in cats:
                cats[c] = self.tree.insert("", "end", iid=f"c{len(cats)}", text=c, tags=("cat",),
                                           open=bool(busca) or c in aberto)
            iid = f"k{idx}"
            self.tree.insert(cats[c], "end", iid=iid, text=titulo_kit(k), values=(len(k["itens"]),),
                             tags=() if k["auto"] else ("manual",))
            if self.atual == (k["id"], k["categoria"], k["nome"]):
                sel = iid
        if sel:
            self.tree.item(self.tree.parent(sel), open=True)
            self._sel_prog = True
            self.tree.selection_set(sel)
            self.tree.see(sel)
            self._sel_prog = False
        self.sec_lista.rotulo.config(text=f"Materiais principais ({len(COMPOSICOES.kits)})")

    def mostrar_soltos(self):
        self.lst_soltos.delete(0, "end")
        try:
            soltos = sorted(self.app.nomes_soltos())
        except Exception:
            soltos = []
        for n in soltos:
            self.lst_soltos.insert("end", n)
        if not soltos:
            self.lst_soltos.insert("end", "(nenhum — ou nenhum PDF processado)")

    def _idx(self, chave=None):
        chave = chave or self.atual
        if not chave:
            return None
        for i, k in enumerate(COMPOSICOES.kits):
            if (k["id"], k["categoria"], k["nome"]) == chave:
                return i
        return None

    def _duplo_lista(self, e):
        iid = self.tree.identify_row(e.y)
        if iid.startswith("c"):
            self.renomear_cat(self.tree.item(iid, "text"))
            return "break"

    def abrir(self):
        if getattr(self, "_sel_prog", False):
            return
        s = self.tree.selection()
        if not s or not s[0].startswith("k"):
            return
        k = COMPOSICOES.kits[int(s[0][1:])]
        self.atual = (k["id"], k["categoria"], k["nome"])
        self._carregar_editor(k)

    def _carregar_editor(self, k, titulo=None):
        self.v_id.set(k["id"])
        self.v_nome.set(k["nome"])
        self.v_cat.set(k["categoria"])
        self.v_apel.set(", ".join(k["apelidos"]))
        self.v_auto.set(k["auto"])
        self.itens = [dict(i) for i in k["itens"]]
        self.sec_ed.rotulo.config(text=titulo or f"Material principal: {k['nome']}")
        self.mostrar_itens()
        self._mostra_casa()

    def novo(self, limpar_sel=True):
        self.atual = None
        cat = self.v_cat.get() if limpar_sel else ""
        self._carregar_editor({"id": "", "nome": "", "categoria": cat, "apelidos": [], "auto": True,
                               "itens": []}, "Novo material principal")
        if limpar_sel:
            self.tree.selection_remove(*self.tree.selection())

    def duplicar(self):
        if self.atual is None:
            messagebox.showinfo("Duplicar", "Selecione um material principal na lista.")
            return
        self.atual = None
        self.v_id.set("")
        self.v_nome.set(self.v_nome.get() + " (cópia)")
        self.sec_ed.rotulo.config(text="Novo material principal (cópia)")
        self.tree.selection_remove(*self.tree.selection())

    def desfazer(self):
        i = self._idx()
        if i is None:
            self.novo()
        else:
            self._carregar_editor(COMPOSICOES.kits[i])

    def _mostra_casa(self):
        nome = self.v_nome.get().strip()
        if not nome:
            self.lbl_casa.config(text="")
            return
        nomes = [_RE_COND_POSTE.sub(" ", nome).strip()] + \
            [x.strip() for x in self.v_apel.get().split(",") if x.strip()]
        txt = "Entra quando o balão tiver: " + ", ".join(nomes)
        kp = poste_do_kit({"nome": nome, "categoria": self.v_cat.get(), "itens": self.itens})
        if kp:
            txt += (f"  ·  e nos postes {kp['altura']} m {kp['esforco']} daN"
                    f"{' DT' if kp['tipo'] == 'dt' else ' circular' if kp['tipo'] else ''}"
                    f"{' de fibra (FV)' if kp['fibra'] else ''} (ex.: {kp['altura']}{kp['esforco']}"
                    f"{'D' if kp['tipo'] == 'dt' else 'FV' if kp['fibra'] else ''})")
        m = _RE_COND_POSTE.search(nome)
        if m:
            txt += f"  ·  só quando o poste do balão for circular {m.group(1)}/{m.group(2)}"
        if any(_und(i["und"]) == "M" for i in self.itens) and all(_und(i["und"]) == "M" for i in self.itens):
            txt += "  ·  cabo: quantidade por metro lançado"
        if not self.v_auto.get():
            txt = "Não entra sozinho nos balões (só quando adicionado à mão na Página inicial)."
        self.lbl_casa.config(text=txt)

    def testar(self):
        t = self.v_teste.get().strip()
        if not t:
            self.lbl_teste.config(text="")
            return
        r = COMPOSICOES.achar(t, info_poste(t), CADASTRO.config.get("poste_padrao", "circular"))
        if r:
            k, mult = r
            self.lbl_teste.config(text=f"→ {titulo_kit(k)}" + (f" ×{mult}" if mult != 1 else "") +
                                  f"  ({len(k['itens'])} materiais)", fg=AZUL)
        else:
            cod = CADASTRO.codigo_de(CADASTRO.nome_real(t))
            self.lbl_teste.config(text="→ nenhum principal" + (f" (cadastro: {cod})" if cod else ""), fg=CINZA)

    # ---------------------------------------------------------------- itens
    def mostrar_itens(self):
        self.tree_itens.delete(*self.tree_itens.get_children())
        for n, i in enumerate(self.itens):
            tags = []
            if _sem_acento(i["mov"]).upper().startswith("RETIR"):
                tags.append("ret")
            if not i["codigo"]:
                tags.append("semcod")
            self.tree_itens.insert("", "end", iid=str(n), values=(i["nome"], i["codigo"], i["und"],
                                                                  formata_num(i["qtd"]), i["mov"]), tags=tags)
        self.item_sel = None
        if hasattr(self, "fr_orig"):
            self.fr_orig.pack_forget()

    def sel_item(self):
        s = self.tree_itens.selection()
        if not s:
            return
        self.item_sel = int(s[0])
        i = self.itens[self.item_sel]
        self.mostrar_origem(i)
        self.vi_nome.set(i["nome"])
        self.vi_cod.set(i["codigo"])
        self.vi_und.set(i["und"])
        self.vi_qtd.set(formata_num(i["qtd"]))
        self.vi_mov.set(i["mov"])

    def mostrar_origem(self, i):
        """Item sem código vindo do normativo: diz de qual tabela sai e o que decide."""
        self._tab_item = None
        txt = ""
        if not i.get("codigo"):
            k_ = self._idx()
            kit = COMPOSICOES.kits[k_] if k_ is not None else None
            o = origem_no_normativo(kit, i["nome"])
            if o:
                e, it, chave = o
                t = TABELAS_NORMA.conteudo.get(chave) if chave else None
                ref = it.get("ref") or chave or "normativo"
                if t:
                    self._tab_item = chave
                    txt = (f"Material \"A DEFINIR\" ({e['norma']} – {e['nome']}). Vem de: {ref.replace('Ref.: ', '')}. "
                           f"No relatório é escolhido {EXPLICA_ESCOLHA.get(t.get('modo'), '')}.")
                else:
                    txt = (f"Material \"A DEFINIR\" da {e['norma']} – {e['nome']}: {ref}. "
                           f"{it.get('info') or ''} Não tem tabela no sistema: vem pendente para quem confere.")
            elif kit:
                txt = "Material sem código: confira o código (no relatório ele vem como pendente)."
        if txt:
            self.lbl_orig.config(text=txt)
            if self._tab_item:
                self.bt_orig.pack(side="right", padx=6, pady=4)
            else:
                self.bt_orig.pack_forget()
            self.fr_orig.pack(side="bottom", fill="x", padx=14, pady=(6, 0), before=self._antes_orig)
        else:
            self.fr_orig.pack_forget()

    def ver_tabela_item(self):
        JanelaTabelasNorma(self, self._tab_item, pode=getattr(self, "pode", True))

    def baixar_modelo(self, qual):
        """Modelo vazio (com explicação e exemplo) da planilha de materiais extras ou dos normativos."""
        nome = "Modelo_materiais_extras.xlsx" if qual == "composicoes" else "Modelo_normativos.xlsx"
        cam = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")],
                                           initialfile=nome, title="Salvar modelo")
        if not cam:
            return
        try:
            (salvar_modelo_composicoes if qual == "composicoes" else salvar_modelo_normativos)(cam)
        except Exception as ex:
            messagebox.showerror("Modelo", f"{ex}\n\nSe a planilha estiver aberta no Excel, feche e tente de novo.")
            return
        messagebox.showinfo("Modelo", f"Modelo salvo:\n{cam}\n\nA aba \"Como preencher\" explica cada coluna. "
                                      "As linhas de EXEMPLO não são carregadas.")

    def ver_tabelas(self):
        """Abre as tabelas; com um item "A DEFINIR" selecionado, já na tabela dele."""
        JanelaTabelasNorma(self, self._tab_item if self.item_sel is not None else None,
                           pode=getattr(self, "pode", True))

    def procurar_item(self):
        r = EscolherMaterial(self, "Escolher material", com_kits=False, com_qtd=False).resultado
        if r:
            self.vi_nome.set(r["nome"])
            self.vi_cod.set(r["codigo"])
            self.vi_und.set(r["und"])

    def _item_dos_campos(self):
        nome = re.sub(r"\s+", " ", self.vi_nome.get()).strip()
        q = _num(self.vi_qtd.get())
        if not nome:
            messagebox.showinfo("Item", "Informe o nome do material (ou clique em Procurar material…).")
            return None
        if q is None or q <= 0:
            messagebox.showinfo("Item", "Quantidade inválida.")
            return None
        return {"nome": nome, "codigo": normaliza_codigo(self.vi_cod.get()),
                "und": (self.vi_und.get() or "CDA").strip().upper(), "qtd": q,
                "mov": self.vi_mov.get().strip() or MOVIMENTOS[0]}

    def add_item(self):
        it = self._item_dos_campos()
        if it:
            self.itens.append(it)
            self.mostrar_itens()
            self._mostra_casa()
            self.tree_itens.see(str(len(self.itens) - 1))

    def upd_item(self):
        if self.item_sel is None:
            messagebox.showinfo("Item", "Selecione na tabela o item que quer alterar.")
            return
        it = self._item_dos_campos()
        if it:
            n = self.item_sel
            self.itens[n] = it
            self.mostrar_itens()
            self.tree_itens.selection_set(str(n))

    def del_item(self):
        s = self.tree_itens.selection()
        if not s:
            return
        for n in sorted((int(x) for x in s), reverse=True):
            self.itens.pop(n)
        self.mostrar_itens()
        self._mostra_casa()

    def mover_item(self, d):
        s = self.tree_itens.selection()
        if not s:
            return
        n = int(s[0])
        m = n + d
        if 0 <= m < len(self.itens):
            self.itens[n], self.itens[m] = self.itens[m], self.itens[n]
            self.mostrar_itens()
            self.tree_itens.selection_set(str(m))

    # ---------------------------------------------------------------- gravar
    def _gravar(self, mudar):
        """Relê o arquivo (outra pessoa pode ter mudado), aplica a mudança e salva."""
        COMPOSICOES.recarregar_se_mudou()
        r = mudar()
        if r is False:
            return False
        COMPOSICOES.salvar()
        self.app.cadastro_mudou()
        return True

    def salvar(self):
        nome = re.sub(r"\s+", " ", self.v_nome.get()).strip()
        if not nome:
            messagebox.showinfo("Salvar", "Informe o nome do material principal.")
            return
        if not self.itens and not messagebox.askyesno("Salvar", "Este principal não tem nenhum material. "
                                                                "Salvar mesmo assim?"):
            return
        kit = kit_limpo({"id": self.v_id.get().strip().upper(), "nome": nome,
                         "categoria": self.v_cat.get().strip() or "SEM CLASSIFICAÇÃO",
                         "apelidos": [x.strip() for x in self.v_apel.get().split(",") if x.strip()],
                         "auto": self.v_auto.get(), "itens": self.itens})
        anterior = self.atual

        def mudar():
            lst = COMPOSICOES.kits
            i = self._idx(anterior)
            if anterior and i is None:
                if not messagebox.askyesno("Salvar", "Este principal foi alterado ou excluído por outra pessoa. "
                                                     "Salvar como novo?"):
                    return False
            if i is not None:
                if lst[i]["categoria"] == kit["categoria"]:
                    lst[i] = kit
                    return
                lst.pop(i)
            pos = max((j for j, k in enumerate(lst) if k["categoria"] == kit["categoria"]), default=len(lst) - 1)
            lst.insert(pos + 1, kit)

        if self._gravar(mudar):
            self.atual = (kit["id"], kit["categoria"], kit["nome"])
            self.mostrar_lista()
            self.sec_ed.rotulo.config(text=f"Material principal: {kit['nome']}")
            self.app.msg(f"Material principal \"{kit['nome']}\" salvo.")

    def excluir(self):
        i = self._idx()
        if i is None:
            messagebox.showinfo("Excluir", "Selecione um material principal na lista.")
            return
        k = COMPOSICOES.kits[i]
        if not messagebox.askyesno("Excluir", f"Excluir o material principal \"{titulo_kit(k)}\" e os "
                                              f"{len(k['itens'])} materiais dele?"):
            return
        chave = self.atual

        def mudar():
            j = self._idx(chave)
            if j is not None:
                COMPOSICOES.kits.pop(j)
        if self._gravar(mudar):
            self.novo()
            self.mostrar_lista()

    def renomear_cat(self, atual=None):
        if not atual:
            s = self.tree.selection()
            if s and s[0].startswith("c"):
                atual = self.tree.item(s[0], "text")
            elif s:
                atual = COMPOSICOES.kits[int(s[0][1:])]["categoria"]
        if not atual or not self.pode:
            return
        from tkinter import simpledialog
        novo = simpledialog.askstring("Renomear classificação", f"Novo nome para \"{atual}\":",
                                      initialvalue=atual, parent=self)
        if not novo or not novo.strip() or novo.strip() == atual:
            return
        novo = novo.strip()

        def mudar():
            for k in COMPOSICOES.kits:
                if k["categoria"] == atual:
                    k["categoria"] = novo
        if self._gravar(mudar):
            if self.atual and self.atual[1] == atual:
                self.atual = (self.atual[0], novo, self.atual[2])
                self.v_cat.set(novo)
            self.atualizar()

    def ligar_solto(self):
        s = self.lst_soltos.curselection()
        i = self._idx()
        if not s or self.lst_soltos.get(s[0]).startswith("("):
            messagebox.showinfo("Ligar", "Selecione um nome na lista de nomes sem material principal.")
            return
        if i is None:
            messagebox.showinfo("Ligar", "Selecione na lista de cima o material principal que esse nome usa.")
            return
        nome = self.lst_soltos.get(s[0])
        chave = self.atual

        def mudar():
            j = self._idx(chave)
            if j is None:
                return False
            if chave_nome(nome) not in {chave_nome(a) for a in COMPOSICOES.kits[j]["apelidos"]}:
                COMPOSICOES.kits[j]["apelidos"].append(nome)
        if self._gravar(mudar):
            self.v_apel.set(", ".join(COMPOSICOES.kits[self._idx()]["apelidos"]))
            self.mostrar_soltos()

    def mostrar_norma(self):
        ne = len(ESTRUTURAS_NORMA.conteudo)
        nt = len([k for k in TABELAS_NORMA.conteudo if not k.startswith("DIS-ETE-011|")])
        npo = len(_linhas_postes())
        self.lbl_norma.config(text=(f"carregados: {ne} estruturas, {nt} tabelas, {npo} postes" if (ne or nt or npo)
                                    else "nenhuma planilha carregada"))

    def carregar_normativos(self):
        arq = filedialog.askopenfilename(
            title="Planilha dos normativos (estruturas e tabelas)",
            filetypes=[("Excel", "*.xlsx *.xlsm"), ("Todos", "*.*")])
        if not arq:
            return
        try:
            est, tab, avisos, comps = carregar_planilha_normativos(arq)
        except Exception as e:
            messagebox.showerror("Normativos", f"Não consegui ler a planilha:\n{e}")
            return
        if est is None and tab is None and not any(a.startswith("Postes") for a in avisos):
            messagebox.showwarning("Normativos", "\n".join(avisos))
            return
        partes = []
        if est is not None:
            partes.append(f"{len(est)} estruturas ({sum(len(e['itens']) for e in est)} itens)")
        if tab is not None:
            partes.append(f"{len(tab)} tabelas de escolha ({sum(len(t['linhas']) for t in tab.values())} linhas)")
        falta = []
        if est is None:
            falta.append("A planilha não tinha a aba de estruturas: as estruturas que já estavam continuam.")
        if tab is None:
            falta.append("A planilha não tinha a aba Tabelas: as tabelas que já estavam continuam.")
        partes += [a for a in avisos if a.startswith("Postes")]
        if comps:
            partes.append(f"Composições: {comps[0]} atualizadas (nome, apelidos e categoria mantidos) "
                          f"e {comps[1]} novas")
        messagebox.showinfo("Normativos", "Carregado:\n- " + "\n- ".join(partes) +
                            ("\n\n" + "\n".join(falta) if falta else ""))
        self.mostrar_norma()
        self.atualizar()
        self.app.cadastro_mudou()

    def salvar_norma(self):
        CADASTRO.recarregar_se_mudou()
        CADASTRO.config["estruturas_normativo"] = bool(self.v_norma.get())
        CADASTRO.salvar()
        self.app.cadastro_mudou()

    def salvar_poste(self):
        CADASTRO.recarregar_se_mudou()
        CADASTRO.config["poste_padrao"] = "dt" if self.v_poste.get() == "DT" else "circular"
        CADASTRO.salvar()
        self.app.cadastro_mudou()

    # ---------------------------------------------------------------- planilha
    def carregar(self):
        cam = filedialog.askopenfilename(title="Planilha de materiais extras",
                                         filetypes=[("Excel", "*.xlsx *.xlsm"), ("Todos", "*.*")])
        if not cam:
            return
        try:
            kits, avisos = ler_planilha_composicoes(cam)
        except Exception as ex:
            messagebox.showerror("Planilha", f"Não consegui ler a planilha:\n{ex}")
            return
        if not kits:
            messagebox.showwarning("Planilha", "\n\n".join(avisos))
            return
        n_it = sum(len(k["itens"]) for k in kits)
        n_cat = len({k["categoria"] for k in kits})
        txt = (f"A planilha tem {n_cat} classificações, {len(kits)} materiais principais e {n_it} materiais "
               f"que vêm junto.\n\n")
        if COMPOSICOES.kits:
            txt += (f"Ela SUBSTITUI os {len(COMPOSICOES.kits)} principais atuais (inclusive as mudanças feitas "
                    "aqui no programa). Os outros nomes usados nos projetos são mantidos.\n\n")
        if avisos:
            txt += "Atenção:\n• " + "\n• ".join(avisos) + "\n\n"
        if not messagebox.askyesno("Carregar planilha", txt + "Carregar?"):
            return
        COMPOSICOES.recarregar_se_mudou()
        COMPOSICOES.definir(kits, cam)
        self.novo()
        self.app.cadastro_mudou()
        self.atualizar()

    def baixar(self):
        if not COMPOSICOES.kits:
            messagebox.showinfo("Baixar planilha", "Ainda não há materiais principais.")
            return
        cam = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")],
                                           initialfile="materiais_interligados.xlsx")
        if not cam:
            return
        try:
            salvar_planilha_composicoes(cam, COMPOSICOES.kits)
        except Exception as ex:
            messagebox.showerror("Baixar planilha", f"{ex}\n\nSe a planilha estiver aberta no Excel, feche e "
                                                    "tente de novo.")
            return
        messagebox.showinfo("Baixar planilha", f"Planilha salva:\n{cam}\n\nVocê pode alterar no Excel e "
                                               "carregar de novo.")
