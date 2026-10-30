@echo off
chcp 65001 >nul
title Gerando o instalador - Ceneged Levantamento de Materiais
cd /d "%~dp0"

rem ====================================================================
rem  Versao do programa: aumente a cada atualizacao (1.6, 1.7, 1.8...)
set VERSAO=1.6
rem ====================================================================

rem ---- confere se os arquivos estao nesta pasta
echo %~dp0 | find /i "\AppData\Local\Temp\" >nul
if not errorlevel 1 goto dentro_do_zip
rem este arquivo fica em instalador\ ; o codigo fica na pasta de cima
if not exist "..\iniciar.py" goto sem_codigo
if not exist "..\ceneged\__init__.py" goto sem_codigo
if not exist "instalador.iss" goto sem_iss
if not exist "ceneged.ico" goto sem_iss
if not exist "publicar_atualizacao.py" goto sem_iss
if not exist "banco_mongo.txt" goto sem_banco
findstr /c:"COLOQUE_A_SENHA" "banco_mongo.txt" >nul
if not errorlevel 1 goto sem_senha_banco

rem ---- monta tudo numa pasta curta, fora do OneDrive/Downloads (caminho longo passa de
rem      260 letras e o Windows/Inno da "O sistema nao pode encontrar o caminho")
set ORIGEM=%~dp0
set TRAB=%LOCALAPPDATA%\CenegedBuild
if not exist "%TRAB%" mkdir "%TRAB%"
if exist "%TRAB%\ceneged" rmdir /s /q "%TRAB%\ceneged"
mkdir "%TRAB%\instalador" >nul 2>nul
xcopy /e /i /y /q "%ORIGEM%..\ceneged" "%TRAB%\ceneged" >nul
copy /y "%ORIGEM%..\iniciar.py" "%TRAB%\" >nul
copy /y "%ORIGEM%instalador.iss" "%TRAB%\instalador\" >nul
copy /y "%ORIGEM%ceneged.ico" "%TRAB%\instalador\" >nul
cd /d "%TRAB%\instalador"
echo  Pasta de trabalho: %TRAB%
echo.

rem ---- Python
where py >nul 2>nul
if %errorlevel%==0 (set PY=py) else (set PY=python)
%PY% --version >nul 2>nul
if errorlevel 1 goto sem_python

echo  [1/5] Preparando o ambiente...
if not exist ".build\Scripts\python.exe" %PY% -m venv .build
if not exist ".build\Scripts\python.exe" goto erro_ambiente
".build\Scripts\python.exe" -m pip install --upgrade pip >nul

echo  [2/5] Instalando as bibliotecas (alguns minutos na primeira vez)...
".build\Scripts\python.exe" -m pip install pyinstaller pypdfium2 opencv-python-headless numpy pillow openpyxl pymongo
if errorlevel 1 goto erro_bibliotecas

echo  [3/5] Montando o programa...
rem roda na raiz (onde estao iniciar.py e a pasta ceneged); o resultado vai para instalador\dist
pushd ..
"instalador\.build\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onedir --windowed --name CenegedLevantamento --icon "%TRAB%\instalador\ceneged.ico" --paths . --collect-submodules ceneged --collect-all pypdfium2 --collect-all pypdfium2_raw --collect-submodules pymongo --collect-submodules bson --collect-submodules dns --distpath instalador\dist --workpath instalador\build iniciar.py
set ERRO_PYI=%errorlevel%
del /q CenegedLevantamento.spec >nul 2>nul
popd
if not "%ERRO_PYI%"=="0" goto erro_programa
rem o endereco do banco (com a senha) vai junto do programa instalado
copy /y "%ORIGEM%banco_mongo.txt" "dist\CenegedLevantamento\banco_mongo.txt" >nul

echo  [4/5] Criando o instalador...
set ISCC=
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe
if exist "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe" set ISCC=%LocalAppData%\Programs\Inno Setup 6\ISCC.exe
if not "%ISCC%"=="" goto tem_inno
echo  Inno Setup nao encontrado. Tentando instalar...
winget install --id JRSoftware.InnoSetup -e --silent --accept-source-agreements --accept-package-agreements
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe
if exist "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe" set ISCC=%LocalAppData%\Programs\Inno Setup 6\ISCC.exe
if "%ISCC%"=="" goto sem_inno

