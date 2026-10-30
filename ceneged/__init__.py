"""Levantamento de materiais a partir dos balões de projetos elétricos em PDF (Ceneged).

Camadas (cada uma só usa as de baixo):
    interface   -> telas (Tkinter)
    servicos    -> casos de uso: ler um projeto, exportar, carregar normativos
    dominio     -> regras de negócio: balões, normativos, postes, cerca, relatório
    dados       -> banco SQLite, modo OneDrive, planilhas, usuários
    leitura_pdf -> visão computacional: balões, textos, rede de cabos
    comum       -> funções pequenas usadas por todos
"""

__version__ = "1.0"
