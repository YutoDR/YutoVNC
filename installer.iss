; Inno Setup Script for YutoVNC (Smart Remote Client)
; Generates a clean, professional Windows Setup installer (Setup_YutoVNC.exe)

#define MyAppName "YutoVNC"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "YutoVNC Team"
#define MyAppURL "https://github.com/yutovnc"
#define MyAppExeName "YutoVNC.exe"

[Setup]
; Unique GUID for YutoVNC
AppId={{9B3C2A1E-4F5D-6C7B-8A9E-0D1F2E3A4B5C}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; Installation target directory: Program Files for all users, or Local AppData if user-only
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes

; Output Configuration
OutputDir=Output
OutputBaseFilename=Setup_YutoVNC
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

; Modern styling and high-ratio compression
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=auto

; Allow user to choose between installing for All Users (admin) or Current User
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "startmenuicon"; Description: "Buat pintasan di Start Menu"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
; Copy all compiled binaries and assets from dist/YutoVNC
Source: "dist\YutoVNC\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; NOTE: Do not use "Flags: ignoreversion" on any shared system files

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: startmenuicon
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Option to launch YutoVNC immediately after setup completes
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Clean up any leftover cached logs or temp files in installation directory
Type: files; Name: "{app}\*.log"
Type: files; Name: "{app}\*.tmp"
