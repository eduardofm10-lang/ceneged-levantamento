"""Onde ficam o programa e os dados (pasta_dados.txt).

Parte do programa Levantamento de Materiais (Ceneged)."""

import os
import re
import sys

def pasta_programa():
    """Pasta do programa (.exe ou .py); no Jupyter, a pasta do notebook."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    try:
        # ceneged/dados/caminhos.py -> raiz do repositório (onde fica iniciar.py)
        return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    except NameError:
        return os.getcwd()


def _limpar_caminho(p):
    """Caminho do pasta_dados.txt pronto para usar. Conserta o caso em que o instalador gravou
    'C:\\pasta do instalador\\%OneDriveCommercial%\\Levantamento' (juntou duas pastas)."""
    p = (p or "").strip().strip('"')
    i = p.find("%")
    if i > 0:                                   # algo antes do %VARIAVEL%: descarta
        p = p[i:]
    p = os.path.expandvars(os.path.expanduser(p))
    # duas unidades no mesmo caminho (C:\...\C:\...): vale a última
    m = [x.start() for x in re.finditer(r"[A-Za-z]:[\\/]", p)]
    if m and m[-1] > 0:
        p = p[m[-1]:]
    return p


def pasta_dados():
    """Onde ficam usuários, cadastro e regras: a pasta do programa, ou a pasta
    escrita no arquivo "pasta_dados.txt" (ao lado do programa), se existir."""
    p_env = os.environ.get("CENEGED_DADOS", "").strip()
    if p_env:                   # testes / desenvolvimento: não mexe nos dados de verdade
        os.makedirs(p_env, exist_ok=True)
        return p_env
    base = pasta_programa()
    try:
        with open(os.path.join(base, "pasta_dados.txt"), encoding="utf-8-sig") as f:
            p = f.read().strip().strip('"')
        # %OneDriveCommercial%\Levantamento: o OneDrive de cada pessoa fica num caminho diferente
        p = _limpar_caminho(p)
    except (OSError, ValueError):
        p = ""
    if not p:
        return base
    if not tem_dados(p) and not modo_mongo():
        # o colaborador recebeu a pasta pelo OneDrive num caminho diferente do escrito no
        # instalador (ex.: OneDrive\Levantamento em vez de OneDrive\Qualidade\Levantamento):
        # procura a pasta com os dados no OneDrive dele e passa a usar essa
        achada = procurar_pasta_dados(os.path.basename(p.rstrip("\\/")))
        if achada:
            if os.path.normcase(os.path.abspath(achada)) != os.path.normcase(os.path.abspath(p)):
                try:
                    with open(os.path.join(base, "pasta_dados.txt"), "w", encoding="utf-8") as f:
                        f.write(achada)
                except OSError:
                    pass
            return achada
    # não cria a pasta: no OneDrive isso faria uma pasta vazia (e um cadastro novo, zerado);
    # se ela não existir, a tela de login avisa e mostra como resolver
    return p


def tem_dados(p):
    """A pasta já tem os dados do programa (modo OneDrive, banco ou arquivos antigos)?"""
    return any(os.path.isfile(os.path.join(p, *c)) for c in
               (("dados", "usuarios.json"), ("ceneged.db",), ("ceneged_usuarios.json",)))


_PASTA_ACHADA = {}


def procurar_pasta_dados(nome_preferido="Levantamento", forcar=False):
    """Procura no OneDrive deste computador a pasta com os dados do programa (até 4 níveis).
    Só lista pastas (não baixa nada da nuvem). Preferência: o mesmo nome da pasta configurada
    e, depois, os dados mais recentes."""
    chave = (nome_preferido or "").lower()
    if chave in _PASTA_ACHADA and not forcar:
        return _PASTA_ACHADA[chave]
    raizes = []
    for v in ("OneDriveCommercial", "OneDrive", "OneDriveConsumer"):
        r = os.environ.get(v, "")
        if r and os.path.isdir(r) and r not in raizes:
            raizes.append(r)
    casa = os.path.expanduser("~")
    try:
        for n in os.listdir(casa):
            r = os.path.join(casa, n)
            if n.lower().startswith("onedrive") and os.path.isdir(r) and r not in raizes:
                raizes.append(r)
    except OSError:
        pass
    achados, vistos = [], 0
    for raiz in raizes:
        fila = [(raiz, 0)]
        while fila and vistos < 6000:
            pasta, nivel = fila.pop(0)
            vistos += 1
            if pasta != raiz and tem_dados(pasta):
                achados.append(pasta)
                continue                        # não desce dentro da pasta de dados
            if nivel >= 4:
                continue
            try:
                with os.scandir(pasta) as it:
                    for e in it:
                        if e.name.startswith((".", "_", "~")) or e.name.lower() in ("dados", "atualizacao"):
                            continue
                        try:
                            if e.is_dir(follow_symlinks=False):
                                fila.append((e.path, nivel + 1))
                        except OSError:
                            pass
            except OSError:
                pass

    def nota(p):
        try:
            t = max(os.path.getmtime(os.path.join(p, *c)) for c in
                    (("dados", "usuarios.json"), ("ceneged.db",), ("ceneged_usuarios.json",))
                    if os.path.isfile(os.path.join(p, *c)))
        except (OSError, ValueError):
            t = 0
        return (os.path.basename(p).lower() == chave, os.path.isfile(os.path.join(p, "dados", "usuarios.json")), t)
    achada = max(achados, key=nota) if achados else None
    _PASTA_ACHADA[chave] = achada
    return achada


def fixar_pasta_no_computador(pasta=None):
    """OneDrive: marca a pasta dos dados como "Sempre manter neste dispositivo" (attrib +P),
    para os arquivos ficarem no computador e não só na nuvem. Roda escondido, sem esperar."""
    if os.name != "nt":
        return
    pasta = pasta or pasta_dados()
    if not os.path.isdir(pasta):
        return
    try:
        import subprocess
        sem_janela = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        for args in (["attrib", "+P", "-U", pasta],
                     ["attrib", "+P", "-U", os.path.join(pasta, "*"), "/S", "/D"]):
            subprocess.Popen(args, creationflags=sem_janela, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
    except Exception:
        pass


def reiniciar_programa(root):
    """Fecha e abre o programa de novo (para usar a pasta de dados que acabou de ser achada)."""
    try:
        import subprocess
        if getattr(sys, "frozen", False):
            subprocess.Popen([sys.executable])
        else:
            subprocess.Popen([sys.executable, os.path.abspath(sys.argv[0])])
    finally:
        root.destroy()


def pasta_acessivel(pasta):
    """A pasta compartilhada está ao alcance e aceita gravação?"""
    if not os.path.isdir(pasta):
        return False
    teste = os.path.join(pasta, f".teste_{os.getpid()}")
    try:
        with open(teste, "w") as f:
            f.write("ok")
        os.remove(teste)
        return True
    except OSError:
        return False

_MODO_OD = None


def modo_onedrive():
    """Pasta de dados dentro do OneDrive/SharePoint (ou com o arquivo MODO_ONEDRIVE.txt)."""
    global _MODO_OD
    if _MODO_OD is None and modo_mongo():
        _MODO_OD = False             # com banco MongoDB a pasta do OneDrive só guarda o instalador
    if _MODO_OD is None:
        p = pasta_dados()
        baixo = p.lower()
        raizes = [os.environ.get(v, "") for v in ("OneDrive", "OneDriveCommercial", "OneDriveConsumer")]
        dentro = any(r and os.path.normcase(os.path.abspath(p)).startswith(os.path.normcase(os.path.abspath(r)))
                     for r in raizes)
        _MODO_OD = (("onedrive" in baixo or "sharepoint" in baixo or dentro) and
                    not os.path.exists(os.path.join(p, "MODO_BANCO.txt"))) or \
            os.path.exists(os.path.join(p, "MODO_ONEDRIVE.txt"))
    return _MODO_OD


_MONGO = {"uri": None, "cli": None, "db": None, "erro": "", "off_ate": 0.0}


def config_mongo():
    """Endereço do banco: variável CENEGED_MONGO ou arquivo banco_mongo.txt na pasta do programa
    (vai junto no instalador). Linhas começando com # são ignoradas."""
    if _MONGO["uri"] is None:
        uri = os.environ.get("CENEGED_MONGO", "").strip()
        if not uri:
            for pasta in (pasta_programa(),):
                try:
                    with open(os.path.join(pasta, "banco_mongo.txt"), encoding="utf-8-sig") as f:
                        for linha in f:
                            linha = linha.strip()
                            if linha.startswith(("mongodb://", "mongodb+srv://", "mongomock://")):
                                uri = linha
                                break
                except OSError:
                    continue
                if uri:
                    break
        _MONGO["uri"] = uri
    return _MONGO["uri"]


def modo_mongo():
    return bool(config_mongo())


def descricao_banco():
    """Texto curto para o rodapé: 'MongoDB · cluster0.xxxxx.mongodb.net'."""
    m = re.search(r"@([^/?]+)", config_mongo() or "")
    return "MongoDB · " + (m.group(1) if m else "local")
