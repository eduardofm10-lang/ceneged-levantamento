"""Login, troca de senha e usuários.

Parte do programa Levantamento de Materiais (Ceneged)."""

import os
import tkinter as tk
from tkinter import messagebox
from tkinter import ttk

from ceneged.dados.caminhos import (_MONGO, descricao_banco, modo_mongo, pasta_acessivel,
    pasta_programa, procurar_pasta_dados, reiniciar_programa, tem_dados)
from ceneged.dados.mongo import (_mongo_lidos, mongo_conectado, ultimo_acesso)
from ceneged.dados.atualizacao import versao_instalada
from ceneged.dados.usuarios import (SENHA_MIN, USUARIOS, Usuarios)
from ceneged.interface.tema import (AZUL, BORDA, BRANCO, CINZA, FONTE, FUNDO, TEXTO, VERMELHO,
    VERM_ESC, _LOGO_G_PNG, _imagem, cartao, secao, tabela)

def _campo(pai, rotulo, var, show=None, bg=BRANCO, dica=None):
    tk.Label(pai, text=rotulo, bg=bg, fg=TEXTO, font=(FONTE, 9, "bold"), anchor="w").pack(fill="x", pady=(8, 2))
    e = ttk.Entry(pai, textvariable=var, show=show or "", font=(FONTE, 11))
    e.pack(fill="x", ipady=3)
    if dica:
        tk.Label(pai, text=dica, bg=bg, fg=CINZA, font=(FONTE, 8), anchor="w", justify="left",
                 wraplength=330).pack(fill="x")
    return e


