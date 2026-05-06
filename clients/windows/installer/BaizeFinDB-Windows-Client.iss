#define AppName "BaizeFinDB Windows Client"
#define AppPublisher "BaizeFinDB"
#define AppExeName "BaizeFinDB-Windows-Client.exe"

#ifndef AppVersion
#define AppVersion "0.1.0-preview"
#endif

#ifndef SourceDir
#define SourceDir "..\dist\BaizeFinDB-Windows-Client"
#endif

#ifndef OutputDir
#define OutputDir "..\dist\installer"
#endif

#ifndef SetupBaseName
#define SetupBaseName "BaizeFinDB-Windows-Client-Setup"
#endif

[Setup]
AppId={{C958A8F2-20FB-42E2-ABE9-4DB08E3DD6E4}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\BaizeFinDB Windows Client
DefaultGroupName=BaizeFinDB
DisableProgramGroupPage=yes
OutputDir={#OutputDir}
OutputBaseFilename={#SetupBaseName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\{#AppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\BaizeFinDB Windows Client"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\BaizeFinDB Windows Client"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
