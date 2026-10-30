"""Equipes, carteira de obras e memória de projetos.

Parte do programa Levantamento de Materiais (Ceneged)."""

import json
import os
import re
import time

from ceneged.comum.texto import chave_nome
from ceneged.dados.caminhos import pasta_dados
from ceneged.dados.armazenamento import (ler_dados, salvar_json, versao_dados)

# ---------------------------------------------------------------------------
#  Cadastro de equipe (pessoas e equipes) e Carteira de obra
#  (arquivos .json na pasta de dados: iguais para todos)
# ---------------------------------------------------------------------------
ARQ_EQUIPES = os.path.join(pasta_dados(), "ceneged_equipes.json")
ARQ_CARTEIRA = os.path.join(pasta_dados(), "ceneged_carteira.json")
FUNCOES = ("Supervisor", "Encarregado", "Colaborador")
OPC_SNP = ("SIM", "NÃO", "PARCIAL")
OPC_SN = ("SIM", "NÃO")
STATUS_OBRA = ("EM ANDAMENTO", "CONCLUÍDA", "REPROGRAMADA", "NÃO EXECUTADA", "ESTRATÉGICA")
CAMPOS_OBRA = [  # chave, título na tabela/planilha, largura
    ("projeto", "PROJETO", 80), ("nota", "NOTA", 95), ("supervisor", "SUPERVISOR", 110),
    ("encarregado", "ENCARREGADO", 110), ("viabilizada", "VIABILIZADA?", 90), ("requisicao", "REQUISIÇÃO", 90),
    ("equipe", "EQUIPE", 80), ("inicio", "DATA INÍCIO", 90), ("fim", "DATA FIM", 90),
    ("desligamento", "DESLIGAMENTO", 100), ("data_desl", "DATA DO DESLIGAMENTO", 170),
    ("conclusao", "DATA CONC", 90), ("status", "STATUS DA OBRA", 120), ("obs", "OBSERVAÇÕES", 260)]
CORES_STATUS = {"REPROGRAMADA": ("#FDE3D3", "#C2410C"), "EM ANDAMENTO": ("#DCEBFA", "#1D4ED8"),
                "CONCLUÍDA": ("#DFF1E3", "#15803D"), "NÃO EXECUTADA": ("#F9D6D6", "#B91C1C"),
                "ESTRATÉGICA": ("#E4E1F7", "#4338CA")}


def data_br(txt):
    """'1/10/26', '01102026', '2026-10-01' -> '01/10/2026'. Vazio -> ''. Inválida -> ValueError."""
    if txt is None:
        return ""
    if hasattr(txt, "strftime"):
        return txt.strftime("%d/%m/%Y")
    t = str(txt).strip()
    if not t:
        return ""
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T].*)?", t)
    if m:
        a, mes, d = (int(x) for x in m.groups())
    else:
        m = re.fullmatch(r"(\d{1,2})[/.\-](\d{1,2})(?:[/.\-](\d{2,4}))?", t) or \
            re.fullmatch(r"(\d{2})(\d{2})(\d{4})?", t)
        if not m:
            raise ValueError(f"Data inválida: {t}  (use dd/mm/aaaa)")
        d, mes = int(m.group(1)), int(m.group(2))
        a = int(m.group(3)) if m.group(3) else time.localtime().tm_year
        if a < 100:
            a += 2000
    import datetime as _dt
    try:
        return _dt.date(a, mes, d).strftime("%d/%m/%Y")
    except ValueError:
        raise ValueError(f"Data inválida: {t}")


MESES = ("Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro",
         "Outubro", "Novembro", "Dezembro")


def nome_mes(ano, mes):
    return f"{MESES[mes - 1]}/{ano}"


