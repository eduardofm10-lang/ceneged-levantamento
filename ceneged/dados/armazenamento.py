"""Leitura/gravação dos conjuntos de dados (escolhe banco ou OneDrive) e configurações.

Parte do programa Levantamento de Materiais (Ceneged)."""

import json
import os
import sqlite3

from ceneged.dados.caminhos import (modo_mongo, modo_onedrive, pasta_dados)
from ceneged.dados.banco import (_banco, _gravar_banco, _nome_dados)
from ceneged.dados.onedrive import (od_ler_dados, od_salvar, od_versao)
from ceneged.dados.mongo import (mongo_ler_dados, mongo_salvar, mongo_versao)

def ler_dados(caminho):
    """Conteúdo de um conjunto de dados (dict). Vem do banco; se ainda não estiver nele,
    vem do .json antigo (e já é copiado para o banco). Sem nenhum dos dois: OSError."""
    if modo_mongo():
        return mongo_ler_dados(caminho)
    if modo_onedrive():
        return od_ler_dados(caminho)
    nome = _nome_dados(caminho)
    try:
        con = _banco()
        try:
            row = con.execute("SELECT conteudo FROM dados WHERE nome = ?", (nome,)).fetchone()
        finally:
            con.close()
    except sqlite3.Error:
        row = None
        with open(caminho, encoding="utf-8") as f:          # banco fora do ar: usa o .json
            return json.load(f)
    if row is not None:
        return json.loads(row[0])
    with open(caminho, encoding="utf-8") as f:              # migração: .json -> banco
        d = json.load(f)
    try:
        _gravar_banco(nome, d)
    except sqlite3.Error:
        pass
    return d


def versao_dados(caminho):
    """Marca de alteração (para reler quando outra pessoa grava): a versão no banco."""
    if modo_mongo():
        return mongo_versao(caminho)
    if modo_onedrive():
        return od_versao(caminho)
    try:
        con = _banco()
        try:
            row = con.execute("SELECT versao, alterado FROM dados WHERE nome = ?",
                              (_nome_dados(caminho),)).fetchone()
        finally:
            con.close()
        if row is not None:
            return f"{row[0]}|{row[1]}"
    except sqlite3.Error:
        pass
    try:
        return os.path.getmtime(caminho)
    except OSError:
        return None


def salvar_json(caminho, dados):
    """Grava o conjunto de dados no banco. Se o banco não abrir, grava no .json (sem
    deixar o arquivo pela metade: outra pessoa pode estar lendo)."""
    if modo_mongo():
        mongo_salvar(caminho, dados)
        return
    if modo_onedrive():
        od_salvar(caminho, dados)
        return
    try:
        _gravar_banco(_nome_dados(caminho), dados)
        return
    except sqlite3.Error:
        pass
    tmp = caminho + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=1)
    os.replace(tmp, caminho)


ARQ_CADASTRO = os.path.join(pasta_dados(), "ceneged_cadastro.json")
ARQ_COMPOSICOES = os.path.join(pasta_dados(), "ceneged_composicoes.json")
CONFIG_PADRAO = {"regiao": "Nordeste",        # coluna de código dos normativos
                 "kv": "auto",                # tensão da rede MT: auto | 15 | 36.2
                 "poste_padrao": "circular",  # quando o nome do poste não diz se é DT ou circular
                 "estruturas_normativo": True,  # estruturas dos normativos no lugar das composições
                 "conector_nua": "compressao",  # rede nua (DIS-NOR-018 Tabela 1): compressao | cunha
                 "conectores_flbit": 4}  # conectores perfurantes do FLBIT/FLABIT do normativo (meio de rede)
