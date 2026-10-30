"""Diálogos: escolher nome, cerca, escolher material.

Parte do programa Levantamento de Materiais (Ceneged)."""

import re
import tkinter as tk
from tkinter import messagebox
from tkinter import ttk
from PIL import ImageTk

from ceneged.comum.texto import (chave_nome, normaliza_codigo)
from ceneged.dados.cadastro import CADASTRO
from ceneged.dados.composicoes import (COMPOSICOES, _num, titulo_kit)
from ceneged.dados.planilhas import UNIDADES
from ceneged.dominio.materiais import materiais_conhecidos
from ceneged.interface.tema import (AZUL, BORDA, BRANCO, CINZA, FONTE, TEXTO, VERDE, VERMELHO)

class EscolherNome(tk.Toplevel):
    """Janela para escolher, no cadastro, o nome certo de um nome do projeto."""

    def __init__(self, pai, nome):
        super().__init__(pai)
        self.title("Escolher nome do cadastro")
        self.configure(bg=BRANCO)
        self.transient(pai.winfo_toplevel())
        self.resultado = None
        tk.Frame(self, bg=VERMELHO, height=3).pack(fill="x")
        tk.Label(self, text="Nome no projeto:", bg=BRANCO, fg=CINZA, font=(FONTE, 9)).pack(anchor="w", padx=16, pady=(12, 0))
        tk.Label(self, text=nome, bg=BRANCO, fg=AZUL, font=(FONTE, 13, "bold")).pack(anchor="w", padx=16)
        tk.Label(self, text="Escolha o nome do cadastro (digite para filtrar):", bg=BRANCO, fg=TEXTO,
                 font=(FONTE, 9)).pack(anchor="w", padx=16, pady=(10, 2))
        self.v = tk.StringVar()
        e = ttk.Entry(self, textvariable=self.v, width=60)
        e.pack(fill="x", padx=16)
        self.lst = tk.Listbox(self, height=14, bg=BRANCO, fg=TEXTO, selectbackground=AZUL, selectforeground=BRANCO,
                              highlightthickness=1, highlightbackground=BORDA, highlightcolor=AZUL, relief="flat",
                              font=(FONTE, 10), activestyle="none", exportselection=False)
        self.lst.pack(fill="both", expand=True, padx=16, pady=8)
        self.sugeridos = CADASTRO.candidatos(nome)
        self.v.trace_add("write", lambda *a: self.filtrar())
        self.filtrar()
        self.lst.bind("<Double-1>", lambda e_: self.ok())
        e.bind("<Return>", lambda e_: self.ok())
        e.bind("<Down>", lambda e_: (self.lst.focus_set(), self.lst.selection_set(0)))
        bts = tk.Frame(self, bg=BRANCO)
        bts.pack(fill="x", padx=16, pady=(0, 14))
        ttk.Button(bts, text="Usar este nome", style="Azul.TButton", command=self.ok).pack(side="right")
        ttk.Button(bts, text="Cancelar", command=self.destroy).pack(side="right", padx=6)
        ttk.Button(bts, text="Manter o nome do projeto", command=lambda: self.fim(nome)).pack(side="left")
        self.bind("<Escape>", lambda e_: self.destroy())
        self.geometry("+%d+%d" % (pai.winfo_rootx() + 200, pai.winfo_rooty() + 80))
        e.focus_set()
        self.grab_set()
        self.wait_window()

    def filtrar(self):
        k = chave_nome(self.v.get())
        self.lst.delete(0, "end")
        if not k:
            vals = self.sugeridos + [m for m in CADASTRO.materiais if m not in self.sugeridos]
        else:
            vals = [m for m in CADASTRO.materiais if k in chave_nome(m)]
        for m in vals[:500]:
            self.lst.insert("end", m)
            if not k and m in self.sugeridos:
                self.lst.itemconfig("end", fg=AZUL)
        if vals:
            self.lst.selection_set(0)

    def ok(self):
        s = self.lst.curselection()
        if s:
            self.fim(self.lst.get(s[0]))

    def fim(self, valor):
        self.resultado = valor
        self.destroy()