:tem_inno
rem o antivirus as vezes trava o instalador enquanto ele e gravado (erro 110):
rem grava fora da pasta Downloads e tenta ate 3 vezes
set SAIDA=%USERPROFILE%\CenegedInstalador
if not exist "%SAIDA%" mkdir "%SAIDA%"
set TENTATIVA=0
:compilar
set /a TENTATIVA+=1
del /q "%SAIDA%\Instalar_CenegedLevantamento.exe" >nul 2>nul
"%ISCC%" "/O%SAIDA%" "/DVersao=%VERSAO%" "/DUsaBanco=1" instalador.iss
if not errorlevel 1 goto compilou
if %TENTATIVA% GEQ 3 goto erro_instalador
echo.
echo  O antivirus atrapalhou. Tentando de novo em 10 segundos (tentativa %TENTATIVA% de 3)...
timeout /t 10 /nobreak >nul
goto compilar

:compilou
copy /y "%SAIDA%\Instalar_CenegedLevantamento.exe" "%ORIGEM%Instalar_CenegedLevantamento.exe" >nul

echo  [5/5] Publicando a versao %VERSAO% no banco de dados (atualizacao automatica)...
set PUBLICADO=
".build\Scripts\python.exe" "%ORIGEM%publicar_atualizacao.py" "%ORIGEM%banco_mongo.txt" "%SAIDA%\Instalar_CenegedLevantamento.exe" %VERSAO%
if not errorlevel 1 set PUBLICADO=1

rmdir /s /q build >nul 2>nul
del /q CenegedLevantamento.spec >nul 2>nul
echo.
echo  ==================================================================
echo   PRONTO!  Instalar_CenegedLevantamento.exe esta nesta pasta
echo   (e tambem em %SAIDA%).
echo  ==================================================================
if defined PUBLICADO echo   Versao %VERSAO% publicada no banco de dados.
if defined PUBLICADO echo   Quem ja tem o programa recebe o aviso de atualizacao ao abrir.
if defined PUBLICADO echo   Colaborador novo: mande o Instalar_CenegedLevantamento.exe para ele.
if not defined PUBLICADO echo   ATENCAO: nao consegui publicar no banco (veja a mensagem acima).
if not defined PUBLICADO echo   O instalador funciona, mas ninguem recebe o aviso de atualizacao.
if not defined PUBLICADO echo   Confira a internet e o banco_mongo.txt e rode de novo.
echo.
pause
exit /b 0

:dentro_do_zip
echo.
echo  Este arquivo foi aberto de dentro do .zip.
echo  Feche esta janela, clique com o botao direito no .zip ^> "Extrair tudo...",
echo  abra a pasta extraida e de dois cliques no GERAR_INSTALADOR.bat de la.
goto fim_erro

:sem_codigo
echo.
echo  Nao encontrei o codigo do programa (iniciar.py e a pasta ceneged)
echo  na pasta acima desta:
echo     %~dp0..
echo  Este arquivo tem que ficar dentro da pasta "instalador" do repositorio.
goto fim_erro

:sem_iss
echo.
echo  Faltam arquivos nesta pasta (instalador.iss / ceneged.ico / publicar_atualizacao.py).
echo  Coloque todos os arquivos juntos e rode o GERAR_INSTALADOR.bat de novo.
goto fim_erro

:sem_banco
echo.
echo  Falta o arquivo banco_mongo.txt nesta pasta (endereco e senha do banco MongoDB).
echo  Coloque o banco_mongo.txt aqui e rode de novo.
goto fim_erro

:sem_senha_banco
echo.
echo  O arquivo banco_mongo.txt ainda esta com COLOQUE_A_SENHA_AQUI.
echo  Abra o banco_mongo.txt no Bloco de Notas, troque pela senha do usuario do banco
echo  (MongoDB Atlas ^> Database Access), salve e rode de novo.
goto fim_erro

:sem_python
echo.
echo  Python nao encontrado.
echo  Instale em https://www.python.org/downloads/
echo  (na instalacao marque "Add python.exe to PATH") e abra este arquivo de novo.
goto fim_erro

:erro_ambiente
echo  Falha ao criar o ambiente do Python.
goto fim_erro

:erro_bibliotecas
echo  Falha ao instalar as bibliotecas. Verifique a internet e tente de novo.
goto fim_erro

:erro_programa
echo  Falha ao montar o programa (veja as mensagens acima).
goto fim_erro

:sem_inno
echo.
echo  Nao consegui instalar o Inno Setup sozinho.
echo  Baixe e instale em https://jrsoftware.org/isdl.php  (gratis)
echo  e abra este arquivo de novo.
goto fim_erro

:erro_instalador
echo.
echo  Falha ao criar o instalador (veja as mensagens acima).
echo  Se o erro for "EndUpdateResource failed (110)": o antivirus esta bloqueando.
echo  Abra Seguranca do Windows ^> Protecao contra virus e ameacas ^> Gerenciar
echo  configuracoes ^> Exclusoes ^> Adicionar exclusao ^> Pasta, escolha
echo     %SAIDA%
echo  e rode este arquivo de novo.
goto fim_erro

:fim_erro
echo.
pause
exit /b 1
