# Como o programa funciona

(Texto que ficava no topo do antigo `encontrar_baloes.py`.)

```text
Levantamento de materiais a partir dos balões de projetos elétricos em PDF.

Uso na tela:
  - "Adicionar PDFs": até 15 arquivos. Cada um é delimitado e lido sozinho.
  - Contorno vermelho = área do projeto (automática). Se não estiver boa:
    "Desenhar retângulo" ou "Desenhar polígono" (clique nos pontos, duplo
    clique fecha). "Automática" volta ao contorno original.
  - Direita, em cima: balões encontrados. Embaixo: como vai sair no relatório.
    Clicar num material destaca, no desenho, os balões de onde ele veio.
  - "Exportar relatório": escolhe os arquivos; sai Arquivo | Material | Quantidade.
    Itens separados por vírgula são materiais diferentes; materiais com
    metros (ex.: PB120 40M + PB120 30M) são somados (PB120 = 70 M).

Menu lateral (botão ☰ no canto de cima):
  - Página inicial: a tela dos balões e da prévia do relatório.
  - Cadastro de materiais: carrega uma planilha (.xlsx ou .csv) com o título
    "Materiais" na célula A1 e os nomes abaixo, um por linha. Cada nome do
    projeto é procurado no cadastro e o relatório sai com o nome do cadastro
    (os números têm que bater: PB35 nunca vira PB70). Dá para corrigir à mão
    qualquer nome (dois cliques na lista); a correção fica guardada.
  - Materiais extras: regra "material principal -> materiais que vêm junto
    (com quantidade)". Se o principal aparece num balão, os que faltam são
    acrescentados nesse balão; os que já vieram não são repetidos.
  - Usuários (só administrador): cria o login e a senha de quem pode usar.
  - Trocar minha senha / Sair.

Login: na primeira vez o programa pede para criar o administrador. Usuários,
cadastro e regras ficam em "ceneged_usuarios.json" e "ceneged_cadastro.json",
na pasta do programa (ou na pasta escrita em "pasta_dados.txt", ao lado dele).
Com o programa numa pasta compartilhada, todos usam os mesmos dados.
Para gerar o .exe: GERAR_EXE.bat (veja LEIA-ME.txt).

Dois tipos de projeto (escolha automática, ou em "Tipo de projeto"):
  A) Balões com vírgula: cada balão lista materiais separados por vírgula;
     metros (ex.: 40M) dentro do balão, no balão de baixo ou ao lado.
  B) Caixas empilhadas + cabos pelo caminho: cada caixa da pilha é um
     material (1 unidade); os cabos ficam em balões com chamada até a linha
     tracejada, e os metros estão escritos ao longo do caminho (vão a vão).
     O programa refaz a rede tracejada, liga cada balão de cabo à sua linha,
     e soma cada comprimento no cabo daquela linha. Quando há duas linhas
     paralelas no mesmo vão (ex.: MT e BT no mesmo poste), o comprimento vale
     para as duas, cada uma com o seu cabo. Na tela, cada cabo tem uma cor e
     o comprimento lido aparece em cima do vão ("?" = sem cabo identificado).
     Os textos desse tipo de projeto são desenhados com a fonte de traço do
     CAD (não são texto do PDF); o programa tem um leitor próprio para ela.

Como os balões são achados (independente de tamanho, espessura ou cor):
  1. A área do projeto é achada sozinha: moldura, carimbo, legendas e tabelas
     (feitos quase só de retas em pé/deitadas) ficam de fora.
  2. O texto é lido direto do PDF (sem OCR, sai exato) e, numa cópia da página,
     todos os textos são removidos. Essa cópia "só desenho" é renderizada em
     alta resolução e todo traço de qualquer cor/espessura vira "tinta".
  3. Cada região de papel totalmente cercada por tinta é uma "região fechada".
     Um balão é exatamente isso: uma região fechada com texto dentro.
  4. Filtros simples separam balões de outras regiões fechadas (quarteirões,
     bolsões entre linhas): o balão é justo ao texto, tem forma de retângulo
     ou oval e não tem nada dentro além do texto.
  5. Se uma rua/linha passar por cima de um balão e cortá-lo em dois, as
     partes são reunidas porque as letras da mesma palavra ficaram separadas.
  6. Balões empilhados (colados, separados só por uma linha) são o mesmo
     material: o de cima é o principal e o de baixo vem entre parênteses.
  7. Comprimentos fora do balão ("45m") são ligados ao balão mais próximo.
     Regra: até 4 números terminados em M. Se forem texto do PDF são lidos
     direto; se forem desenho (linhas), um leitor próprio reconhece os dígitos.
```
