"""Atualização automática do programa instalado.

Parte do programa Levantamento de Materiais (Ceneged)."""

import os
import re
import shutil
import sys

from ceneged.dados.caminhos import (modo_mongo, pasta_dados, pasta_programa)
from ceneged.dados.mongo import (mongo_baixar_instalador, mongo_programa_publicado)

# ---------------------------------------------------------------------------
#  Atualização automática: o GERAR_INSTALADOR.bat coloca o instalador novo em
#  <pasta compartilhada>\atualizacao\ junto com versao.txt. Ao abrir, o
#  programa compara com a versão instalada e oferece atualizar.
# ---------------------------------------------------------------------------

def _versao_tupla(v):
    return tuple(int(x) for x in re.findall(r"\d+", v or "")) or (0,)


def _ler_versao(arq):
    try:
        with open(arq, encoding="utf-8-sig") as f:
            return f.read().strip()
    except (OSError, ValueError):
        return ""


def versao_instalada():
    return _ler_versao(os.path.join(pasta_programa(), "versao.txt"))


def atualizacao_disponivel():
    """-> (versão nova, caminho do instalador) ou None."""
    if not getattr(sys, "frozen", False):          # rodando pelo .py: não atualiza
        return None
    if modo_mongo():                               # versão nova guardada no próprio banco
        info = mongo_programa_publicado()
        atual = versao_instalada()
        if info and info.get("versao") and _versao_tupla(info["versao"]) > _versao_tupla(atual or "0"):
            return info["versao"], info
        return None
    pasta = os.path.join(pasta_dados(), "atualizacao")
    nova = _ler_versao(os.path.join(pasta, "versao.txt"))
    inst = os.path.join(pasta, "Instalar_CenegedLevantamento.exe")
    atual = versao_instalada()
    if nova and os.path.isfile(inst) and _versao_tupla(nova) > _versao_tupla(atual or "0"):
        return nova, inst
    return None


def instalar_atualizacao(inst):
    """Copia o instalador para a pasta temporária e roda em modo silencioso.
    O instalador fecha este programa, atualiza e abre de novo."""
    import subprocess
    import tempfile
    destino = os.path.join(tempfile.gettempdir(), "Instalar_CenegedLevantamento.exe")
    if isinstance(inst, dict):                     # versão guardada no banco: baixa primeiro
        mongo_baixar_instalador(inst, destino)
    else:
        shutil.copy2(inst, destino)
    subprocess.Popen([destino, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"],
                     close_fds=True)
