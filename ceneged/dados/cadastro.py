"""Cadastro de materiais (nome usado na empresa).

Parte do programa Levantamento de Materiais (Ceneged)."""

import re

from ceneged.comum.texto import (_sem_acento, chave_nome, normaliza_codigo, semelhanca)
from ceneged.dados.armazenamento import (ARQ_CADASTRO, CONFIG_PADRAO, ler_dados, salvar_json,
    versao_dados)

NEUTRO_MULTIPLEXADO = {16: 16, 25: 25, 35: 35, 50: 35, 70: 50, 95: 70, 120: 70, 150: 70, 185: 95}


def bitolas_do_cabo(nome):
    """'3x70+1x50' -> (70, 50); 'PB35' -> (35, 35); 'PB70' -> (70, 50)."""
    t = _sem_acento(nome).upper().replace(",", ".")
    m = re.search(r"\d\s*X\s*(\d+(?:\.\d+)?)\s*\+\s*\d\s*X\s*(\d+(?:\.\d+)?)", t)
    if m:
        return float(m.group(1)), float(m.group(2))
    t = re.sub(r"\d+(\.\d+)?\s*KV", " ", t)
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", t)]
    nums = [x for x in nums if x >= 10]
    if not nums:
        return None
    f = nums[-1]
    return f, float(NEUTRO_MULTIPLEXADO.get(int(f), int(f)))