class TelaLogin(tk.Frame):
    """Tela de entrada. Sem nenhum usuário cadastrado, cria o administrador."""

    def __init__(self, root, usuarios, ao_entrar):
        super().__init__(root, bg=FUNDO)
        self.usuarios = usuarios
        self.ao_entrar = ao_entrar
        self._img = _imagem(_LOGO_G_PNG)
        tk.Frame(self, bg=AZUL, height=6).pack(fill="x")
        tk.Frame(self, bg=VERMELHO, height=3).pack(fill="x")
        self.card = tk.Frame(self, bg=BRANCO, highlightbackground=BORDA, highlightthickness=1)
        self.card.place(relx=0.5, rely=0.48, anchor="center", width=440)
        v = versao_instalada()
        onde = descricao_banco() if modo_mongo() else os.path.dirname(usuarios.caminho)
        tk.Label(self, text=(f"Versão {v}   ·   " if v else "") + f"Dados em: {onde}",
                 bg=FUNDO, fg="#9AA4B2",
                 font=(FONTE, 8)).place(relx=0.5, rely=1.0, y=-10, anchor="s")
        pasta = os.path.dirname(usuarios.caminho)
        if modo_mongo():
            if not mongo_conectado(forcar=True) or not _mongo_lidos:
                self._sem_banco()
            elif usuarios.vazio():
                self._primeiro_acesso()
            else:
                self._login()
        elif not pasta_acessivel(pasta):
            self._sem_pasta(pasta)
        elif usuarios.vazio():
            self._primeiro_acesso()
        else:
            self._login()

    def _sem_banco(self):
        self._cabeca("Sem conexão com o banco de dados",
                     "O programa não conseguiu falar com o banco onde ficam os usuários e o cadastro.")
        tk.Label(self.card, text=_MONGO.get("erro") or descricao_banco(), bg=BRANCO, fg=VERM_ESC,
                 font=(FONTE, 10, "bold"), wraplength=350).pack(padx=30, pady=(4, 8))
        tk.Label(self.card, bg=BRANCO, fg=TEXTO, font=(FONTE, 9), justify="left", wraplength=350,
                 text="•  Confira se o computador está com internet.\n"
                      "•  Rede da empresa bloqueando? Teste em outra rede (ex.: celular).\n"
                      "•  Administrador: no MongoDB Atlas, confira em Network Access se o acesso "
                      "está liberado e se o usuário/senha do banco_mongo.txt estão certos.").pack(padx=30)

        def tentar():
            if mongo_conectado(forcar=True):
                messagebox.showinfo("Banco de dados", "Conectado! O programa vai abrir de novo.", parent=self)
                reiniciar_programa(self.winfo_toplevel())
            else:
                self.erro.config(text="Ainda sem conexão.")
        self._rodape("Tentar de novo", tentar)

    def _sem_pasta(self, pasta):
        self._cabeca("Sem acesso à pasta compartilhada",
                     "O programa não conseguiu abrir a pasta onde ficam os usuários e o cadastro:")
        tk.Label(self.card, text=pasta, bg=BRANCO, fg=VERM_ESC, font=(FONTE, 10, "bold"),
                 wraplength=350).pack(padx=30, pady=(4, 8))
        tk.Label(self.card, bg=BRANCO, fg=TEXTO, font=(FONTE, 9), justify="left", wraplength=350,
                 text="•  OneDrive: abra o e-mail de compartilhamento da pasta Levantamento > Abrir > "
                      "\"Adicionar atalho a Meus arquivos\". Espere 1 ou 2 minutos e clique em Tentar de novo "
                      "(o programa acha a pasta sozinho).\n"
                      "•  Confira se o OneDrive está ligado e sincronizado (ícone de nuvem perto do relógio).\n"
                      "•  Confira se você tem permissão de editar nessa pasta.").pack(padx=30)

        def tentar():
            # o atalho do OneDrive pode ter chegado depois que o programa abriu: procura de novo
            if not tem_dados(pasta):
                achada = procurar_pasta_dados(os.path.basename(pasta.rstrip("\\/")), forcar=True)
                if achada and os.path.normcase(achada) != os.path.normcase(pasta):
                    try:
                        with open(os.path.join(pasta_programa(), "pasta_dados.txt"), "w", encoding="utf-8") as f:
                            f.write(achada)
                    except OSError:
                        pass
                    messagebox.showinfo("Pasta encontrada",
                                        f"Encontrei a pasta compartilhada:\n{achada}\n\n"
                                        "O programa vai abrir de novo para usar essa pasta.",
                                        parent=self)
                    reiniciar_programa(self.winfo_toplevel())
                    return
            if pasta_acessivel(pasta):
                self.winfo_toplevel().unbind("<Return>")
                if self.usuarios.vazio():
                    self._primeiro_acesso()
                else:
                    self._login()
            else:
                self.erro.config(text="Ainda sem acesso à pasta.")
        self._rodape("Tentar de novo", tentar)

    def _cabeca(self, titulo, sub):
        for w in self.card.winfo_children():
            w.destroy()
        tk.Frame(self.card, bg=VERMELHO, height=4).pack(fill="x")
        if self._img:
            tk.Label(self.card, image=self._img, bg=BRANCO).pack(pady=(24, 6))
        tk.Label(self.card, text=titulo, fg=AZUL, bg=BRANCO, font=(FONTE, 16, "bold")).pack()
        tk.Label(self.card, text=sub, fg=CINZA, bg=BRANCO, font=(FONTE, 9), wraplength=350,
                 justify="center").pack(padx=30, pady=(4, 6))
        form = tk.Frame(self.card, bg=BRANCO)
        form.pack(fill="x", padx=44)
        return form

    def _rodape(self, texto_bt, acao):
        self.erro = tk.Label(self.card, text="", fg=VERM_ESC, bg=BRANCO, font=(FONTE, 9), wraplength=350)
        self.erro.pack(padx=44, pady=(10, 0))
        ttk.Button(self.card, text=texto_bt, style="Azul.TButton", command=acao).pack(
            fill="x", padx=44, pady=(6, 28), ipady=4)
        self.winfo_toplevel().bind("<Return>", lambda e: acao())

    def _login(self):
        form = self._cabeca("Levantamento de Materiais",
                            "Entre com o usuário e a senha que o administrador passou para você.")
        self.v_login, self.v_senha = tk.StringVar(), tk.StringVar()
        e1 = _campo(form, "Usuário", self.v_login)
        self.e_senha = _campo(form, "Senha", self.v_senha, show="•")
        self.v_ver = tk.BooleanVar(value=False)
        ver = tk.Checkbutton(form, text="Mostrar senha", variable=self.v_ver, bg=BRANCO, fg=CINZA,
                             activebackground=BRANCO, font=(FONTE, 8), bd=0, highlightthickness=0,
                             command=lambda: self.e_senha.config(show="" if self.v_ver.get() else "•"))
        ver.pack(anchor="w", pady=(4, 0))
        self._rodape("Entrar", self.entrar)
        e1.focus_set()

    def _primeiro_acesso(self):
        form = self._cabeca("Primeiro acesso",
                            "Ainda não há nenhum usuário. Crie o administrador: é ele quem cria o "
                            "acesso das outras pessoas.")
        self.v_nome, self.v_login, self.v_senha, self.v_conf = (tk.StringVar() for _ in range(4))
        e = _campo(form, "Seu nome", self.v_nome)
        _campo(form, "Usuário", self.v_login, dica="Ex.: anderson.silva (minúsculas, sem espaço)")
        _campo(form, "Senha", self.v_senha, show="•", dica=f"Pelo menos {SENHA_MIN} caracteres.")
        _campo(form, "Confirmar senha", self.v_conf, show="•")
        self._rodape("Criar administrador e entrar", self.criar_admin)
        e.focus_set()

    def entrar(self):
        if not self.v_login.get().strip() or not self.v_senha.get():
            self.erro.config(text="Preencha o usuário e a senha.")
            return
        r = self.usuarios.autenticar(self.v_login.get(), self.v_senha.get())
        if isinstance(r, str):
            self.erro.config(text=r)
            self.v_senha.set("")
            self.e_senha.focus_set()
            return
        self.winfo_toplevel().unbind("<Return>")
        self.ao_entrar(r)

    def criar_admin(self):
        if self.v_senha.get() != self.v_conf.get():
            self.erro.config(text="As senhas não são iguais.")
            return
        try:
            self.usuarios.criar(self.v_login.get(), self.v_nome.get(), self.v_senha.get(), admin=True)
        except ValueError as ex:
            self.erro.config(text=str(ex))
            return
        except OSError as ex:
            self.erro.config(text=f"Não consegui gravar na pasta de dados:\n{ex}")
            return
        r = self.usuarios.autenticar(self.v_login.get(), self.v_senha.get())
        self.winfo_toplevel().unbind("<Return>")
        self.ao_entrar(r)


