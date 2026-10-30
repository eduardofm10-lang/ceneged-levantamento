"""Publica o instalador novo no banco MongoDB, para os programas instalados oferecerem a
atualização sozinhos. Quem roda é o GERAR_INSTALADOR.bat (não precisa abrir este arquivo).

    python publicar_atualizacao.py <banco_mongo.txt> <Instalar_CenegedLevantamento.exe> <versão>
"""
import hashlib
import os
import re
import sys
import time
from urllib.parse import quote_plus, unquote_plus

PARTE = 4 * 1024 * 1024           # 4 MB por documento (o limite do MongoDB é 16 MB)


def ler_uri(arq):
    with open(arq, encoding="utf-8-sig") as f:
        for linha in f:
            linha = linha.strip()
            if linha.startswith(("mongodb://", "mongodb+srv://", "mongomock://")):
                m = re.match(r"^(mongodb(?:\+srv)?://)([^:/@]+):(.*)@([^@/]+(?:/.*)?)$", linha)
                if m:
                    linha = m.group(1) + m.group(2) + ":" + quote_plus(unquote_plus(m.group(3))) + "@" + m.group(4)
                return linha
    raise SystemExit("banco_mongo.txt sem o endereço do banco (linha mongodb+srv://...).")


def conectar(uri):
    if uri.startswith("mongomock://"):
        import mongomock
        cli = mongomock.MongoClient()
    else:
        import pymongo
        cli = pymongo.MongoClient(uri, serverSelectionTimeoutMS=15000, appname="CenegedPublicar")
    try:
        return cli.get_default_database("ceneged")
    except Exception:
        return cli["ceneged"]


def publicar(db, exe, versao):
    with open(exe, "rb") as f:
        dados = f.read()
    partes = [dados[i:i + PARTE] for i in range(0, len(dados), PARTE)]
    for n, p in enumerate(partes):                       # 1) sobe as partes da versão nova
        db.instalador.replace_one({"_id": f"{versao}|{n}"},
                                  {"_id": f"{versao}|{n}", "versao": versao, "n": n, "dados": p},
                                  upsert=True)
        print(f"   parte {n + 1} de {len(partes)} enviada", flush=True)
    db.conjuntos.replace_one({"_id": "_programa"}, {      # 2) só agora a versão nova vale
        "_id": "_programa", "versao": versao, "partes": len(partes), "tamanho": len(dados),
        "sha256": hashlib.sha256(dados).hexdigest(), "publicado_em": time.strftime("%d/%m/%Y %H:%M"),
        "publicado_por": os.environ.get("USERNAME", "")}, upsert=True)
    db.instalador.delete_many({"versao": {"$ne": versao}})   # 3) apaga as versões antigas


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    banco, exe, versao = sys.argv[1:]
    try:
        publicar(conectar(ler_uri(banco)), exe, versao)
    except SystemExit:
        raise
    except Exception as ex:
        print(f"ERRO ao publicar no banco: {type(ex).__name__}: {ex}")
        sys.exit(1)
    print(f"   versão {versao} publicada no banco de dados")
