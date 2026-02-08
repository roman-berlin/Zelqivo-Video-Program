; Inno Setup script for Zelqivo (Windows 10/11)
; Save as: C:\Python Projects\Video_Program\installer\setup1.iss
; Icon file recommended path:
;   C:\Python Projects\Video_Program\installer\assets\icons\Zelqivo.ico

#define MyAppName "Zelqivo"
#define MyAppVersion "1.0.3"
#define MyAppPublisher "Roman Berlin"
#define MyAppExeName "MulticamEditor.exe"

; Recommended relative paths (relative to this .iss file inside /installer)
#define MyDistDir "..\dist\MulticamEditor"
#define MyIconFile "assets\icons\Zelqivo.ico"

[Setup]
; NOTE: AppId must stay the same for upgrades of the SAME app
AppId={{309602F2-D1D7-4559-8184-4C78E579B907}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}

DefaultDirName={autopf}\{#MyAppName}
PrivilegesRequired=admin

UninstallDisplayIcon={app}\{#MyAppExeName}

OutputDir=build_installer
OutputBaseFilename={#MyAppName}_Setup_{#MyAppVersion}
Compression=lzma
SolidCompression=yes

WizardStyle=modern
SetupIconFile={#MyIconFile}

ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Copy the whole PyInstaller dist folder (EXE + all deps)
Source: "{#MyDistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; Copy icon into install dir with a forced stable name for shortcuts
Source: "{#MyIconFile}"; DestDir: "{app}"; DestName: "Zelqivo.ico"; Flags: ignoreversion

[Icons]
; Start Menu shortcut (forces our icon)
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\Zelqivo.ico"

; Desktop shortcut (optional task)
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; IconFilename: "{app}\Zelqivo.ico"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