class TrocarSenha(tk.Toplevel):
    def __init__(self, pai, login):
        super().__init__(pai)
        self.title("Trocar minha senha")
        self.configure(bg=BRANCO)
        self.transient(pai.winfo_toplevel())
        self.resizable(False, False)
        self.login = login
        tk.Frame(self, bg=VERMELHO, height=3).pack(fill="x")
        f = tk.Frame(self, bg=BRANCO)
        f.pack(fill="both", padx=24, pady=(10, 0))
        tk.Label(f, text="Trocar minha senha", bg=BRANCO, fg=AZUL, font=(FONTE, 13, "bold")).pack(anchor="w")
        self.v = [tk.StringVar() for _ in range(3)]
        e = _campo(f, "Senha atual", self.v[0], show="•")
        _campo(f, "Nova senha", self.v[1], show="•", dica=f"Pelo menos {SENHA_MIN} caracteres.")
        _campo(f, "Confirmar nova senha", self.v[2], show="•")
        self.erro = tk.Label(self, text="", fg=VERM_ESC, bg=BRANCO, font=(FONTE, 9))
        self.erro.pack(padx=24, pady=(8, 0))
        b = tk.Frame(self, bg=BRANCO)
        b.pack(fill="x", padx=24, pady=(6, 18))
        ttk.Button(b, text="Salvar", style="Azul.TButton", command=self.ok).pack(side="right")
        ttk.Button(b, text="Cancelar", command=self.destroy).pack(side="right", padx=6)
        self.bind("<Return>", lambda e_: self.ok())
        self.bind("<Escape>", lambda e_: self.destroy())
        self.geometry("+%d+%d" % (pai.winfo_rootx() + 300, pai.winfo_rooty() + 120))
        e.focus_set()
        self.grab_set()

    def ok(self):
        atual, nova, conf = (v.get() for v in self.v)
        if isinstance(USUARIOS.autenticar(self.login, atual), str):
            self.erro.config(text="A senha atual está errada.")
            return
        if nova != conf:
            self.erro.config(text="As novas senhas não são iguais.")
            return
        try:
            USUARIOS.alterar(self.login, senha=nova)
        except (ValueError, OSError) as ex:
            self.erro.config(text=str(ex))
            return
        messagebox.showinfo("Senha", "Senha alterada.", parent=self)
        self.destroy()


