# Como publicar no GitHub (passo a passo)

O jeito mais simples, sem digitar comando, é o **GitHub Desktop**.

> **Sempre PRIVADO.** O código tem as regras da empresa. Os PDFs dos clientes e o
> `ceneged.db` já estão bloqueados pelo `.gitignore` e não sobem. Mesmo assim, nunca arraste PDF,
> banco ou planilha da empresa para o repositório.

## 1. Criar a conta e a organização (uma vez)

1. Entre em **github.com** → **Sign up** e crie a conta com o e-mail da empresa.
2. (Recomendado) Crie uma **organização** gratuita para o código ser da empresa, não de uma pessoa:
   foto do perfil (canto de cima) → **Your organizations** → **New organization** → plano
   **Free** → nome, ex.: `ceneged`.

## 2. Instalar o GitHub Desktop

1. Baixe em **desktop.github.com** e instale.
2. Abra o programa → **Sign in to GitHub.com** → autorize no navegador.
3. Na tela "Configure Git", deixe o seu nome e e-mail → **Finish**.

## 3. Colocar o repositório no computador

1. Extraia o `CenegedLevantamento_GitHub.zip` em `C:\CenegedLevantamento`
   (botão direito → **Extrair tudo...**).
   Dentro dele tem uma pasta oculta `.git`: é ela que guarda o histórico. Não apague.
2. No GitHub Desktop: **File → Add local repository...** → **Choose...** →
   escolha `C:\CenegedLevantamento` → **Add repository**.

## 4. Publicar

1. Clique em **Publish repository** (botão azul em cima).
2. Preencha:
   * **Name:** `ceneged-levantamento`
   * **Description:** Levantamento de materiais dos projetos em PDF
   * ✅ **Keep this code private** (deixe MARCADO)
   * **Organization:** `ceneged` (se criou no passo 1)
3. **Publish repository**. Pronto: o código está em
   `github.com/ceneged/ceneged-levantamento`, visível só para quem você convidar.

## 5. Convidar o pessoal de TI

* Repositório pessoal: no site, abra o repositório → **Settings** → **Collaborators** →
  **Add people** → e-mail ou usuário do GitHub da pessoa.
* Organização: **Settings** do repositório → **Collaborators and teams** → **Add people**.
  Papel sugerido: **Write** para quem programa; **Admin** só para o responsável.

A pessoa recebe um e-mail, aceita e já consegue baixar (**Code → Open with GitHub Desktop**).

## 6. Dia a dia

| Situação | No GitHub Desktop |
|---|---|
| Mudei arquivos e quero salvar no GitHub | à esquerda aparecem as mudanças → escreva um resumo embaixo (ex.: "Conector FLBIT no fim de rede") → **Commit to main** → **Push origin** |
| Alguém mudou e eu quero a versão nova | **Fetch origin** → **Pull origin** |
| Mudança grande, quero revisão antes | **Current branch → New branch** → trabalhe nela → **Publish branch** → **Create Pull Request** |
| Ver o que mudou e quando | aba **History** |
| Voltar uma mudança | **History** → botão direito no commit → **Revert changes in commit** |

Os testes automáticos rodam sozinhos a cada envio: no site, aba **Actions**
(✔ verde = passou; ✖ vermelho = algo quebrou, clique para ver).

## 7. Gerar o instalador a partir do GitHub

1. GitHub Desktop: **Pull origin** (pega a versão mais nova).
2. Aumente a versão em `instalador\GERAR_INSTALADOR.bat` (linha `set VERSAO=`), faça commit.
3. Dois cliques em `instalador\GERAR_INSTALADOR.bat`.
4. Os colaboradores recebem o aviso de atualização ao abrir o programa.

## Alternativa sem instalar nada (só pelo site)

1. **github.com/new** → nome `ceneged-levantamento` → marque **Private** → **Create repository**.
2. Clique em **uploading an existing file**.
3. Abra a pasta extraída, selecione **tudo o que está dentro dela** e arraste para a página.
4. Escreva um resumo → **Commit changes**.

Funciona, mas confira antes de arrastar que não tem PDF, `ceneged.db` ou planilha da empresa
no meio: pelo site você controla na mão o que sobe. Pastas que começam com ponto (`.git`,
`.github`) podem não ir pelo arrastar e o histórico começa do zero. Por isso o GitHub Desktop é
o caminho recomendado.
