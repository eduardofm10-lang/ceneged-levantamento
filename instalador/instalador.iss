; Instalador do Ceneged · Levantamento de Materiais (Inno Setup 6).
; Não precisa abrir este arquivo: o GERAR_INSTALADOR.bat usa ele sozinho.

#ifndef Versao
  #define Versao "1.0"
#endif
#ifndef PastaDados
  #define PastaDados ""
#endif
#ifndef UsaBanco
  #define UsaBanco "0"
#endif

[Setup]
AppId={{F2669EB9-6B6A-44D9-9457-F44863E146A2}
AppName=Ceneged Levantamento de Materiais
AppVersion={#Versao}
AppVerName=Ceneged Levantamento de Materiais {#Versao}
AppPublisher=Ceneged
DefaultDirName={autopf}\Ceneged Levantamento
DefaultGroupName=Ceneged
DisableProgramGroupPage=yes
; instala só para o usuário: não pede senha de administrador do Windows
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=.
OutputBaseFilename=Instalar_CenegedLevantamento
SetupIconFile=ceneged.ico
UninstallDisplayIcon={app}\CenegedLevantamento.exe
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
CloseApplications=yes

[Languages]
Name: "pt"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "atalho"; Description: "Criar atalho na área de trabalho"; GroupDescription: "Atalhos:"

[Files]
Source: "dist\CenegedLevantamento\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Ceneged Levantamento de Materiais"; Filename: "{app}\CenegedLevantamento.exe"
Name: "{autodesktop}\Ceneged Levantamento de Materiais"; Filename: "{app}\CenegedLevantamento.exe"; Tasks: atalho

[Run]
Filename: "{app}\CenegedLevantamento.exe"; Description: "Abrir o programa agora"; Flags: nowait postinstall skipifsilent
; atualização automática (instalação silenciosa): abre o programa de novo no fim
Filename: "{app}\CenegedLevantamento.exe"; Flags: nowait; Check: WizardSilent

[UninstallDelete]
Type: files; Name: "{app}\pasta_dados.txt"
Type: files; Name: "{app}\versao.txt"

[Code]
var
  PastaPage: TInputQueryWizardPage;

procedure InitializeWizard;
begin
  { caixa de texto simples: a de pasta (InputDir) junta a pasta do instalador na frente de %OneDriveCommercial% }
  PastaPage := CreateInputQueryPage(wpSelectDir,
    'Pasta compartilhada',
    'Onde ficam os usuários, o cadastro de materiais e as regras?',
    'Pode deixar como está e clicar em Avançar: se a pasta estiver em outro lugar no seu OneDrive ' +
    '(ex.: direto em OneDrive\Levantamento), o programa acha a pasta compartilhada sozinho.' + #13#10 + #13#10 +
    'Antes, adicione a pasta Levantamento ao seu OneDrive: e-mail de compartilhamento > Abrir > "Adicionar atalho a Meus arquivos".');
  PastaPage.Add('Pasta compartilhada:', False);
  PastaPage.Values[0] := '{#PastaDados}';
end;

{ com banco de dados (MongoDB) não existe pasta compartilhada: a tela nem aparece }
function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := (PageID = PastaPage.ID) and ('{#UsaBanco}' = '1');
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = PastaPage.ID) and (Trim(PastaPage.Values[0]) <> '') and (Pos('%', PastaPage.Values[0]) = 0) and (not DirExists(PastaPage.Values[0])) then
    Result := MsgBox('Não encontrei a pasta:' + #13#10 + PastaPage.Values[0] + #13#10 + #13#10 +
                     'Ela pode estar fora do ar agora (rede/OneDrive). Continuar mesmo assim?',
                     mbConfirmation, MB_YESNO) = IDYES;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Linhas: TArrayOfString;
begin
  if CurStep = ssPostInstall then
  begin
    SetArrayLength(Linhas, 1);
    Linhas[0] := '{#Versao}';
    SaveStringsToUTF8File(ExpandConstant('{app}\versao.txt'), Linhas, False);
    { banco de dados: não mexe no pasta_dados.txt antigo (o programa usa o banco; a pasta antiga
      só serve, na primeira vez, para levar os dados para o banco) }
    if '{#UsaBanco}' = '1' then
      Exit;
    { atualização automática: mantém a pasta que já estava configurada neste computador }
    if WizardSilent and FileExists(ExpandConstant('{app}\pasta_dados.txt')) then
      Exit;
    if Trim(PastaPage.Values[0]) <> '' then
    begin
      SetArrayLength(Linhas, 1);
      Linhas[0] := Trim(PastaPage.Values[0]);
      SaveStringsToUTF8File(ExpandConstant('{app}\pasta_dados.txt'), Linhas, False);
    end
    else
      DeleteFile(ExpandConstant('{app}\pasta_dados.txt'));
  end;
end;