class JanelaCerca(tk.Toplevel):
    """Janela pequena (ao lado, sem travar o programa) para conferir ou digitar os dados
    da cerca: nº de fios, aterramentos de cerca e seccionamentos.
    ao_ok(valores | None): None = "não tem cerca"."""

    def __init__(self, pai, valores=None, achados=None, ao_ok=None, titulo="Cerca - SIT. 01",
                 com_nao=True, marcar=None, ao_ignorar=None, ao_novo=None, ao_fechar=None, imagem=None,
                 editar=None):
        super().__init__(pai)
        self.title(titulo)
        self.configure(bg=BRANCO)
        self.transient(pai.winfo_toplevel())
        self.resizable(False, False)
        self.ao_ok = ao_ok
        valores = valores or {}
        manual = achados is None
        achados = achados or {}
        tk.Frame(self, bg=VERMELHO, height=3).pack(fill="x")
        tk.Label(self, text=titulo, bg=BRANCO, fg=AZUL,
                 font=(FONTE, 11, "bold")).pack(anchor="w", padx=12, pady=(8, 0))
        if imagem is not None:
            self._foto = ImageTk.PhotoImage(imagem)
            tk.Label(self, image=self._foto, bg=BRANCO, bd=1, relief="solid").pack(padx=12, pady=(6, 2))
            tk.Label(self, text="laranja = cerca deste trecho", bg=BRANCO, fg=CINZA,
                     font=(FONTE, 8)).pack(anchor="w", padx=12)
        self.ao_fechar = ao_fechar
        self.protocol("WM_DELETE_WINDOW", self.fechar)
        falta = [n for k, n in (("fios", "nº de fios"), ("aterr", "aterramentos"), ("secc", "seccionamentos"))
                 if not achados.get(k)]
        txt = ("Preencha os três números e clique OK." if manual else
               "Confira o que foi lido no desenho e clique OK." if not falta else
               "Não encontrei no desenho: " + ", ".join(falta) + ". Preencha e clique OK.")
        if achados.get("fios_lista") and len(set(achados["fios_lista"])) > 1:
            txt += f"\n(fios escritos no desenho: {', '.join(str(x) for x in achados['fios_lista'])})"
        tk.Label(self, text=txt, bg=BRANCO, fg=CINZA, font=(FONTE, 9), justify="left",
                 wraplength=260).pack(anchor="w", padx=12, pady=(2, 6))
        f = tk.Frame(self, bg=BRANCO)
        f.pack(fill="x", padx=12)
        self.vars = {}
        for lin, (k, rot) in enumerate((("fios", "Nº de fios"), ("aterr", "Aterramentos de cerca"),
                                        ("secc", "Seccionamentos"))):
            tk.Label(f, text=rot, bg=BRANCO, fg=TEXTO, font=(FONTE, 10)).grid(row=lin, column=0, sticky="w", pady=3)
            v = tk.StringVar(value="" if valores.get(k) in (None, 0) else str(valores.get(k)))
            e = ttk.Entry(f, textvariable=v, width=8)
            e.grid(row=lin, column=1, padx=8, pady=3)
            st = "" if manual else ("lido no desenho" if achados.get(k) else "digite ou marque")
            tk.Label(f, text=st, bg=BRANCO, fg=VERDE if achados.get(k) else VERMELHO,
                     font=(FONTE, 8)).grid(row=lin, column=3, sticky="w")
            if marcar:
                ttk.Button(f, text="Marcar", width=7,
                           command=lambda k=k: marcar(k)).grid(row=lin, column=2, padx=(0, 6))
            self.vars[k] = v
        if marcar:
            tk.Label(self, text="Marcar: clique no desenho em cada figura (clicar de novo numa marca "
                                "tira); para os fios, clique no texto \"N FIOS\". Esc termina.",
                     bg=BRANCO, fg=CINZA, font=(FONTE, 8), justify="left", wraplength=300
                     ).pack(anchor="w", padx=12, pady=(4, 0))
        if editar:
            fe = tk.Frame(self, bg=BRANCO)
            fe.pack(fill="x", padx=12, pady=(8, 0))
            tk.Label(fe, text="Cerca no desenho (rosa):", bg=BRANCO, fg=TEXTO,
                     font=(FONTE, 9)).pack(side="left")
            for txt_, ac in (("Aumentar", "aum"), ("Diminuir", "dim"), ("Apagar", "apagar")):
                ttk.Button(fe, text=txt_, command=lambda ac=ac: editar(ac)).pack(side="left", padx=2)
        self.lbl = tk.Label(self, text="", bg=BRANCO, fg=VERMELHO, font=(FONTE, 9))
        self.lbl.pack(anchor="w", padx=12)
        b = tk.Frame(self, bg=BRANCO)
        b.pack(fill="x", padx=12, pady=(4, 10))
        ttk.Button(b, text="OK", style="Azul.TButton", command=self.ok).pack(side="right")
        if com_nao:
            ttk.Button(b, text="Não tem cerca", command=self.nao).pack(side="right", padx=6)
        if ao_ignorar or ao_novo:
            b2 = tk.Frame(self, bg=BRANCO)
            b2.pack(fill="x", padx=12, pady=(0, 10))
            if ao_ignorar:
                ttk.Button(b2, text="Não é trecho de cerca", command=lambda: (self.destroy(), ao_ignorar())
                           ).pack(side="left")
            if ao_novo:
                ttk.Button(b2, text="+ Trecho", command=ao_novo).pack(side="right")
        self.bind("<Return>", lambda e: self.ok())
        # ao lado direito da janela principal
        try:
            r = pai.winfo_toplevel()
            self.update_idletasks()
            x = r.winfo_rootx() + r.winfo_width() - self.winfo_reqwidth() - 30
            y = r.winfo_rooty() + 90
            self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        except Exception:
            pass

    def set_valor(self, k, v):
        self.vars[k].set("" if not v else str(v))

    def fechar(self):
        self.destroy()
        if self.ao_fechar:
            self.ao_fechar()

    def ok(self):
        vals = {}
        for k, v in self.vars.items():
            q = _num(v.get())
            if q is None or q <= 0 or q != int(q):
                self.lbl.config(text="Preencha os três números (inteiros maiores que zero).")
                return
            vals[k] = int(q)
        self.destroy()
        if self.ao_ok:
            self.ao_ok(vals)

    def nao(self):
        self.destroy()
        if self.ao_ok:
            self.ao_ok(None)


