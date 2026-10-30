"""Garante a regra das camadas: cada camada só importa as de baixo.

    comum < leitura_pdf < dados < dominio < servicos < interface

Se este teste falhar, alguém importou "para cima" (ex.: dominio importando interface).
"""
import ast
import os
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NIVEL = {"comum": 0, "leitura_pdf": 1, "dados": 2, "dominio": 3, "servicos": 4, "interface": 5}


def imports_do_pacote():
    pasta = os.path.join(RAIZ, "ceneged")
    for raiz, _, arquivos in os.walk(pasta):
        for nome in arquivos:
            if not nome.endswith(".py"):
                continue
            caminho = os.path.join(raiz, nome)
            camada = os.path.relpath(caminho, pasta).split(os.sep)[0]
            if camada not in NIVEL:
                continue
            arvore = ast.parse(open(caminho, encoding="utf-8").read())
            for n in ast.walk(arvore):
                if isinstance(n, ast.ImportFrom) and (n.module or "").startswith("ceneged."):
                    yield caminho, camada, n.module.split(".")[1], n.lineno


class Camadas(unittest.TestCase):
    def test_ninguem_importa_para_cima(self):
        erros = ["%s:%d importa %s (camada de cima)" % (os.path.relpath(c, RAIZ), ln, alvo)
                 for c, camada, alvo, ln in imports_do_pacote() if NIVEL[alvo] > NIVEL[camada]]
        self.assertEqual(erros, [])


if __name__ == "__main__":
    unittest.main()
