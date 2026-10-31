; Inno Setup script: turns dist\PrintEasy into one friendly PrintEasy-Setup.exe
; Build:  iscc packaging\windows\printeasy.iss    (run from the project folder, after PyInstaller)

#define AppName "PrintEasy"
#define AppVersion "1.0.0"

[Setup]
AppId={{6E2B8C51-3E1D-4A7B-9C55-5B0A1F0E7A21}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=PrintEasy
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=yes
OutputDir=..\..\dist\installers
OutputBaseFilename=PrintEasy-Setup-{#AppVersion}-Windows
SetupIconFile=..\assets\printeasy.ico
UninstallDisplayIcon={app}\PrintEasy.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Put a PrintEasy icon on my desktop"; Flags: checkedonce
Name: "startup"; Description: "Start PrintEasy when I turn on my computer (keeps per-program printers working)"; Flags: unchecked

[Files]
Source: "..\..\dist\PrintEasy\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\PrintEasy.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\PrintEasy.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "PrintEasy"; ValueData: """{app}\PrintEasy.exe"" --tray"; Flags: uninsdeletevalue; Tasks: startup

[Run]
Filename: "{app}\PrintEasy.exe"; Description: "Open PrintEasy now"; Flags: nowait postinstall skipifsilent runasoriginaluser

[UninstallRun]
Filename: "taskkill"; Parameters: "/IM PrintEasy.exe /F"; Flags: runhidden; RunOnceId: "StopPrintEasy"

[UninstallDelete]
Type: filesandordirs; Name: "{userappdata}\PrintEasy"