class EscolherMaterial(tk.Toplevel):
    """Procura um material (cadastro + planilha de materiais extras) ou, se `com_kits`,
    um material principal inteiro. Também aceita um material digitado à mão."""

    def __init__(self, pai, titulo="Adicionar material", com_kits=False, com_qtd=True, qtd="1"):
        super().__init__(pai)
        self.title(titulo)
        self.configure(bg=BRANCO)
        self.transient(pai.winfo_toplevel())
        self.resultado = None
        self.com_kits = com_kits
        tk.Frame(self, bg=VERMELHO, height=3).pack(fill="x")
        tk.Label(self, text=titulo, bg=BRANCO, fg=AZUL, font=(FONTE, 13, "bold")).pack(anchor="w", padx=16,
                                                                                       pady=(10, 0))
        tk.Label(self, bg=BRANCO, fg=CINZA, font=(FONTE, 9), justify="left", anchor="w",
                 text="Digite parte do nome ou do código para procurar. Se o material não estiver na lista, "
                      "preencha os campos de baixo à mão." +
                      ("\n◆ = material principal: entram todos os materiais dele." if com_kits else "")
                 ).pack(fill="x", padx=16, pady=(2, 6))
        self.v_busca = tk.StringVar()
        e = ttk.Entry(self, textvariable=self.v_busca, width=80)
        e.pack(fill="x", padx=16)
        self.lst = tk.Listbox(self, height=14, bg=BRANCO, fg=TEXTO, selectbackground=AZUL,
                              selectforeground=BRANCO, highlightthickness=1, highlightbackground=BORDA,
                              highlightcolor=AZUL, relief="flat", font=(FONTE, 10), activestyle="none",
                              exportselection=False)
        self.lst.pack(fill="both", expand=True, padx=16, pady=8)
        self.opcoes = []
        for cod, nome, und in sorted(materiais_conhecidos().values(), key=lambda x: x[1].upper()):
            self.opcoes.append(("m", (cod, nome, und), f"{cod or '(sem código)'}  —  {nome}"))
        if com_kits:
            for k in COMPOSICOES.kits:
                self.opcoes.append(("k", k, f"◆  {titulo_kit(k)}   ({len(k['itens'])} materiais · {k['categoria']})"))
        f = tk.Frame(self, bg=BRANCO)
        f.pack(fill="x", padx=16)
        self.v_cod, self.v_nome = tk.StringVar(), tk.StringVar()
        self.v_und, self.v_qtd = tk.StringVar(value="CDA"), tk.StringVar(value=qtd)
        self.kit = None
        for col, (rot, var, w) in enumerate((("Código", self.v_cod, 12), ("Material", self.v_nome, 46),
                                             ("UND", self.v_und, 6)) + ((("Quantidade", self.v_qtd, 9),)
                                                                        if com_qtd else ())):
            tk.Label(f, text=rot, bg=BRANCO, fg=CINZA, font=(FONTE, 8)).grid(row=0, column=col, sticky="w",
                                                                           padx=(0, 6))
            if var is self.v_und:
                w_ = ttk.Combobox(f, textvariable=var, values=UNIDADES, width=w)
            else:
                w_ = ttk.Entry(f, textvariable=var, width=w)
            w_.grid(row=1, column=col, sticky="we", padx=(0, 6))
        f.columnconfigure(1, weight=1)
        self.v_nome.trace_add("write", lambda *a: setattr(self, "kit", None) if not getattr(self, "_pondo", 0)
                              else None)
        self.v_busca.trace_add("write", lambda *a: self.filtrar())
        self.lst.bind("<<ListboxSelect>>", lambda e_: self.pegar())
        self.lst.bind("<Double-1>", lambda e_: self.ok())
        e.bind("<Down>", lambda e_: (self.lst.focus_set(), self.lst.selection_set(0), self.pegar()))
        e.bind("<Return>", lambda e_: self.ok())
        bts = tk.Frame(self, bg=BRANCO)
        bts.pack(fill="x", padx=16, pady=12)
        ttk.Button(bts, text="OK", style="Azul.TButton", command=self.ok).pack(side="right")
        ttk.Button(bts, text="Cancelar", command=self.destroy).pack(side="right", padx=6)
        self.bind("<Escape>", lambda e_: self.destroy())
        self.filtrar()
        self.geometry("+%d+%d" % (pai.winfo_rootx() + 160, pai.winfo_rooty() + 60))
        e.focus_set()
        self.grab_set()
        self.wait_window()

    def filtrar(self):
        k = chave_nome(self.v_busca.get())
        self.vis = [o for o in self.opcoes if not k or k in chave_nome(o[2])][:800]
        self.lst.delete(0, "end")
        for tipo, _, txt in self.vis:
            self.lst.insert("end", txt)
            if tipo == "k":
                self.lst.itemconfig("end", fg=AZUL)

    def pegar(self):
        s = self.lst.curselection()
        if not s:
            return
        tipo, dado, _ = self.vis[s[0]]
        self._pondo = 1
        if tipo == "k":
            self.v_cod.set(dado["id"])
            self.v_nome.set(dado["nome"])
            self.v_und.set("CDA")
            self.kit = dado
        else:
            self.v_cod.set(dado[0])
            self.v_nome.set(dado[1])
            self.v_und.set(dado[2] or "CDA")
            self.kit = None
        self._pondo = 0

    def ok(self):
        nome = re.sub(r"\s+", " ", self.v_nome.get()).strip()
        if not nome:
            if self.lst.curselection():
                self.pegar()
                nome = self.v_nome.get().strip()
            if not nome:
                messagebox.showinfo(self.title(), "Escolha um material na lista ou digite o nome.", parent=self)
                return
        q = _num(self.v_qtd.get())
        if q is None or q <= 0:
            messagebox.showinfo(self.title(), "Quantidade inválida.", parent=self)
            return
        self.resultado = {"kit": self.kit, "codigo": normaliza_codigo(self.v_cod.get()) if not self.kit else "",
                          "nome": nome, "und": (self.v_und.get() or "CDA").strip().upper(), "qtd": q}
        self.destroy()
