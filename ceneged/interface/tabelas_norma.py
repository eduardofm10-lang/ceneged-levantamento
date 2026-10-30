"""Janela para ver/editar as tabelas dos normativos.

Parte do programa Levantamento de Materiais (Ceneged)."""

import json
import re
import tkinter as tk
from tkinter import filedialog
from tkinter import messagebox
from tkinter import ttk

from ceneged.comum.texto import (_sem_acento, chave_nome, fmt_num)
from ceneged.dados.normativos import (CHAVE_ALTURAS, CHAVE_POSTES, ESTRUTURAS_NORMA,
    TABELAS_NORMA, _cod_planilha, _faixa_planilha, _num_planilha)
from ceneged.dominio.tabelas import _tabela_do_item
from ceneged.dominio.postes import (_postes_fixos, codigo_nua, descricao_do_codigo)
from ceneged.dominio.normativo import (EXPLICA_ESCOLHA, uso_da_linha)
from ceneged.dados.planilhas_normativos import (_txt_faixa, salvar_planilha_normativos)
from ceneged.interface.tema import (AZUL, BRANCO, CINZA, FONTE, TEXTO, VERMELHO, VERM_ESC,
    dica_na_tabela, tabela)

class JanelaTabelasNorma(tk.Toplevel):
    """Tabelas dos normativos (escolha de materiais "A DEFINIR"), postes da DIS-ETE-011 e
    alturas de aplicação: consulta e edição (duplo clique na célula)."""

    COLS = [("ne", "Cód. Nordeste", 95), ("descricao", "Descrição", 330), ("b", "Bitola (mm²)", 90),
            ("p", "Principal (mm²)", 105), ("d", "Derivação (mm²)", 105), ("f", "Fase (mm²)", 80),
            ("n", "Neutro (mm²)", 85), ("pares", "Pares princ./deriv.", 150), ("mat", "Material", 100),
            ("tipo", "Tipo", 80), ("kv", "Tensão (kV)", 80), ("comp", "Compr. (mm) / Cód. compressão", 170),
            ("cunha", "Cód. cunha", 90), ("postes", "Postes fixos (ex.: 9/600)", 170),
            ("padrao", "Usar sempre (sim)", 120),
            ("_uso", "Usado quando (automático)", 420)]
    COLS_POSTE = [("tipo", "Tipo", 70), ("l", "Compr. (m)", 85), ("rn", "Resist. (daN)", 100),
                  ("rn_a", "Res. face A", 90), ("ne", "Cód. Nordeste", 105),
                  ("topo", "Topo Ø (mm)", 85), ("base", "Base Ø (mm)", 85), ("a", "Topo face A", 85),
                  ("A", "Base face A", 85), ("b", "Topo face B", 85), ("B", "Base face B", 85)]
    COLS_ALTURA = [("norma", "Normativo", 120), ("situacao", "Situação", 220), ("d", "Distância do topo (m)", 140)]
    TEXTO_LIVRE = ("ne", "descricao", "mat", "tipo", "cunha", "norma", "situacao")

    def __init__(self, pai, chave=None, pode=True):
        super().__init__(pai)
        self.title("Tabelas dos normativos")
        self.configure(bg=BRANCO)
        self.geometry("1280x720")
        self.transient(pai.winfo_toplevel())
        self.pode = pode
        self.chave = None            # tabela aberta
        self.copia = None            # cópia em edição (só grava em "Salvar alterações")
        self.mudou = False
        self._ent = None
        tk.Frame(self, bg=VERMELHO, height=3).pack(fill="x")
        topo = tk.Frame(self, bg=BRANCO)
        topo.pack(fill="x", padx=16, pady=(10, 0))
        tk.Label(topo, text="Tabelas dos normativos", bg=BRANCO, fg=AZUL, font=(FONTE, 13, "bold")).pack(side="left")
        ttk.Button(topo, text="Baixar planilha dos normativos (com as alterações)",
                   command=self.baixar).pack(side="right")
        tk.Label(self, bg=BRANCO, fg=CINZA, font=(FONTE, 9), justify="left", anchor="w", wraplength=1220,
                 text="De onde sai o material dos itens \"A DEFINIR\" das estruturas (os vermelhos, sem código, nas "
                      "composições). No relatório o sistema escolhe a linha certa pelo cabo e pelo poste da folha; "
                      "a coluna \"Usado quando\" mostra em que situação cada material entra. " +
                      ("Para editar: duplo clique na célula, digite e Enter; depois \"Salvar alterações\". "
                       "Para obrigar um material num poste (ex.: esta cinta no 9/600), escreva o poste na coluna "
                       "\"Postes fixos\" dessa linha." if pode else "Você pode consultar, mas não alterar.")
                 ).pack(fill="x", padx=16, pady=(2, 8))
        corpo = tk.Frame(self, bg=BRANCO)
        corpo.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        esq = tk.Frame(corpo, bg=BRANCO)
        esq.pack(side="left", fill="y")
        self.v_busca = tk.StringVar()
        tk.Label(esq, text="Procurar:", bg=BRANCO, fg=CINZA, font=(FONTE, 9)).pack(anchor="w")
        ttk.Entry(esq, textvariable=self.v_busca, width=40).pack(fill="x", pady=(0, 6))
        self.lst = tabela(esq, [("n", "Normativo", 95), ("t", "Tabela", 80), ("ti", "Título", 230)], altura=24)
        self.lst.quadro.pack(fill="both", expand=True)
        self.lst.bind("<<TreeviewSelect>>", lambda e: self.mostrar())
        dir_ = tk.Frame(corpo, bg=BRANCO)
        dir_.pack(side="left", fill="both", expand=True, padx=(12, 0))
        self.lbl_tit = tk.Label(dir_, text="", bg=BRANCO, fg=AZUL, font=(FONTE, 11, "bold"), anchor="w")
        self.lbl_tit.pack(fill="x")
        self.lbl_info = tk.Label(dir_, text="", bg=BRANCO, fg=TEXTO, font=(FONTE, 9), anchor="w", justify="left",
                                 wraplength=820)
        self.lbl_info.pack(fill="x", pady=(2, 6))
        bot = tk.Frame(dir_, bg=BRANCO)
        bot.pack(side="bottom", fill="x", pady=(8, 0))
        self.lbl_usa = tk.Label(dir_, text="", bg=BRANCO, fg=CINZA, font=(FONTE, 8), anchor="w", justify="left",
                                wraplength=820)
        self.lbl_usa.pack(side="bottom", fill="x", pady=(6, 0))
        self.quadro = tk.Frame(dir_, bg=BRANCO)
        self.quadro.pack(fill="both", expand=True)
        self.bts = []
        for txt, cmd, st in (("Adicionar linha", self.add_linha, "TButton"),
                             ("Remover linha", self.del_linha, "TButton")):
            b = ttk.Button(bot, text=txt, command=cmd, style=st)
            b.pack(side="left", padx=(0, 6))
            self.bts.append(b)
        b = ttk.Button(bot, text="Salvar alterações", style="Verm.TButton", command=self.salvar)
        b.pack(side="right")
        self.bts.append(b)
        b = ttk.Button(bot, text="Desfazer", command=self.desfazer)
        b.pack(side="right", padx=6)
        self.bts.append(b)
        self.lbl_mudou = tk.Label(bot, text="", bg=BRANCO, fg=VERM_ESC, font=(FONTE, 9))
        self.lbl_mudou.pack(side="right", padx=10)
        if not pode:
            for b in self.bts:
                b.state(["disabled"])
        self.tree = None
        self.cols = []
        self.v_busca.trace_add("write", lambda *a: self.listar())
        self.protocol("WM_DELETE_WINDOW", self.fechar)
        self.listar(chave)

    # ---------------------------------------------------------------- lista de tabelas
    def _chaves(self):
        tabs = TABELAS_NORMA.conteudo
        normais = sorted([k for k in tabs if not k.startswith("DIS-ETE-011|")],
                         key=lambda k: (k.split("|")[0], int((re.findall(r"\d+", k.split("|")[1]) or [0])[0])))
        return [k for k in (CHAVE_POSTES, CHAVE_ALTURAS) if k in tabs] + normais

    def listar(self, chave=None):
        tabs = TABELAS_NORMA.conteudo
        b = chave_nome(self.v_busca.get())
        self._sel_prog = True
        self.lst.delete(*self.lst.get_children())
        for k in self._chaves():
            n, _, t = k.partition("|")
            ti = tabs[k].get("titulo", "")
            if b and b not in chave_nome(f"{n} {t} {ti}") and not any(
                    b in chave_nome(str(l.get("descricao", "")) + str(l.get("ne", ""))) for l in tabs[k]["linhas"]):
                continue
            self.lst.insert("", "end", iid=k, values=(n, t, ti))
        self._sel_prog = False
        if not self.lst.get_children():
            self.lbl_tit.config(text="Nenhuma tabela carregada" if not tabs else "Nada encontrado")
            self.lbl_info.config(text="Carregue a planilha dos normativos na tela de Materiais extras."
                                 if not tabs else "")
            return
        alvo = chave or self.chave
        alvo = alvo if alvo in self.lst.get_children() else self.lst.get_children()[0]
        self.lst.selection_set(alvo)
        self.lst.see(alvo)

    @staticmethod
    def _fmt(v):
        if v is None or v == "":
            return ""
        if isinstance(v, bool):
            return "cunha" if v else ""
        if isinstance(v, list):
            return _txt_faixa(v)
        if isinstance(v, (int, float)):
            return fmt_num(v)
        return str(v)

    def _cols_de(self, k, linhas):
        if k == CHAVE_POSTES:
            return self.COLS_POSTE
        if k == CHAVE_ALTURAS:
            return self.COLS_ALTURA
        modo = (TABELAS_NORMA.conteudo.get(k) or {}).get("modo")
        if modo == "nua":
            return [("ne", "Cód. usado", 90), ("descricao", "Descrição (do código usado)", 300),
                    ("_uso", "Usado quando (automático)", 380), ("cunha", "Cód. conector cunha", 120),
                    ("comp", "Cód. conector compressão", 150)]
        tem = [c for c in self.COLS if c[0] in ("ne", "descricao", "_uso") or (c[0] == "postes" and modo == "poste")
               or (c[0] == "padrao" and modo == "manual")
               or any(self._fmt(l.get(c[0])) for l in linhas)]
        # "Usado quando" logo depois da descrição
        tem = [c for c in tem if c[0] != "_uso"]
        i = next((n for n, c in enumerate(tem) if c[0] == "descricao"), 1) + 1
        return tem[:i] + [c for c in self.COLS if c[0] == "_uso"] + tem[i:]

    def mostrar(self):
        if getattr(self, "_sel_prog", False):
            return
        s = self.lst.selection()
        if not s or s[0] == self.chave:
            return
        if self.mudou and not messagebox.askyesno(
                "Tabelas", "Há alterações não salvas nesta tabela. Descartar?", parent=self):
            self._sel_prog = True
            self.lst.selection_set(self.chave)
            self._sel_prog = False
            return
        self.chave = s[0]
        t = TABELAS_NORMA.conteudo.get(self.chave)
        if not t:
            return
        self.copia = json.loads(json.dumps(t))
        self._marcar(False)
        n, _, tb = self.chave.partition("|")
        self.lbl_tit.config(text=f"{n} – {tb}: {t.get('titulo', '')}")
        modo = t.get("modo", "")
        self.lbl_info.config(text=f"Escolha: {EXPLICA_ESCOLHA.get(modo, modo)}." +
                                  (f"\nInformação necessária: {t['info']}" if t.get("info") else ""))
        self.cols = self._cols_de(self.chave, self.copia["linhas"])
        for w in self.quadro.winfo_children():
            w.destroy()
        sbx = ttk.Scrollbar(self.quadro, orient="horizontal")
        sbx.pack(side="bottom", fill="x")
        self.tree = tabela(self.quadro, self.cols, altura=18)
        self.tree.quadro.pack(fill="both", expand=True)
        self.tree.configure(xscrollcommand=sbx.set)
        sbx.configure(command=self.tree.xview)
        self.tree.tag_configure("semcod", foreground=VERM_ESC)
        self.tree.bind("<Double-1>", self._editar_celula)
        dica_na_tabela(self.tree, lambda iid: "\n".join(
            f"{h}: {v}" for (c, h, w), v in zip(self.cols, self.tree.item(iid, "values")) if str(v).strip()),
            largura=640)
        self._preencher()
        usam = []
        if self.chave not in (CHAVE_POSTES, CHAVE_ALTURAS):
            for e in ESTRUTURAS_NORMA.conteudo:
                if any(i.get("adef") and _tabela_do_item(i, e["norma"]) == self.chave for i in e["itens"]):
                    usam.append(e["nome"])
        self.lbl_usa.config(text=("Estruturas que usam esta tabela: " + ", ".join(usam)) if usam else
                            ("Em vermelho: sem código Nordeste." if self.chave != CHAVE_ALTURAS else ""))

    def _preencher(self):
        self.tree.delete(*self.tree.get_children())
        tem_ne = "ne" in [c[0] for c in self.cols]
        for n, l in enumerate(self.copia["linhas"]):
            vals = []
            nua = self.copia.get("modo") == "nua"
            for c, _, _ in self.cols:
                v = l.get(c)
                if nua and c == "ne":
                    v = codigo_nua(l)
                elif nua and c == "descricao":
                    v = descricao_do_codigo(codigo_nua(l)) or "(código sem descrição no sistema)"
                elif c == "_uso":
                    try:
                        v = uso_da_linha(self.chave, self.copia, l)
                    except Exception:
                        v = ""
                elif c == "postes":
                    v = "; ".join(v or [])
                elif c == "padrao":
                    v = "sim" if v else ""
                if self.chave == CHAVE_POSTES and c == "tipo":
                    v = "DT" if v == "dt" else "Circular"
                if c == "tipo" and l.get("cunha") is True:
                    v = "cunha"
                if c == "cunha" and v is True:
                    v = ""
                vals.append(self._fmt(v))
            sem = not (codigo_nua(l) if self.copia.get("modo") == "nua" else l.get("ne"))
            self.tree.insert("", "end", iid=str(n), values=vals, tags=("semcod",) if tem_ne and sem else ())

    # ---------------------------------------------------------------- edição
    def _marcar(self, m):
        self.mudou = m
        self.lbl_mudou.config(text="alterações não salvas" if m else "")

    def _editar_celula(self, e):
        if not self.pode or self.tree is None:
            return
        row, col = self.tree.identify_row(e.y), self.tree.identify_column(e.x)
        if not row or not col:
            return
        ci = int(col[1:]) - 1
        x, y, w, h = self.tree.bbox(row, col)
        if self._ent is not None:
            self._ent.destroy()
        v = tk.StringVar(value=self.tree.item(row, "values")[ci])
        ent = ttk.Entry(self.tree, textvariable=v)
        ent.place(x=x, y=y, width=max(w, 80), height=h)
        ent.focus_set()
        ent.select_range(0, "end")
        self._ent = ent

        def gravar(_=None):
            if self._ent is None:
                return
            self._ent = None
            ent.destroy()
            self._gravar_valor(int(row), self.cols[ci][0], v.get())
        ent.bind("<Return>", gravar)
        ent.bind("<FocusOut>", gravar)
        ent.bind("<Escape>", lambda _: (ent.destroy(), setattr(self, "_ent", None)))

    def _gravar_valor(self, n, ch, txt):
        l = self.copia["linhas"][n]
        txt = txt.strip()
        modo = self.copia.get("modo")
        if modo == "nua" and ch in ("ne", "descricao"):
            messagebox.showinfo("Tabelas", "Nesta tabela o código usado sai das colunas \"Cód. conector cunha\" e "
                                           "\"Cód. conector compressão\" (compressão por padrão). Edite lá.",
                                parent=self)
            return
        if ch == "_uso":
            messagebox.showinfo("Tabelas", "Esta coluna é calculada pelo sistema. Para mudar quando a linha é "
                                           "usada, mude os valores das outras colunas (ou \"Postes fixos\").",
                                parent=self)
            return
        if ch == "padrao":
            sim = _sem_acento(txt).strip().upper() in ("S", "SIM", "X", "1")
            for x in self.copia["linhas"]:
                x.pop("padrao", None)              # só uma linha pode ser a de sempre
            if sim:
                l["padrao"] = True
            self._marcar(True)
            self._preencher()
            self.tree.selection_set(str(n))
            return
        if ch == "postes":
            lista = [x.strip() for x in re.split(r"[;,]", txt) if x.strip()]
            ruins = [x for x in lista if not _postes_fixos({"postes": [x]})]
            if ruins:
                messagebox.showwarning("Tabelas", "Escreva os postes como altura/resistência, separados por ponto e "
                                                  "vírgula. Ex.: 9/600; 11/400; 12/1000 C", parent=self)
                return
            if lista:
                l["postes"] = lista
            else:
                l.pop("postes", None)
            self._marcar(True)
            self._preencher()
            self.tree.selection_set(str(n))
            return
        if self.chave == CHAVE_POSTES and ch == "tipo":
            l["tipo"] = "dt" if _sem_acento(txt).upper().startswith("D") else "circular"
        elif ch == "tipo" and txt.lower() == "cunha" and self.chave not in (CHAVE_POSTES, CHAVE_ALTURAS):
            l.pop("tipo", None)
            l["cunha"] = True
        elif not txt:
            if ch in ("ne", "descricao"):
                l[ch] = ""
            else:
                l.pop(ch, None)
            if ch == "tipo" and l.get("cunha") is True:
                l.pop("cunha")
        elif ch in ("ne", "cunha") or (ch == "comp" and modo == "nua"):
            l[ch] = _cod_planilha(txt)
        elif ch in self.TEXTO_LIVRE:
            l[ch] = txt
        elif ch in ("p", "d"):
            v = _faixa_planilha(txt)
            if v is None:
                messagebox.showwarning("Tabelas", "Escreva um número (21,2) ou uma faixa (35 a 50).", parent=self)
                return
            l[ch] = v
        elif ch == "pares":
            v = [[_num_planilha(a) for a in par.split("/")] for par in re.split(r"[;|]", txt) if "/" in par]
            if not v or any(None in par or len(par) != 2 for par in v):
                messagebox.showwarning("Tabelas", "Escreva os pares assim: 25/25; 35/35", parent=self)
                return
            l[ch] = v
        else:
            v = _num_planilha(txt)
            if v is None:
                messagebox.showwarning("Tabelas", "Esse campo é um número.", parent=self)
                return
            l[ch] = v
        self._marcar(True)
        self._preencher()
        self.tree.selection_set(str(n))

    def add_linha(self):
        if self.copia is None:
            return
        if self.chave == CHAVE_POSTES:
            nova = {"tipo": "circular", "l": None, "rn": None, "ne": "", "descricao": ""}
        elif self.chave == CHAVE_ALTURAS:
            nova = {"norma": "", "situacao": "", "d": None}
        else:
            nova = {"ne": "", "se": "", "br": "", "descricao": ""}
        self.copia["linhas"].append(nova)
        self._marcar(True)
        self._preencher()
        n = str(len(self.copia["linhas"]) - 1)
        self.tree.selection_set(n)
        self.tree.see(n)

    def del_linha(self):
        if self.tree is None:
            return
        s = self.tree.selection()
        if not s:
            messagebox.showinfo("Tabelas", "Selecione a linha que quer remover.", parent=self)
            return
        if not messagebox.askyesno("Tabelas", "Remover a linha selecionada?", parent=self):
            return
        del self.copia["linhas"][int(s[0])]
        self._marcar(True)
        self._preencher()

    def desfazer(self):
        if self.chave is None:
            return
        k, self.chave = self.chave, None
        self._marcar(False)
        self.lst.selection_remove(*self.lst.selection())
        self.lst.selection_set(k)

    def salvar(self):
        if self.copia is None or not self.mudou:
            return
        if self.chave == CHAVE_POSTES:
            ruins = [l for l in self.copia["linhas"] if not (l.get("l") and l.get("rn") and
                     ((l.get("topo") and l.get("base")) if l.get("tipo") == "circular" else (l.get("a") and l.get("A"))))]
            if ruins and not messagebox.askyesno(
                    "Tabelas", f"{len(ruins)} poste(s) sem comprimento, resistência ou medidas de topo/base: "
                               "eles não vão ser usados. Salvar assim mesmo?", parent=self):
                return
        TABELAS_NORMA.recarregar_se_mudou()
        tabs = dict(TABELAS_NORMA.conteudo)
        tabs[self.chave] = self.copia
        TABELAS_NORMA.trocar(tabs)
        self.copia = json.loads(json.dumps(self.copia))
        self._marcar(False)
        messagebox.showinfo("Tabelas", "Tabela salva. Vale para os próximos relatórios.", parent=self)

    def baixar(self):
        if self.mudou and messagebox.askyesno("Tabelas", "Salvar as alterações desta tabela antes?", parent=self):
            self.salvar()
        cam = filedialog.asksaveasfilename(parent=self, defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")],
                                           initialfile="Normativos_Neoenergia_para_carregar.xlsx")
        if not cam:
            return
        try:
            salvar_planilha_normativos(cam)
        except Exception as ex:
            messagebox.showerror("Tabelas", f"{ex}\n\nSe a planilha estiver aberta no Excel, feche e tente de novo.",
                                 parent=self)
            return
        messagebox.showinfo("Tabelas", f"Planilha salva:\n{cam}", parent=self)

    def fechar(self):
        if self.mudou and not messagebox.askyesno("Tabelas", "Há alterações não salvas. Fechar assim mesmo?",
                                                  parent=self):
            return
        self.destroy()