class TelaUsuarios(tk.Frame):
    """Só para administradores: cria e controla quem pode acessar o programa."""
    PERFIS = ("Usuário", "Administrador")

    def __init__(self, pai, app):
        super().__init__(pai, bg=FUNDO)
        self.app = app
        self.editando = None
        cab = tk.Frame(self, bg=FUNDO)
        cab.pack(fill="x", padx=20, pady=(16, 10))
        ttk.Label(cab, text="Usuários", style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(cab, style="Sub.TLabel", wraplength=1100, justify="left",
                  text="Crie o usuário e a senha de cada pessoa que pode usar o programa e passe esses "
                       "dados para ela. Só administradores veem esta tela.").pack(anchor="w")
        corpo = tk.Frame(self, bg=FUNDO)
        corpo.pack(fill="both", expand=True, padx=20, pady=(0, 16))
        corpo.columnconfigure(0, weight=3, uniform="c")
        corpo.columnconfigure(1, weight=2, uniform="c")
        corpo.rowconfigure(0, weight=1)

        esq = cartao(corpo)
        esq.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.sec_lista = secao(esq, "Quem pode acessar")
        self.sec_lista.pack(anchor="w", padx=14, pady=(12, 8))
        self.tree = tabela(esq, [("login", "Usuário", 130), ("nome", "Nome", 220), ("perfil", "Perfil", 150),
                                 ("sit", "Situação", 90), ("ult", "Último acesso", 130)], altura=14)
        self.tree.quadro.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        self.tree.tag_configure("inativo", foreground="#9AA4B2")
        self.tree.tag_configure("admin", foreground=AZUL)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.abrir())

        dir_ = tk.Frame(corpo, bg=FUNDO)
        dir_.grid(row=0, column=1, sticky="nsew")
        ed = cartao(dir_)
        ed.pack(fill="x")
        self.sec_ed = secao(ed, "Novo usuário")
        self.sec_ed.pack(anchor="w", padx=14, pady=(12, 0))
        f = tk.Frame(ed, bg=BRANCO)
        f.pack(fill="x", padx=14)
        self.v_login, self.v_nome, self.v_senha, self.v_conf = (tk.StringVar() for _ in range(4))
        self.e_login = _campo(f, "Usuário (para entrar)", self.v_login,
                              dica="Minúsculas, sem espaço. Ex.: joao.souza")
        _campo(f, "Nome", self.v_nome)
        _campo(f, "Senha", self.v_senha, show="•")
        _campo(f, "Confirmar senha", self.v_conf, show="•")
        self.dica_senha = tk.Label(f, text="", bg=BRANCO, fg=CINZA, font=(FONTE, 8), anchor="w")
        self.dica_senha.pack(fill="x")
        tk.Label(f, text="Perfil", bg=BRANCO, fg=TEXTO, font=(FONTE, 9, "bold"), anchor="w").pack(fill="x", pady=(8, 2))
        self.v_perfil = tk.StringVar(value=self.PERFIS[0])
        cb = ttk.Combobox(f, textvariable=self.v_perfil, values=self.PERFIS, state="readonly")
        cb.pack(fill="x")
        cb.bind("<<ComboboxSelected>>", lambda e: self._perfil())
        self.v_editar = tk.BooleanVar(value=False)
        self.ck_editar = ttk.Checkbutton(f, text="Pode alterar o cadastro de materiais e os materiais extras",
                                         variable=self.v_editar)
        self.ck_editar.configure(style="Card.TCheckbutton")
        self.ck_editar.pack(anchor="w", pady=(8, 0))
        b = tk.Frame(ed, bg=BRANCO)
        b.pack(fill="x", padx=14, pady=14)
        ttk.Button(b, text="Novo", command=self.novo).pack(side="left")
        self.bt_ativo = ttk.Button(b, text="Desativar", command=self.ativar)
        self.bt_ativo.pack(side="left", padx=6)
        ttk.Button(b, text="Excluir", command=self.excluir).pack(side="left")
        ttk.Button(b, text="Salvar", style="Verm.TButton", command=self.salvar).pack(side="right")

        ex = cartao(dir_)
        ex.pack(fill="both", expand=True, pady=(12, 0))
        secao(ex, "Como liberar o acesso").pack(anchor="w", padx=14, pady=(12, 6))
        tk.Label(ex, bg=BRANCO, fg=TEXTO, font=(FONTE, 9), justify="left", anchor="nw", wraplength=440,
                 text="1.  Preencha usuário, nome e senha e clique em Salvar.\n"
                      "2.  Passe para a pessoa o usuário, a senha e onde está o programa.\n"
                      "3.  Ela pode trocar a senha em \"Trocar minha senha\", no menu.\n"
                      "4.  Para bloquear alguém, use Desativar (pode reativar depois) ou Excluir.\n"
                      "5.  Esqueceu a senha? Selecione a pessoa, digite uma senha nova e Salvar.\n\n"
                      "Administrador: faz tudo, inclusive criar usuários.\n"
                      "Usuário: usa o programa; altera cadastro e extras só se a opção estiver marcada.").pack(
            fill="both", padx=14, pady=(0, 14))
        self.novo()

    def _perfil(self):
        adm = self.v_perfil.get() == "Administrador"
        if adm:
            self.v_editar.set(True)
        self.ck_editar.state(["disabled"] if adm else ["!disabled"])

    def atualizar(self):
        USUARIOS.carregar()
        t = self.tree
        sel = t.selection()
        t.delete(*t.get_children())
        for login, u in sorted(USUARIOS.lista.items()):
            perfil = "Administrador" if u["admin"] else ("Usuário (edita)" if u.get("editar") else "Usuário")
            tags = [] if u.get("ativo", True) else ["inativo"]
            if u["admin"]:
                tags.append("admin")
            t.insert("", "end", iid=login, values=(login, u["nome"], perfil,
                                                   "Ativo" if u.get("ativo", True) else "Desativado",
                                                   ultimo_acesso(login, u)), tags=tags)
        self.sec_lista.rotulo.config(text=f"Quem pode acessar ({len(USUARIOS.lista)})")
        for s in sel:
            if t.exists(s):
                t.selection_set(s)

    def novo(self):
        self.editando = None
        self.tree.selection_remove(*self.tree.selection())
        for v in (self.v_login, self.v_nome, self.v_senha, self.v_conf):
            v.set("")
        self.v_perfil.set(self.PERFIS[0])
        self.v_editar.set(False)
        self._perfil()
        self.e_login.state(["!disabled"])
        self.sec_ed.rotulo.config(text="Novo usuário")
        self.dica_senha.config(text=f"Pelo menos {SENHA_MIN} caracteres.")
        self.bt_ativo.config(text="Desativar")
        self.e_login.focus_set()

    def abrir(self):
        s = self.tree.selection()
        if not s:
            return
        self.editando = s[0]
        u = USUARIOS.lista[self.editando]
        self.v_login.set(self.editando)
        self.v_nome.set(u["nome"])
        self.v_senha.set("")
        self.v_conf.set("")
        self.v_perfil.set("Administrador" if u["admin"] else "Usuário")
        self.v_editar.set(bool(u.get("editar")))
        self._perfil()
        self.e_login.state(["disabled"])
        self.sec_ed.rotulo.config(text=f"Editar: {self.editando}")
        self.dica_senha.config(text="Deixe a senha em branco para manter a atual.")
        self.bt_ativo.config(text="Desativar" if u.get("ativo", True) else "Ativar")

    def salvar(self):
        senha = self.v_senha.get()
        if senha != self.v_conf.get():
            messagebox.showwarning("Usuários", "As senhas não são iguais.")
            return
        adm = self.v_perfil.get() == "Administrador"
        try:
            if self.editando is None:
                if not senha:
                    messagebox.showwarning("Usuários", "Informe a senha do novo usuário.")
                    return
                USUARIOS.criar(self.v_login.get(), self.v_nome.get(), senha, admin=adm,
                               editar=self.v_editar.get())
                login = Usuarios.normaliza(self.v_login.get())
                msg = (f"Usuário criado.\n\nPasse para {self.v_nome.get().strip()}:\n"
                       f"   Usuário: {login}\n   Senha: (a que você digitou)")
            else:
                login = self.editando
                if login == self.app.usuario.get("login") and not adm:
                    messagebox.showwarning("Usuários", "Você não pode tirar o seu próprio perfil de administrador.")
                    return
                USUARIOS.alterar(login, nome=self.v_nome.get(), admin=adm, editar=self.v_editar.get(),
                                 senha=senha or None)
                msg = "Alterações salvas." + ("\nA senha foi trocada." if senha else "")
        except (ValueError, OSError) as ex:
            messagebox.showwarning("Usuários", str(ex))
            return
        self.atualizar()
        self.tree.selection_set(login)
        messagebox.showinfo("Usuários", msg)

    def ativar(self):
        if self.editando is None:
            return
        if self.editando == self.app.usuario.get("login"):
            messagebox.showwarning("Usuários", "Você não pode desativar o seu próprio acesso.")
            return
        ativo = not USUARIOS.lista[self.editando].get("ativo", True)
        try:
            USUARIOS.alterar(self.editando, ativo=ativo)
        except (ValueError, OSError) as ex:
            messagebox.showwarning("Usuários", str(ex))
            return
        self.atualizar()
        self.abrir()

    def excluir(self):
        if self.editando is None:
            return
        if self.editando == self.app.usuario.get("login"):
            messagebox.showwarning("Usuários", "Você não pode excluir o seu próprio acesso.")
            return
        if not messagebox.askyesno("Usuários", f"Excluir o acesso de {self.editando}?"):
            return
        try:
            USUARIOS.remover(self.editando)
        except (ValueError, OSError) as ex:
            messagebox.showwarning("Usuários", str(ex))
            return
        self.novo()
        self.atualizar()