class Cadastro:
    """Guarda (num .json ao lado do programa) os nomes cadastrados, os ajustes
    manuais de nome e as regras de materiais extras."""
    LIMITE = 0.65                     # nota mínima para aceitar um nome parecido

    def __init__(self, caminho=None):
        self.caminho = caminho
        self.materiais = []           # nomes como a empresa usa
        self.de_para = {}             # chave_nome(nome do projeto) -> nome escolhido à mão
        self.extras = []              # [{"principal": nome, "itens": [[nome, qtd], ...]}]
        self.codigos = {}             # chave_nome(nome do cadastro) -> código
        self.apelidos = {}            # chave_nome(estrutura) -> [nomes usados nos projetos]
        self.escolhas = {}            # "norma|Tabela N|alvo" -> código escolhido ("" = não usar)
        self.config = dict(CONFIG_PADRAO)
        self._cache = {}
        self._regras = None
        self.mudou()
        if caminho:
            self.carregar()

    # ---- arquivo
    def carregar(self):
        try:
            d = ler_dados(self.caminho)
        except (OSError, ValueError):
            return
        self.materiais = [str(m) for m in d.get("materiais", []) if str(m).strip()]
        self.de_para = {str(k): str(v) for k, v in d.get("de_para", {}).items()}
        self.extras = [{"principal": str(r["principal"]),
                        "itens": [[str(n), int(q)] for n, q in r.get("itens", [])]}
                       for r in d.get("extras", []) if r.get("principal")]
        self.codigos = {str(k): str(v) for k, v in d.get("codigos", {}).items()}
        self.apelidos = {str(k): [str(x) for x in v] for k, v in d.get("apelidos", {}).items()}
        self.escolhas = {str(k): str(v) for k, v in d.get("escolhas", {}).items()}
        self.config = dict(CONFIG_PADRAO, **d.get("config", {}))
        self.mudou()

    def salvar(self):
        self.mudou()
        if not self.caminho:
            return
        dados = {"materiais": self.materiais, "codigos": self.codigos, "de_para": self.de_para,
                 "extras": self.extras, "apelidos": self.apelidos, "escolhas": self.escolhas,
                 "config": self.config}
        salvar_json(self.caminho, dados)
        self._lido_em = self._data_arquivo()

    def _data_arquivo(self):
        try:
            return versao_dados(self.caminho) if self.caminho else None
        except OSError:
            return None

    def recarregar_se_mudou(self):
        """Relê o arquivo se outra pessoa o alterou (pasta compartilhada)."""
        d = self._data_arquivo()
        if d is not None and d != getattr(self, "_lido_em", None):
            self.carregar()
            return True
        return False

    def mudou(self):
        self._lido_em = self._data_arquivo()
        self._cache.clear()
        self._regras = None
        self._chaves_cad = {chave_nome(m) for m in self.materiais}
        self._nome_por_codigo = {c: n for n in self.materiais for c in [self.codigos.get(chave_nome(n), "")] if c}

    # ---- nomes
    def definir_materiais(self, itens, substituir=True):
        """itens: [(código, nome)] ou [nome]."""
        self.recarregar_se_mudou()
        base = [] if substituir else list(self.materiais)
        codigos = {} if substituir else dict(self.codigos)
        vistos = {chave_nome(m) for m in base}
        for it in itens:
            cod, n = (it if isinstance(it, (tuple, list)) else ("", it))
            k = chave_nome(n)
            if not k:
                continue
            if k not in vistos:
                vistos.add(k)
                base.append(n)
            if cod:
                codigos[k] = normaliza_codigo(cod)
        self.materiais = base
        self.codigos = codigos
        self.salvar()

    def adicionar_material(self, codigo, nome):
        self.recarregar_se_mudou()
        k = chave_nome(nome)
        if not k:
            raise ValueError("Informe o nome do material.")
        if any(chave_nome(m) == k for m in self.materiais):
            raise ValueError(f"Já existe um material com o nome \"{nome}\".")
        self.materiais.append(nome)
        if codigo:
            self.codigos[k] = normaliza_codigo(codigo)
        self.salvar()

    def editar_material(self, nome_antigo, codigo, nome):
        """Troca o código e/ou o nome; os nomes do projeto ligados a ele continuam ligados."""
        self.recarregar_se_mudou()
        ka, k = chave_nome(nome_antigo), chave_nome(nome)
        if not k:
            raise ValueError("Informe o nome do material.")
        i = next((i for i, m in enumerate(self.materiais) if chave_nome(m) == ka), None)
        if i is None:
            raise ValueError("Esse material não está mais no cadastro (outra pessoa pode ter mudado).")
        if k != ka and any(chave_nome(m) == k for m in self.materiais):
            raise ValueError(f"Já existe um material com o nome \"{nome}\".")
        self.materiais[i] = nome
        self.codigos.pop(ka, None)
        if codigo:
            self.codigos[k] = normaliza_codigo(codigo)
        for p, v in list(self.de_para.items()):
            if chave_nome(v) == ka:
                self.de_para[p] = nome
        self.salvar()

    def excluir_material(self, nome):
        self.recarregar_se_mudou()
        k = chave_nome(nome)
        self.materiais = [m for m in self.materiais if chave_nome(m) != k]
        self.codigos.pop(k, None)
        self.de_para = {p: v for p, v in self.de_para.items() if chave_nome(v) != k}
        self.salvar()

    def codigo_de(self, nome):
        """Código do material (nome do cadastro ou do projeto já resolvido)."""
        return self.codigos.get(chave_nome(nome), "")

    def nome_do_codigo(self, codigo):
        return self._nome_por_codigo.get(normaliza_codigo(codigo), "")

    def resolver(self, nome):
        """-> (nome final, como achou, nota). como: manual | igual | parecido | nao | ''"""
        k = chave_nome(nome)
        if k in self._cache:
            return self._cache[k]
        if k in self.de_para:
            r = (self.de_para[k], "manual", 1.0)
        elif not self.materiais or not k:
            r = (nome, "", 0.0)
        else:
            nota, _, m = max((semelhanca(nome, m), -len(m), m) for m in self.materiais)
            if nota >= 1.0:
                r = (m, "igual", 1.0)
            elif nota >= self.LIMITE:
                r = (m, "parecido", nota)
            else:
                r = (nome, "nao", nota)
        self._cache[k] = r
        return r

    def nome_real(self, nome):
        return self.resolver(nome)[0]

    def cadastrado(self, nome):
        return chave_nome(nome) in self._chaves_cad

    def candidatos(self, nome, n=8):
        """Nomes do cadastro mais parecidos (para a escolha manual)."""
        notas = sorted(((semelhanca(nome, m), m) for m in self.materiais), reverse=True)
        return [m for s, m in notas[:n] if s > 0.3]

    def ajustar(self, nome_projeto, nome_cadastro):
        self.recarregar_se_mudou()
        k = chave_nome(nome_projeto)
        if nome_cadastro is None:
            self.de_para.pop(k, None)
        else:
            self.de_para[k] = nome_cadastro
        self.salvar()

    # ---- materiais extras
    def extras_de(self, nome):
        """[(nome, qtd)] que obrigatoriamente vêm com o material `nome`."""
        if self._regras is None:
            self._regras = {}
            for r in self.extras:
                k = chave_nome(self.nome_real(r["principal"]))
                self._regras.setdefault(k, []).extend((n, q) for n, q in r["itens"])
        return self._regras.get(chave_nome(nome), [])


CADASTRO = Cadastro(ARQ_CADASTRO)
