"""Teste de regressão com PDFs reais: confere se uma mudança alterou a leitura.

Os PDFs são projetos de cliente e NÃO vão para o GitHub (estão no .gitignore).
Cada pessoa coloca os seus em  testes/pdfs/.

1) Antes de mudar o código, grave o resultado atual (a "foto"):
       python testes/regressao.py --gravar
2) Depois da mudança, compare:
       python testes/regressao.py
   Mostra, projeto a projeto, o que mudou nos balões e no relatório.

Use uma cópia dos dados (ceneged.db) em  testes/dados/  para o relatório sair igual ao da
empresa; sem ela, o relatório sai só com o cadastro vazio (os balões continuam valendo).
"""
import json
import os
import sys
import traceback

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)
os.environ.setdefault("CENEGED_DADOS", os.path.join(AQUI, "dados"))

from ceneged.servicos.projeto import Arquivo  # noqa: E402

PASTA_PDFS = os.path.join(AQUI, "pdfs")
PASTA_FOTO = os.path.join(AQUI, "esperado")


def ler(caminho):
    """Resultado de um PDF em forma comparável (balões + relatório)."""
    a = Arquivo(caminho)
    p = a.pagina(0)
    p.processar()
    return {
        "baloes": [[b["texto"], b.get("poste_existente")] for b in p.baloes],
        "relatorio": [{k: (sorted(v) if isinstance(v, set) else v) for k, v in l.items()
                       if k in ("codigo", "material", "qtd", "pendente")} for l in a.relatorio()],
    }


def main():
    gravar = "--gravar" in sys.argv
    if not os.path.isdir(PASTA_PDFS):
        print("Crie a pasta testes/pdfs e coloque PDFs de projetos nela.")
        return 1
    os.makedirs(PASTA_FOTO, exist_ok=True)
    pdfs = sorted(f for f in os.listdir(PASTA_PDFS) if f.lower().endswith(".pdf"))
    mudou = 0
    for nome in pdfs:
        foto = os.path.join(PASTA_FOTO, nome + ".json")
        try:
            r = ler(os.path.join(PASTA_PDFS, nome))
        except Exception:
            r = {"erro": traceback.format_exc()[-800:]}
        if gravar:
            with open(foto, "w", encoding="utf-8") as f:
                json.dump(r, f, ensure_ascii=False, indent=1)
            print("gravado ", nome)
            continue
        if not os.path.exists(foto):
            print("SEM FOTO", nome, "(rode com --gravar)")
            continue
        antes = json.load(open(foto, encoding="utf-8"))
        if antes == json.loads(json.dumps(r, ensure_ascii=False)):
            print("igual   ", nome)
            continue
        mudou += 1
        print("MUDOU   ", nome)
        for k in ("baloes", "relatorio", "erro"):
            a, d = antes.get(k), r.get(k)
            if a != d:
                sa = {json.dumps(x, ensure_ascii=False) for x in (a or [])} if isinstance(a, list) else {str(a)}
                sd = {json.dumps(x, ensure_ascii=False) for x in (d or [])} if isinstance(d, list) else {str(d)}
                for x in sorted(sa - sd):
                    print("      -", k, x)
                for x in sorted(sd - sa):
                    print("      +", k, x)
    if not gravar:
        print("\n%d de %d projetos mudaram." % (mudou, len(pdfs)))
    return 1 if mudou else 0


if __name__ == "__main__":
    sys.exit(main())
