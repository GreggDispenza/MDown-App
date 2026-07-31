; Inno Setup script for MDown.
;
; Wraps the self-contained Flet app folder (mdown_app.exe + its DLLs and
; data/ folder) into a single MDown-Setup.exe installer that:
;   - installs into Program Files (per-machine) or the user's app data,
;   - creates Start-menu and optional Desktop shortcuts,
;   - registers a proper uninstaller in "Apps & features".
;
; The source folder is passed in by CI with /DAppSrc=<absolute path to
; staging\MDown>. Building locally? Point AppSrc at your built app folder:
;   ISCC.exe /DAppSrc=C:\path\to\MDown packaging\windows\mdown.iss
;
; The app version can be overridden with /DAppVersion=x.y.z (defaults below).

#ifndef AppSrc
  #error Define AppSrc (path to the built MDown app folder), e.g. /DAppSrc=staging\MDown
#endif
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

#define MyAppName "MDown"
#define MyAppExeName "mdown_app.exe"
#define MyAppPublisher "MDown-App contributors"
#define MyAppURL "https://github.com/GreggDispenza/MDown-App"

[Setup]
; A stable AppId keeps upgrades/uninstall coherent across versions.
AppId={{5F3B9C2A-4D1E-4A77-9C0B-1A2B3C4D5E6F}}
AppName={#MyAppName}
AppVersion={#AppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
OutputBaseFilename=MDown-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; The Flet app is 64-bit; install into the real Program Files on x64.
ArchitecturesInstallIn64BitMode=x64compatible
; Allow a normal user to install into their own profile without admin.
PrivilegesRequiredOverridesAllowed=commandline dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Recurse the entire staged app folder into {app}.
Source: "{#AppSrc}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
