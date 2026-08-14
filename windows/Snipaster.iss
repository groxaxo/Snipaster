#define MyAppName "Snipaster"
#define MyAppVersion "0.2.0"
#define MyAppPublisher "Snipaster contributors"
#define MyAppExeName "Snipaster.exe"

[Setup]
AppId={{B16FD5E6-BD35-4D72-98A8-45C9270B7FA9}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Snipaster-Setup-{#MyAppVersion}
SetupIconFile=..\assets\snipaster.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no

[Types]
Name: "full"; Description: "Full installation"
Name: "compact"; Description: "Application and Start Menu shortcut"
Name: "custom"; Description: "Custom installation"; Flags: iscustom

[Components]
Name: "startmenu"; Description: "Start Menu shortcut"; Types: full compact custom
Name: "desktop"; Description: "Desktop annotation shortcut"; Types: full
Name: "startup"; Description: "Tray icon and global F1/F2 hotkeys at sign-in"; Types: full

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "annotate"; WorkingDir: "{app}"; Components: startmenu
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "annotate"; WorkingDir: "{app}"; Components: desktop
Name: "{userstartup}\{#MyAppName} Tray"; Filename: "{app}\{#MyAppExeName}"; Parameters: "tray"; WorkingDir: "{app}"; Components: startup

[Run]
Filename: "{app}\{#MyAppExeName}"; Parameters: "tray"; Description: "Start the Snipaster tray icon and F1/F2 hotkeys"; Flags: nowait postinstall skipifsilent; Components: startup

[UninstallRun]
Filename: "{cmd}"; Parameters: "/c taskkill /F /IM {#MyAppExeName}"; Flags: runhidden; RunOnceId: "StopSnipaster"
