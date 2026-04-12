; ScreenSnap Installer (Inno Setup)
; Build with: iscc installer.iss
; Requires: Inno Setup 6+  (https://jrsoftware.org/isinfo.php)
; Prereq:   run build-exe.bat first to produce dist\ScreenSnap.exe and dist\ScreenSnapMonitor.exe

#define MyAppName       "ScreenSnap"
#define MyAppVersion    "1.1.0"
#define MyAppPublisher  "ScreenSnap"
#define MyAppExeName    "ScreenSnap.exe"
#define MyMonitorExe    "ScreenSnapMonitor.exe"

[Setup]
AppId={{B3F7C9A4-3D7E-4E2A-9A4C-SCREENSNAP0001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=installer-output
OutputBaseFilename=ScreenSnap-Setup-{#MyAppVersion}
SetupIconFile=screensnap.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon";      Description: "Create a &desktop shortcut";                    GroupDescription: "Additional shortcuts:"
Name: "startupmonitor";   Description: "Start Print Screen monitor at Windows login";   GroupDescription: "Integration:"; Flags: checkedonce

[Files]
Source: "dist\ScreenSnap.exe";         DestDir: "{app}"; Flags: ignoreversion
Source: "dist\ScreenSnapMonitor.exe";  DestDir: "{app}"; Flags: ignoreversion
Source: "screensnap.ico";              DestDir: "{app}"; Flags: ignoreversion
Source: "PRINTSCREEN-SETUP.md";        DestDir: "{app}"; Flags: ignoreversion isreadme
Source: "stamps\*";                    DestDir: "{app}\stamps"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}";          Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}";    Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

; Auto-start the Print Screen monitor on login (per-user Startup)
Name: "{userstartup}\ScreenSnap Monitor"; Filename: "{app}\{#MyMonitorExe}"; Tasks: startupmonitor

[Run]
; Launch ScreenSnap after install
Filename: "{app}\{#MyAppExeName}";    Description: "Launch {#MyAppName}";          Flags: nowait postinstall skipifsilent
; Start the monitor immediately so PrtScn works without reboot
Filename: "{app}\{#MyMonitorExe}";    Description: "Start Print Screen monitor";  Flags: nowait postinstall skipifsilent; Tasks: startupmonitor

[UninstallRun]
; Kill monitor on uninstall so the exe isn't locked
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM {#MyMonitorExe}"; Flags: runhidden; RunOnceId: "KillMonitor"

[UninstallDelete]
Type: files; Name: "{app}\.printscreen-monitor.lock"
Type: files; Name: "{app}\settings.ini"
Type: filesandordirs; Name: "{app}\stamps"
