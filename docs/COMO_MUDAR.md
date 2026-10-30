# Onde mexer para cada tipo de mudança

| Quero mudar… | Arquivo | Onde |
|---|---|---|
| Valores padrão (região, conector da rede nua, nº de conectores FLBIT…) | `ceneged/dados/armazenamento.py` | `CONFIG_PADRAO` |
| Como um balão é achado no desenho | `ceneged/leitura_pdf/deteccao.py` | `detectar_baloes` |
| A área do projeto (tirar carimbo/legenda) | `ceneged/leitura_pdf/delimitacao.py` | `delimitar_automatico` |
| Rede de cabos, metros por vão, FLBIT/FLABIT no meio ou no fim | `ceneged/leitura_pdf/rede.py` | `RE_FIM_DE_REDE`, `distribuir_comprimentos` |
| Como o texto do balão vira materiais ("2x", vírgulas, metros) | `ceneged/dominio/baloes.py` | `materiais_do_balao`, `multiplicador` |
| Montagem da estrutura pelo normativo | `ceneged/dominio/normativo.py` | `_montar_do_normativo`, `estrutura_do_normativo` |
| Escolha da linha nas tabelas (bitola, cabo, poste, faixa…) | `ceneged/dominio/normativo.py` | `escolher_na_tabela`, `EXPLICA_ESCOLHA`, `uso_da_linha` |
| Postes: tipo DT/circular, diâmetro, altura de aplicação | `ceneged/dominio/postes.py` | `tipo_do_poste`, `geometria_do_poste`, `altura_de_aplicacao`, `linha_pelo_poste` |
| Conectores perfurantes (FLBIT, IT-R, ITF-R) | `ceneged/dominio/relatorio.py` | `materiais_resolvidos`, `conectores_da_composicao` |
| Soma e agrupamento do relatório | `ceneged/dominio/relatorio.py` | `montar_relatorio` |
| Cerca (aterramento, seccionamento) | `ceneged/dominio/cerca.py` | `kit_cerca` e vizinhas |
| Excel exportado (abas NEO, Conferência, TOTAL) | `ceneged/servicos/exportar.py` | `salvar_relatorio_neo`, `salvar_relatorio_todos` |
| Leitura da planilha dos normativos | `ceneged/dados/normativos.py` | `ler_planilha_normativos` |
| Atualizar as composições pelo normativo | `ceneged/servicos/normativos.py` | `atualizar_composicoes_do_normativo` |
| Modelos de planilha para baixar | `ceneged/dados/planilhas_normativos.py` | `salvar_modelo_normativos`, `salvar_modelo_composicoes` |
| Banco MongoDB (gravação, conexão, cópia do dia, atualização) | `ceneged/dados/mongo.py` | `mongo_salvar`, `mongo_ler_dados`, `mongo_copia_do_dia`, `mongo_baixar_instalador` |
| Publicar a versão nova no banco | `instalador/publicar_atualizacao.py` | `publicar` |
| PDF com os balões corrigidos (tela e exportação) | `ceneged/servicos/pdf_corrigido.py` | `layout_balao_corrigido`, `salvar_pdf_corrigido`, `imagem_pagina_corrigida` |
| Balão de dica ao passar o mouse | `ceneged/interface/tema.py` | `dica_na_tabela` |
| Cor dos materiais do balão selecionado | `ceneged/interface/app.py` | `destacar_materiais_do_balao` |
| Tela de materiais extras / tabelas dos normativos | `ceneged/interface/tela_extras.py`, `interface/tabelas_norma.py` | `TelaExtras`, `JanelaTabelasNorma` |
| Versão do programa | `instalador/GERAR_INSTALADOR.bat` | linha `set VERSAO=` |

## Fluxo para fazer uma mudança

1. **Crie um ramo** (branch) com o nome da mudança, ex.: `ajuste-conector-flbit`.
2. Antes de mexer, grave a foto dos PDFs: `python testes\regressao.py --gravar`.
3. Faça a mudança no arquivo da tabela acima.
4. Rode os testes:
   ```bat
   python -m unittest discover -s testes -v
   python testes\regressao.py
   ```
   A regressão mostra o que mudou em cada projeto. Confira se mudou **só** o que você queria.
5. Teste na tela: `python iniciar.py` (com `set CENEGED_DADOS=C:\teste\dados` para não
   mexer nos dados reais).
6. Faça o *commit* com uma frase clara ("FLBIT no fim de rede: só conectores do IT-R") e
   abra um *Pull Request* para outra pessoa revisar.
7. Depois de aprovado: aumente `set VERSAO=` no `GERAR_INSTALADOR.bat` e gere o instalador.
   Os colaboradores recebem o aviso de atualização ao abrir o programa.

## Regras do projeto

* Telas (`interface/`) não decidem regra de negócio: elas chamam `dominio/` ou `servicos/`.
* `dominio/`, `leitura_pdf/`, `dados/` e `servicos/` não usam Tkinter (hoje já é assim). Avisos ao usuário saem pela interface.
* Nada de PDF de cliente, `ceneged.db` ou planilha com dados da empresa no Git.