def data_ordem(txt):
    """'05/10/2026' -> (2026, 10, 5) para ordenar; vazio vai para o fim."""
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", str(txt or ""))
    return (int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else (9999, 0, 0)


def _opcao(v, opcoes):
    """'nao' -> 'NÃO'; 'concluida' -> 'CONCLUÍDA'; desconhecido fica como veio (maiúsculas)."""
    t = str(v or "").strip()
    if not t:
        return ""
    k = chave_nome(t)
    for o in opcoes:
        if chave_nome(o) == k or chave_nome(o).startswith(k) or k.startswith(chave_nome(o)):
            return o
    return t.upper()


class ArquivoDados:
    """Um .json na pasta de dados, relido quando outra pessoa grava."""

    def __init__(self, caminho, padrao):
        self.caminho = caminho
        self.padrao = padrao
        self.dados = json.loads(json.dumps(padrao))
        self._lido_em = None
        self.carregar()

    def _data(self):
        try:
            return versao_dados(self.caminho) if self.caminho else None
        except OSError:
            return None

    def carregar(self):
        try:
            d = ler_dados(self.caminho)
            self.dados = {k: d.get(k, json.loads(json.dumps(v))) for k, v in self.padrao.items()}
        except (OSError, ValueError, TypeError, AttributeError):
            self.dados = json.loads(json.dumps(self.padrao))
        self._lido_em = self._data()

    def recarregar_se_mudou(self):
        d = self._data()
        if d is not None and d != self._lido_em:
            self.carregar()
            return True
        return False

    def salvar(self):
        if self.caminho:
            salvar_json(self.caminho, self.dados)
            self._lido_em = self._data()


class Equipes(ArquivoDados):
    def __init__(self, caminho):
        super().__init__(caminho, {"pessoas": [], "equipes": []})

    @property
    def pessoas(self):
        return self.dados["pessoas"]

    @property
    def equipes(self):
        return self.dados["equipes"]

    def nomes(self, funcao=None):
        return sorted((p["nome"] for p in self.pessoas if funcao is None or p.get("funcao") == funcao),
                      key=str.upper)

    def pessoa(self, nome):
        k = chave_nome(nome)
        return next((p for p in self.pessoas if chave_nome(p["nome"]) == k), None)

    def equipe(self, codigo):
        k = chave_nome(codigo)
        return next((e for e in self.equipes if chave_nome(e["codigo"]) == k), None)

    def codigos(self):
        return sorted((e["codigo"] for e in self.equipes), key=lambda c: (re.sub(r"\d", "", c), [int(x) for x in re.findall(r"\d+", c)]))

    def salvar_pessoa(self, nome_antigo, nome, funcao, matricula=""):
        self.recarregar_se_mudou()
        nome = re.sub(r"\s+", " ", nome).strip().upper()
        if not nome:
            raise ValueError("Informe o nome.")
        if funcao not in FUNCOES:
            raise ValueError("Escolha a função.")
        outro = self.pessoa(nome)
        if outro and (not nome_antigo or chave_nome(nome_antigo) != chave_nome(nome)):
            raise ValueError(f"{nome} já está cadastrado(a) como {outro['funcao']}.")
        if nome_antigo:
            p = self.pessoa(nome_antigo)
            if p is None:
                raise ValueError("Essa pessoa não está mais no cadastro (outra pessoa pode ter mudado).")
            ka = chave_nome(nome_antigo)
            p.update(nome=nome, funcao=funcao, matricula=matricula.strip())
            for e in self.equipes:                       # renomeia nas equipes
                if chave_nome(e.get("supervisor", "")) == ka:
                    e["supervisor"] = nome
                if chave_nome(e.get("encarregado", "")) == ka:
                    e["encarregado"] = nome
                e["colaboradores"] = [nome if chave_nome(c) == ka else c for c in e.get("colaboradores", [])]
        else:
            self.pessoas.append({"nome": nome, "funcao": funcao, "matricula": matricula.strip()})
        self.salvar()
        return nome

    def excluir_pessoa(self, nome):
        self.recarregar_se_mudou()
        k = chave_nome(nome)
        self.dados["pessoas"] = [p for p in self.pessoas if chave_nome(p["nome"]) != k]
        for e in self.equipes:
            if chave_nome(e.get("supervisor", "")) == k:
                e["supervisor"] = ""
            if chave_nome(e.get("encarregado", "")) == k:
                e["encarregado"] = ""
            e["colaboradores"] = [c for c in e.get("colaboradores", []) if chave_nome(c) != k]
        self.salvar()

    def equipes_da_pessoa(self, nome):
        k = chave_nome(nome)
        return [e["codigo"] for e in self.equipes
                if k in {chave_nome(x) for x in [e.get("supervisor", ""), e.get("encarregado", "")] +
                         e.get("colaboradores", [])}]

    def salvar_equipe(self, codigo_antigo, codigo, supervisor, encarregado, colaboradores):
        self.recarregar_se_mudou()
        codigo = re.sub(r"\s+", "", codigo).upper()
        if not codigo:
            raise ValueError("Informe o código da equipe.")
        outra = self.equipe(codigo)
        if outra and (not codigo_antigo or chave_nome(codigo_antigo) != chave_nome(codigo)):
            raise ValueError(f"A equipe {codigo} já existe.")
        e = {"codigo": codigo, "supervisor": supervisor, "encarregado": encarregado,
             "colaboradores": list(colaboradores)}
        if codigo_antigo:
            atual = self.equipe(codigo_antigo)
            if atual is None:
                raise ValueError("Essa equipe não está mais no cadastro (outra pessoa pode ter mudado).")
            atual.clear()
            atual.update(e)
        else:
            self.equipes.append(e)
        self.salvar()
        return codigo

    def excluir_equipe(self, codigo):
        self.recarregar_se_mudou()
        k = chave_nome(codigo)
        self.dados["equipes"] = [e for e in self.equipes if chave_nome(e["codigo"]) != k]
        self.salvar()


class Carteira(ArquivoDados):
    def __init__(self, caminho):
        super().__init__(caminho, {"obras": [], "proximo": 1})

    @property
    def obras(self):
        return self.dados["obras"]

    def obra(self, id_):
        return next((o for o in self.obras if o.get("id") == id_), None)

    def salvar_obra(self, dados, id_=None, usuario=""):
        """Grava um lançamento (novo se id_ é None). -> id."""
        self.recarregar_se_mudou()
        agora = time.strftime("%d/%m/%Y %H:%M")
        limpo = {k: str(dados.get(k, "") or "").strip() for k, _, _ in CAMPOS_OBRA}
        if id_ is None:
            id_ = int(self.dados.get("proximo", 1))
            while self.obra(id_):
                id_ += 1
            self.dados["proximo"] = id_ + 1
            limpo.update(id=id_, criado_por=usuario, criado_em=agora)
            self.obras.append(limpo)
        else:
            o = self.obra(id_)
            if o is None:
                raise ValueError("Esse lançamento não existe mais (outra pessoa pode ter excluído).")
            o.update(limpo)
            o.update(alterado_por=usuario, alterado_em=agora)
        self.salvar()
        return id_

    def excluir_obra(self, id_):
        self.recarregar_se_mudou()
        self.dados["obras"] = [o for o in self.obras if o.get("id") != id_]
        self.salvar()

    def duplicada(self, projeto, nota, menos_id=None):
        kp, kn = chave_nome(projeto), chave_nome(nota)
        return next((o for o in self.obras if o.get("id") != menos_id and chave_nome(o.get("projeto")) == kp
                     and kp and chave_nome(o.get("nota")) == kn), None)


EQUIPES = Equipes(ARQ_EQUIPES)
ARQ_PROJETOS = os.path.join(pasta_dados(), "ceneged_projetos.json")


class MemoriaProjetos(ArquivoDados):
    """Correções de balões e ajustes do relatório de cada PDF (voltam quando o PDF é aberto de novo)."""

    def __init__(self, caminho):
        super().__init__(caminho, {"projetos": {}})

    @staticmethod
    def chave(caminho):
        try:
            return f"{os.path.basename(caminho)}|{os.path.getsize(caminho)}"
        except OSError:
            return os.path.basename(caminho)

    def ler(self, caminho):
        self.recarregar_se_mudou()
        return self.dados["projetos"].get(self.chave(caminho), {})

    def gravar(self, arq):
        self.recarregar_se_mudou()
        aj = arq.ajustes
        d = {"ajustes": {"remover": [list(k) for k in aj["remover"]],
                         "qtd": [[k[0], k[1], q] for k, q in aj["qtd"].items()],
                         "add": aj["add"],
                         "trocar": [[k[0], k[1], v] for k, v in aj.get("trocar", {}).items()]},
             "paginas": {str(i): p.correcoes for i, p in arq._paginas.items()
                         if p.correcoes["excluir"] or p.correcoes["texto"] or p.correcoes["novos"]
                         or p.correcoes.get("rede") or p.correcoes.get("cerca")},
             "alterado": time.strftime("%d/%m/%Y %H:%M")}
        k = self.chave(arq.caminho)
        if not (aj["remover"] or aj["qtd"] or aj["add"] or aj.get("trocar") or d["paginas"]):
            self.dados["projetos"].pop(k, None)
        else:
            self.dados["projetos"][k] = json.loads(json.dumps(d, default=list))
        self.salvar()


PROJETOS = MemoriaProjetos(ARQ_PROJETOS)
CARTEIRA = Carteira(ARQ_CARTEIRA)
