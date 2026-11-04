; Installer for Desktop Dude.
;
; Installs per-user into LocalAppData\Programs, so no UAC prompt. His save game,
; log, sounds and config live in LocalAppData\DesktopDude and survive uninstalls.
;
; Build:  .\build.ps1   (PyInstaller first, then ISCC.exe Installer\DesktopDude.iss)
; Expects the PyInstaller output in dist\DesktopDude\.

#define AppName "Desktop Dude"
#ifndef AppVersion
  #define AppVersion "1.4.0"
#endif
#define AppPublisher "donalddop"
#define AppUrl "https://github.com/donalddop/desktop-dude"
#define AppExe "DesktopDude.exe"

[Setup]
AppId={{3B6F0D2E-7C41-4A8B-9E15-2F6A8C4D1E97}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppUrl}
AppSupportURL={#AppUrl}
VersionInfoVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\DesktopDude
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir=..\publish
OutputBaseFilename=DesktopDude-setup
SetupIconFile=..\assets\app.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Auto-update runs this silently while the old dude is quitting.
CloseApplications=force
RestartApplications=no

[Languages]
Name: "dutch"; MessagesFile: "compiler:Languages\Dutch.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
dutch.StartWithWindows=Automatisch starten met Windows
dutch.LaunchNow=Laat de dude nu los
english.StartWithWindows=Start automatically with Windows
english.LaunchNow=Unleash the dude now

[Tasks]
Name: "startup"; Description: "{cm:StartWithWindows}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\DesktopDude\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: startup

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchNow}"; Flags: nowait postinstall skipifsilent
; Silent install = an auto-update: bring him straight back.
Filename: "{app}\{#AppExe}"; Flags: nowait; Check: WizardSilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/f /im {#AppExe}"; Flags: runhidden; RunOnceId: "StopDude"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
