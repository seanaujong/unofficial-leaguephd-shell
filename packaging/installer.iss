; Inno Setup script for the Unofficial League PhD installer.
; Build the app first (packaging/leaguephd.spec), then:
;   ISCC.exe /DAppVersion=0.1.1 packaging\installer.iss
; Output: dist\UnofficialLeaguePhd-Setup-v<version>.exe
;
; Installs per-user (no admin prompt) into %LOCALAPPDATA%\Programs, adds a Start
; menu shortcut and an uninstaller in Windows "Installed apps".

#ifndef AppVersion
  #error Pass the version: ISCC /DAppVersion=X.Y.Z packaging\installer.iss
#endif

#define AppName "Unofficial League PhD"
#define ExeName "UnofficialLeaguePhd.exe"
#define RepoUrl "https://github.com/seanaujong/unofficial-leaguephd-shell"

[Setup]
; Never change AppId: Windows uses it to recognise upgrades and the uninstaller.
AppId={{6E1A6A2B-5D2C-4C47-9E7B-2B8E4C1F7A31}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=leaguephd-shell contributors
AppPublisherURL={#RepoUrl}
AppSupportURL={#RepoUrl}/issues
AppUpdatesURL={#RepoUrl}/releases
AppComments=Unofficial: not made or endorsed by League PhD or Riot Games.
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#AppName}
VersionInfoDescription={#AppName} installer
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
InfoBeforeFile=before-install.txt
SetupIconFile=..\src\leaguephd_shell\icon.ico
UninstallDisplayIcon={app}\{#ExeName}
UninstallDisplayName={#AppName}
OutputDir=..\dist
OutputBaseFilename=UnofficialLeaguePhd-Setup-v{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\UnofficialLeaguePhd\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#ExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#ExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#ExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
