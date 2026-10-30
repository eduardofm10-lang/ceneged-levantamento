"""Ponto de partida: monta a janela e abre o programa.

Parte do programa Levantamento de Materiais (Ceneged)."""

import tkinter as tk
from tkinter import messagebox

from ceneged.dados.caminhos import (fixar_pasta_no_computador, modo_onedrive)
from ceneged.dados.onedrive import (CONFLITOS_OD, od_copia_do_dia)
from ceneged.dados.mongo import (SemBanco, mongo_copia_do_dia)
from ceneged.dados.atualizacao import (atualizacao_disponivel, instalar_atualizacao,
    versao_instalada)
from ceneged.dados.usuarios import USUARIOS
from ceneged.dados.tabelas_visao import conferir_tabelas_visao
from ceneged.interface.tema import (_ICONE_PNG, _imagem, aplicar_tema)
from ceneged.interface.login import TelaLogin
from ceneged.interface.app import App

def main():
    root = tk.Tk()
    root.title("Ceneged · Levantamento de materiais")
    root.geometry("1500x900")
    root.minsize(1100, 650)
    aplicar_tema(root)
    icone = _imagem(_ICONE_PNG)
    if icone:
        try:
            root.iconphoto(True, icone)
        except tk.TclError:
            pass

    def limpar():
        for w in root.winfo_children():
            w.destroy()
        for ev in ("<Escape>", "<Return>"):
            root.unbind(ev)

    def entrar(usuario):
        limpar()
        try:
            root.state("zoomed")              # tela cheia no Windows
        except tk.TclError:
            pass
        App(root, usuario, ao_sair=sair)
        if usuario.get("admin"):
            root.after(3000, mongo_copia_do_dia)

    def sair():
        limpar()
        TelaLogin(root, USUARIOS, entrar).pack(fill="both", expand=True)

    sair()
    root.after(400, lambda: oferecer_atualizacao(root))
    root.after(1500, od_copia_do_dia)
    root.after(6000, conferir_tabelas_visao)

    def erro_na_tela(tipo, valor, tb):
        if isinstance(valor, SemBanco):
            messagebox.showerror("Sem conexão com o banco de dados",
                                 f"{valor}\n\nO que você acabou de fazer NÃO foi salvo. "
                                 "Quando a conexão voltar, faça de novo.", parent=root)
        else:                       # outros erros: igual antes (só registra)
            import traceback
            traceback.print_exception(tipo, valor, tb)
    root.report_callback_exception = erro_na_tela
    root.after(3000, lambda: modo_onedrive() and fixar_pasta_no_computador())
    root.after(2500, lambda: avisar_conflitos_od(root))
    root.mainloop()


def avisar_conflitos_od(root):
    """Modo OneDrive: avisa quando juntou cópias em conflito (e confere de novo a cada 2 min)."""
    if CONFLITOS_OD:
        lista = "\n".join("• " + c for c in CONFLITOS_OD[:15])
        CONFLITOS_OD.clear()
        messagebox.showinfo(
            "OneDrive", "O OneDrive tinha duas versões de alguns dados (duas pessoas gravaram quase ao "
                        "mesmo tempo). Juntei as duas automaticamente:\n\n" + lista +
                        "\n\nConfira se está tudo certo. As cópias originais ficaram em dados\\_conflitos.",
            parent=root)
    if modo_onedrive():
        try:
            root.after(120000, lambda: avisar_conflitos_od(root))
        except tk.TclError:
            pass


def oferecer_atualizacao(root):
    try:
        nova = atualizacao_disponivel()
    except Exception:
        return
    if not nova:
        return
    versao, inst = nova
    if messagebox.askyesno(
            "Nova versão disponível",
            f"Existe uma versão nova do programa: {versao}\n(a instalada é {versao_instalada()}).\n\n"
            "Atualizar agora? Leva menos de um minuto e o programa abre de novo sozinho.",
            parent=root):
        aviso = tk.Toplevel(root)
        aviso.title("Atualização")
        aviso.transient(root)
        tk.Label(aviso, text=f"Baixando a versão {versao}...\nAguarde, o programa vai fechar e abrir de novo.",
                 padx=30, pady=20).pack()
        aviso.update()
        try:
            instalar_atualizacao(inst)
        except Exception as ex:
            aviso.destroy()
            messagebox.showerror("Atualização", f"Não consegui iniciar a atualização:\n{ex}", parent=root)
            return
        root.destroy()
