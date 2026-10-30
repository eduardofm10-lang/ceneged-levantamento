# Ceneged · Levantamento de Materiais

Programa de computador (Windows) que lê projetos elétricos em PDF, acha os **balões**,
**cabos** e **cercas** do desenho e monta o **relatório de materiais** no padrão NEO,
usando as estruturas e tabelas dos normativos Neoenergia (DIS-NOR-013/014/016/018 e
DIS-ETE-011).

> **Repositório privado.** Os PDFs são projetos de cliente e o `ceneged.db` tem dados da
> empresa. Nenhum dos dois vai para o GitHub (veja o `.gitignore`).

## Como rodar (desenvolvimento)

```bat
python -m pip install -r requirements.txt
python iniciar.py
```

Para não mexer nos dados de verdade enquanto testa, aponte para uma pasta de teste:

```bat
set CENEGED_DADOS=C:\teste\dados
python iniciar.py
```

## Como gerar o instalador para os colaboradores

Dê dois cliques em `instalador\GERAR_INSTALADOR.bat`. O passo a passo completo
(senha do banco, versão, atualização automática) está em
[`instalador/COMECE_AQUI.txt`](instalador/COMECE_AQUI.txt) e
[`instalador/LEIA-ME.txt`](instalador/LEIA-ME.txt).

## Organização do código (camadas)

```
iniciar.py              abre o programa
ceneged/
  interface/            telas (Tkinter)                         ↓ só usa as de baixo
  servicos/             casos de uso: ler um PDF, exportar, carregar normativos
  dominio/              regras: balões, normativos, postes, conectores, cerca, relatório
  dados/                MongoDB (nuvem), planilhas, usuários, composições
  leitura_pdf/          visão computacional: balões, textos, rede de cabos
  comum/                funções pequenas de texto/número
testes/                 testes automáticos e regressão com PDFs (PDFs ficam fora do Git)
instalador/             GERAR_INSTALADOR.bat, instalador.iss, ícone, LEIA-ME
docs/                   como funciona, arquitetura, como mudar, como publicar no GitHub
```

Cada camada só importa as camadas **de baixo** — o teste `testes/test_camadas.py` confere isso.
Detalhes em [`docs/ARQUITETURA.md`](docs/ARQUITETURA.md); onde mexer para cada tipo de
mudança em [`docs/COMO_MUDAR.md`](docs/COMO_MUDAR.md).

## Testes

```bat
python -m unittest discover -s testes -v      :: regras (rápido, sem PDF)
python testes\regressao.py --gravar            :: antes de mudar: grava a "foto" dos PDFs de testes\pdfs
python testes\regressao.py                     :: depois de mudar: mostra o que mudou
```

## Dados

| O quê | Onde fica |
|---|---|
| Usuários, cadastro, composições, equipes, carteira, normativos | **MongoDB Atlas** quando existe `banco_mongo.txt` junto do programa (recomendado); senão `dados\*.json` no **modo OneDrive**, ou `ceneged.db` (SQLite) numa pasta de rede |
| Tabelas para consultar (Atlas, Power BI, Excel) | banco `ceneged_tabelas`: uma linha por registro, colunas em português; mapa em [`docs/Mapa_das_Tabelas.png`](docs/Mapa_das_Tabelas.png) |
| Senha do banco | `instalador\banco_mongo.txt` (fora do Git; modelo em `instalador\banco_mongo.exemplo.txt`) |
| Atualização automática | o `GERAR_INSTALADOR.bat` publica o instalador no próprio banco (coleção `instalador`); o programa baixa e instala ao abrir |
| Cópia de segurança | `Documentos\Ceneged Levantamento - Backup\AAAA-MM-DD.zip` de quem é administrador (1 por dia) |
| Planilha dos normativos | carregada pela tela *Materiais extras → Carregar planilha dos normativos* |
