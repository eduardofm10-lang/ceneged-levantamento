"""Abre o programa Levantamento de Materiais (Ceneged).

    python iniciar.py

É também o arquivo usado pelo PyInstaller para gerar o .exe (veja instalador/).
"""
from ceneged.interface.principal import main

if __name__ == "__main__":
    main()
