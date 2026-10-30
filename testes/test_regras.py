"""Testes rápidos das regras (não precisam de PDF nem de tela).

Rodar, na pasta do repositório:
    python -m unittest discover -s testes -v
"""
import os
import sys
import tempfile
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
# os testes usam uma pasta de dados vazia e temporária: nunca mexem nos dados de verdade
os.environ["CENEGED_DADOS"] = tempfile.mkdtemp(prefix="ceneged_teste_")

from ceneged.comum.texto import chave_nome, formata_num, info_poste, semelhanca  # noqa: E402
from ceneged.dominio.baloes import materiais_do_balao, multiplicador  # noqa: E402
from ceneged.dominio.postes import _dim_no_ponto, _faixas_da_desc, tipo_do_poste  # noqa: E402
from ceneged.dominio.relatorio import montar_relatorio  # noqa: E402
from ceneged.dados.onedrive import _juntar  # noqa: E402
from ceneged.leitura_pdf.deteccao import _num_metros  # noqa: E402


class TextoDoBalao(unittest.TestCase):
    def test_multiplicador(self):
        self.assertEqual(multiplicador("2x ESTAI DE SOLO"), (2, "ESTAI DE SOLO"))
        # no código do cabo o "3x" fica no nome (continua ligado ao cadastro)
        self.assertEqual(multiplicador("3xS04-13,8kV"), (3, "3xS04-13,8kV"))
        self.assertEqual(multiplicador("CE1"), (1, "CE1"))

    def test_materiais_do_balao(self):
        self.assertEqual(materiais_do_balao({"texto": "2x ESTAI DE SOLO"}), [("ESTAI DE SOLO", "UN", 2)])
        self.assertEqual(materiais_do_balao({"texto": "PB70 45M"}), [("PB70", "M", 45)])

    def test_metros(self):
        self.assertEqual(_num_metros("16,5"), 16.5)
        self.assertEqual(_num_metros("45"), 45)


class Nomes(unittest.TestCase):
    def test_chave_nome(self):
        self.assertEqual(chave_nome("Conector ação-10"), "CONECTORACAO10")

    def test_semelhanca_numeros_tem_que_bater(self):
        self.assertGreater(semelhanca("PB35", "CABO PB35"), 0.8)
        self.assertEqual(semelhanca("PB35", "CABO PB70"), 0.0)     # PB35 nunca vira PB70

    def test_formata_num(self):
        self.assertEqual(formata_num(2.0), "2")
        self.assertEqual(formata_num(16.5), "16,5")


class Postes(unittest.TestCase):
    def test_info_poste(self):
        self.assertEqual(info_poste("11400FV"), {"altura": 11, "esforco": 400, "tipo": "circular", "fibra": True})
        self.assertEqual(info_poste("400/9")["altura"], 9)
        self.assertIsNone(info_poste("PB70"))

    def test_tipo_escrito_no_balao_vale(self):
        self.assertEqual(tipo_do_poste(info_poste("12600D")), "dt")
        self.assertEqual(tipo_do_poste(info_poste("11400FV")), "circular")

    def test_diametro_no_ponto(self):
        g = {"l": 12, "topo": 140, "base": 300}
        self.assertEqual(_dim_no_ponto(g, "circular", 6), 220)

    def test_faixas(self):
        self.assertEqual(_faixas_da_desc("CONEC PERF RD COMPACTA 35-70 MM/35-70 MM"), [[35.0, 70.0], [35.0, 70.0]])


class Relatorio(unittest.TestCase):
    def test_metros_do_mesmo_cabo_somam(self):
        r = montar_relatorio([(("a.pdf", 0, 1), {"texto": "PB70 45M"}),
                              (("a.pdf", 0, 2), {"texto": "PB70 30M"})])
        self.assertEqual([(l["material"], l["unidade"], l["qtd"]) for l in r], [("PB70", "M", 75)])


class OneDrive(unittest.TestCase):
    def test_juntar_conflito(self):
        a = {"a": 1, "l": [{"id": 1, "v": 1}]}
        b = {"b": 2, "l": [{"id": 1, "v": 2}, {"id": 2}]}       # b é a versão mais nova
        self.assertEqual(_juntar(a, b), {"a": 1, "b": 2, "l": [{"id": 1, "v": 2}, {"id": 2}]})


class PastaCompartilhada(unittest.TestCase):
    def test_acha_a_pasta_no_onedrive(self):
        from ceneged.dados.caminhos import procurar_pasta_dados
        od = tempfile.mkdtemp(prefix="onedrive_")
        certa = os.path.join(od, "Levantamento")
        os.makedirs(os.path.join(certa, "dados"))
        open(os.path.join(certa, "dados", "usuarios.json"), "w").write("{}")
        os.makedirs(os.path.join(od, "Pessoal", "Fotos"))
        antigo = os.environ.get("OneDriveCommercial")
        os.environ["OneDriveCommercial"] = od
        try:
            self.assertEqual(procurar_pasta_dados("Levantamento", forcar=True), certa)
        finally:
            if antigo is None:
                os.environ.pop("OneDriveCommercial", None)
            else:
                os.environ["OneDriveCommercial"] = antigo


class BancoMongo(unittest.TestCase):
    def test_senha_com_caracteres_especiais(self):
        from ceneged.dados.mongo import _uri_mongo
        self.assertEqual(_uri_mongo("mongodb+srv://u:p@ss:w/rd@cluster0.x.mongodb.net/ceneged?w=majority"),
                         "mongodb+srv://u:p%40ss%3Aw%2Frd@cluster0.x.mongodb.net/ceneged?w=majority")

    def test_chaves_com_ponto_viram_texto(self):
        from ceneged.dados.mongo import _do_banco, _para_banco
        d = {"PB 1.5": "123", "ok": {"a": 1}}
        self.assertIn("_json", _para_banco(d))
        self.assertEqual(_do_banco(_para_banco(d)), d)
        self.assertEqual(_para_banco({"a": [1, {"b": 2}]}), {"a": [1, {"b": 2}]})


if __name__ == "__main__":
    unittest.main()
