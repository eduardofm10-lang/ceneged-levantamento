"""Usuários, login e senhas.

Parte do programa Levantamento de Materiais (Ceneged)."""

import os
import re
import hashlib
import hmac
import secrets
import time

from ceneged.comum.texto import _sem_acento
from ceneged.dados.caminhos import (modo_mongo, modo_onedrive, pasta_dados)
from ceneged.dados.onedrive import od_registrar_acesso
from ceneged.dados.mongo import mongo_registrar_acesso
from ceneged.dados.armazenamento import (ler_dados, salvar_json)

# ---------------------------------------------------------------------------
#  Usuários (login e senha). O administrador cria os acessos.
#  As senhas não ficam escritas no arquivo: só um "hash" (PBKDF2-SHA256).
# ---------------------------------------------------------------------------
ARQ_USUARIOS = os.path.join(pasta_dados(), "ceneged_usuarios.json")
RE_LOGIN = re.compile(r"^[a-z0-9._-]{3,30}$")
SENHA_MIN = 6


class Usuarios:
    def __init__(self, caminho):
        self.caminho = caminho
        self.lista = {}
        self.carregar()

    def carregar(self):
        try:
            self.lista = ler_dados(self.caminho).get("usuarios", {})
        except (OSError, ValueError):
            self.lista = {}

    def salvar(self):
        salvar_json(self.caminho, {"usuarios": self.lista})

    def vazio(self):
        self.carregar()
        return not self.lista

    @staticmethod
    def _hash(senha, sal):
        return hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), bytes.fromhex(sal), 200_000).hex()

    @staticmethod
    def normaliza(login):
        return _sem_acento(login).strip().lower()

    def validar(self, login, nome, senha, novo=True):
        if novo and not RE_LOGIN.match(login):
            return "Usuário: de 3 a 30 letras minúsculas, números, ponto, hífen ou _ (sem espaço)."
        if novo and login in self.lista:
            return f"O usuário \"{login}\" já existe."
        if not nome.strip():
            return "Informe o nome da pessoa."
        if senha is not None and len(senha) < SENHA_MIN:
            return f"A senha precisa ter pelo menos {SENHA_MIN} caracteres."
        return None

    def criar(self, login, nome, senha, admin=False, editar=False):
        self.carregar()
        login = self.normaliza(login)
        erro = self.validar(login, nome, senha)
        if erro:
            raise ValueError(erro)
        sal = secrets.token_hex(16)
        self.lista[login] = {"nome": nome.strip(), "sal": sal, "hash": self._hash(senha, sal),
                             "admin": bool(admin), "editar": bool(admin or editar), "ativo": True,
                             "criado": time.strftime("%d/%m/%Y %H:%M"), "ultimo_acesso": ""}
        self.salvar()

    def alterar(self, login, nome=None, admin=None, editar=None, ativo=None, senha=None):
        self.carregar()
        u = self.lista[login]
        if senha is not None:
            if len(senha) < SENHA_MIN:
                raise ValueError(f"A senha precisa ter pelo menos {SENHA_MIN} caracteres.")
            u["sal"] = secrets.token_hex(16)
            u["hash"] = self._hash(senha, u["sal"])
        if nome is not None:
            if not nome.strip():
                raise ValueError("Informe o nome da pessoa.")
            u["nome"] = nome.strip()
        perde_admin = (admin is False and u["admin"]) or (ativo is False and u["admin"])
        if perde_admin and self._admins_ativos() <= 1:
            raise ValueError("Tem que existir pelo menos um administrador ativo.")
        if admin is not None:
            u["admin"] = bool(admin)
        if editar is not None or admin is not None:
            u["editar"] = bool(u["admin"] or (editar if editar is not None else u.get("editar")))
        if ativo is not None:
            u["ativo"] = bool(ativo)
        self.salvar()

    def remover(self, login):
        self.carregar()
        if self.lista[login]["admin"] and self.lista[login]["ativo"] and self._admins_ativos() <= 1:
            raise ValueError("Não dá para excluir o único administrador.")
        del self.lista[login]
        self.salvar()

    def _admins_ativos(self):
        return sum(1 for u in self.lista.values() if u["admin"] and u["ativo"])

    def autenticar(self, login, senha):
        """-> dados do usuário (com "login") ou mensagem de erro (str)."""
        self.carregar()
        login = self.normaliza(login)
        u = self.lista.get(login)
        if not u or not hmac.compare_digest(u["hash"], self._hash(senha, u["sal"])):
            return "Usuário ou senha incorretos."
        if not u.get("ativo", True):
            return "Este acesso está desativado. Fale com o administrador."
        if modo_mongo():
            mongo_registrar_acesso(login)
        elif modo_onedrive():
            od_registrar_acesso(login)
        else:
            u["ultimo_acesso"] = time.strftime("%d/%m/%Y %H:%M")
            try:
                self.salvar()
            except OSError:
                pass
        return dict(u, login=login)


USUARIOS = Usuarios(ARQ_USUARIOS)
