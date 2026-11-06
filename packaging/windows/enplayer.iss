; Inno Setup script — produces dist/ENPlayer-Setup-<version>.exe
; Build:  iscc packaging\windows\enplayer.iss   (after build-windows.sh)

#define AppName "ENPlayer"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define Bundle "..\..\dist\windows\ENPlayer"

[Setup]
AppId={{6B3E2F7A-5C1D-4E8B-9A0F-2D7C41F0B9E3}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Estiaque
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Per-user install by default: no admin password needed. Users may choose "all users".
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\..\dist
OutputBaseFilename=ENPlayer-Setup-{#AppVersion}
SetupIconFile=enplayer.ico
UninstallDisplayIcon={app}\enplayer.ico
UninstallDisplayName={#AppName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ChangesAssociations=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "openwith"; Description: "Add ENPlayer to ""Open with"" for video files"; GroupDescription: "Integration:"

[Files]
Source: "{#Bundle}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\bin\pythonw.exe"; Parameters: "-m neplayer.main"; \
  WorkingDir: "{app}\bin"; IconFilename: "{app}\enplayer.ico"; AppUserModelID: "ENPlayer.ENPlayer"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\bin\pythonw.exe"; Parameters: "-m neplayer.main"; \
  WorkingDir: "{app}\bin"; IconFilename: "{app}\enplayer.ico"; AppUserModelID: "ENPlayer.ENPlayer"; Tasks: desktopicon

[Registry]
; "Open with ENPlayer" for common video types (does not change the user's default player).
Root: HKA; Subkey: "Software\Classes\ENPlayer.Video"; ValueType: string; ValueData: "Video (ENPlayer)"; Flags: uninsdeletekey; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\ENPlayer.Video\DefaultIcon"; ValueType: string; ValueData: "{app}\enplayer.ico"; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\ENPlayer.Video\shell\open\command"; ValueType: string; ValueData: """{app}\bin\pythonw.exe"" -m neplayer.main ""%1"""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.mp4\OpenWithProgids"; ValueType: string; ValueName: "ENPlayer.Video"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.mkv\OpenWithProgids"; ValueType: string; ValueName: "ENPlayer.Video"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.avi\OpenWithProgids"; ValueType: string; ValueName: "ENPlayer.Video"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.mov\OpenWithProgids"; ValueType: string; ValueName: "ENPlayer.Video"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.webm\OpenWithProgids"; ValueType: string; ValueName: "ENPlayer.Video"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.wmv\OpenWithProgids"; ValueType: string; ValueName: "ENPlayer.Video"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.flv\OpenWithProgids"; ValueType: string; ValueName: "ENPlayer.Video"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.m4v\OpenWithProgids"; ValueType: string; ValueName: "ENPlayer.Video"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.ts\OpenWithProgids"; ValueType: string; ValueName: "ENPlayer.Video"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.mpg\OpenWithProgids"; ValueType: string; ValueName: "ENPlayer.Video"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.3gp\OpenWithProgids"; ValueType: string; ValueName: "ENPlayer.Video"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith

[Run]
Filename: "{app}\bin\pythonw.exe"; Parameters: "-m neplayer.main"; WorkingDir: "{app}\bin"; \
  Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Library database and thumbnails live in %LOCALAPPDATA%\NEPLAYER; removed only if the user agrees (see code).

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    if DirExists(ExpandConstant('{localappdata}\NEPLAYER')) then
      if MsgBox('Also delete your ENPlayer library data (watch history, favorites and thumbnails)?' + #13#10 +
                'Your video files are never touched.', mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(ExpandConstant('{localappdata}\NEPLAYER'), True, True, True);
end;
