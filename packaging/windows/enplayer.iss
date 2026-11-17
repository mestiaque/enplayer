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
AppPublisher=M. Estiaque Ahmed Khan
AppPublisherURL=https://mestiaque.com
AppSupportURL=https://github.com/mestiaque/enplayer/issues
AppUpdatesURL=https://github.com/mestiaque/enplayer/releases
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Per-user install by default: no admin password needed. Users may choose "all users".
PrivilegesRequired=lowest
; commandline: the in-app updater passes /ALLUSERS (Program Files copy) or /CURRENTUSER
PrivilegesRequiredOverridesAllowed=commandline dialog
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
Name: "openwith"; Description: "Add ENPlayer to ""Open with"" for video and music files"; GroupDescription: "Integration:"

[InstallDelete]
; Updating over an older ENPlayer: remove its bundled runtime first, so files the new, smaller
; bundle no longer contains do not stay behind (1.4.9 and older shipped ~790 MB). Only done
; when the folder really holds an ENPlayer bundle; library data is in %LOCALAPPDATA%\NEPLAYER.
Type: filesandordirs; Name: "{app}\bin"; Check: IsEnplayerBundle
Type: filesandordirs; Name: "{app}\lib"; Check: IsEnplayerBundle
Type: filesandordirs; Name: "{app}\share"; Check: IsEnplayerBundle
Type: filesandordirs; Name: "{app}\etc"; Check: IsEnplayerBundle
Type: filesandordirs; Name: "{app}\libexec"; Check: IsEnplayerBundle

[Files]
Source: "{#Bundle}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\bin\ENPlayer.exe"; WorkingDir: "{app}\bin"; AppUserModelID: "ENPlayer.ENPlayer"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\bin\ENPlayer.exe"; WorkingDir: "{app}\bin"; AppUserModelID: "ENPlayer.ENPlayer"; Tasks: desktopicon

[Registry]
; ENPlayer.exe (see launcher.c) is what Windows shows by name in "Open with" and in
; Settings > Apps > Default apps. Nothing here changes the user's current default player.
Root: HKA; Subkey: "Software\Classes\Applications\ENPlayer.exe"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "ENPlayer"; Flags: uninsdeletekey; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\ENPlayer.exe\DefaultIcon"; ValueType: string; ValueData: "{app}\bin\ENPlayer.exe,0"; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\ENPlayer.exe\shell\open\command"; ValueType: string; ValueData: """{app}\bin\ENPlayer.exe"" ""%1"""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\ENPlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".mp4"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\ENPlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".mkv"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\ENPlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".avi"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\ENPlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".mov"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\ENPlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".webm"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\ENPlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".wmv"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\ENPlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".flv"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\ENPlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".m4v"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\ENPlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".ts"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\ENPlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".m2ts"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\ENPlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".mpg"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\ENPlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".mpeg"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\ENPlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".3gp"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\ENPlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".mp3"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\ENPlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".flac"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\ENPlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".m4a"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\ENPlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".aac"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\ENPlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".ogg"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\ENPlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".opus"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\ENPlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".wav"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\Applications\ENPlayer.exe\SupportedTypes"; ValueType: string; ValueName: ".wma"; ValueData: ""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\ENPlayer.Video"; ValueType: string; ValueData: "Video (ENPlayer)"; Flags: uninsdeletekey; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\ENPlayer.Video\DefaultIcon"; ValueType: string; ValueData: "{app}\enplayer.ico"; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\ENPlayer.Video\shell\open"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "ENPlayer"; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\ENPlayer.Video\shell\open\command"; ValueType: string; ValueData: """{app}\bin\ENPlayer.exe"" ""%1"""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\ENPlayer.Audio"; ValueType: string; ValueData: "Audio (ENPlayer)"; Flags: uninsdeletekey; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\ENPlayer.Audio\DefaultIcon"; ValueType: string; ValueData: "{app}\enplayer.ico"; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\ENPlayer.Audio\shell\open"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "ENPlayer"; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\ENPlayer.Audio\shell\open\command"; ValueType: string; ValueData: """{app}\bin\ENPlayer.exe"" ""%1"""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.mp4\OpenWithProgids"; ValueType: string; ValueName: "ENPlayer.Video"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.mkv\OpenWithProgids"; ValueType: string; ValueName: "ENPlayer.Video"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.avi\OpenWithProgids"; ValueType: string; ValueName: "ENPlayer.Video"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.mov\OpenWithProgids"; ValueType: string; ValueName: "ENPlayer.Video"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.webm\OpenWithProgids"; ValueType: string; ValueName: "ENPlayer.Video"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.wmv\OpenWithProgids"; ValueType: string; ValueName: "ENPlayer.Video"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.flv\OpenWithProgids"; ValueType: string; ValueName: "ENPlayer.Video"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.m4v\OpenWithProgids"; ValueType: string; ValueName: "ENPlayer.Video"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.ts\OpenWithProgids"; ValueType: string; ValueName: "ENPlayer.Video"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.m2ts\OpenWithProgids"; ValueType: string; ValueName: "ENPlayer.Video"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.mpg\OpenWithProgids"; ValueType: string; ValueName: "ENPlayer.Video"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.mpeg\OpenWithProgids"; ValueType: string; ValueName: "ENPlayer.Video"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.3gp\OpenWithProgids"; ValueType: string; ValueName: "ENPlayer.Video"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.mp3\OpenWithProgids"; ValueType: string; ValueName: "ENPlayer.Audio"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.flac\OpenWithProgids"; ValueType: string; ValueName: "ENPlayer.Audio"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.m4a\OpenWithProgids"; ValueType: string; ValueName: "ENPlayer.Audio"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.aac\OpenWithProgids"; ValueType: string; ValueName: "ENPlayer.Audio"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.ogg\OpenWithProgids"; ValueType: string; ValueName: "ENPlayer.Audio"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.opus\OpenWithProgids"; ValueType: string; ValueName: "ENPlayer.Audio"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.wav\OpenWithProgids"; ValueType: string; ValueName: "ENPlayer.Audio"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.wma\OpenWithProgids"; ValueType: string; ValueName: "ENPlayer.Audio"; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith
Root: HKA; Subkey: "Software\ENPlayer\Capabilities"; ValueType: string; ValueName: "ApplicationName"; ValueData: "ENPlayer"; Flags: uninsdeletekey; Tasks: openwith
Root: HKA; Subkey: "Software\ENPlayer\Capabilities"; ValueType: string; ValueName: "ApplicationDescription"; ValueData: "Video and music library with live hover previews"; Tasks: openwith
Root: HKA; Subkey: "Software\ENPlayer\Capabilities"; ValueType: string; ValueName: "ApplicationIcon"; ValueData: "{app}\bin\ENPlayer.exe,0"; Tasks: openwith
Root: HKA; Subkey: "Software\ENPlayer\Capabilities\FileAssociations"; ValueType: string; ValueName: ".mp4"; ValueData: "ENPlayer.Video"; Tasks: openwith
Root: HKA; Subkey: "Software\ENPlayer\Capabilities\FileAssociations"; ValueType: string; ValueName: ".mkv"; ValueData: "ENPlayer.Video"; Tasks: openwith
Root: HKA; Subkey: "Software\ENPlayer\Capabilities\FileAssociations"; ValueType: string; ValueName: ".avi"; ValueData: "ENPlayer.Video"; Tasks: openwith
Root: HKA; Subkey: "Software\ENPlayer\Capabilities\FileAssociations"; ValueType: string; ValueName: ".mov"; ValueData: "ENPlayer.Video"; Tasks: openwith
Root: HKA; Subkey: "Software\ENPlayer\Capabilities\FileAssociations"; ValueType: string; ValueName: ".webm"; ValueData: "ENPlayer.Video"; Tasks: openwith
Root: HKA; Subkey: "Software\ENPlayer\Capabilities\FileAssociations"; ValueType: string; ValueName: ".wmv"; ValueData: "ENPlayer.Video"; Tasks: openwith
Root: HKA; Subkey: "Software\ENPlayer\Capabilities\FileAssociations"; ValueType: string; ValueName: ".flv"; ValueData: "ENPlayer.Video"; Tasks: openwith
Root: HKA; Subkey: "Software\ENPlayer\Capabilities\FileAssociations"; ValueType: string; ValueName: ".m4v"; ValueData: "ENPlayer.Video"; Tasks: openwith
Root: HKA; Subkey: "Software\ENPlayer\Capabilities\FileAssociations"; ValueType: string; ValueName: ".ts"; ValueData: "ENPlayer.Video"; Tasks: openwith
Root: HKA; Subkey: "Software\ENPlayer\Capabilities\FileAssociations"; ValueType: string; ValueName: ".m2ts"; ValueData: "ENPlayer.Video"; Tasks: openwith
Root: HKA; Subkey: "Software\ENPlayer\Capabilities\FileAssociations"; ValueType: string; ValueName: ".mpg"; ValueData: "ENPlayer.Video"; Tasks: openwith
Root: HKA; Subkey: "Software\ENPlayer\Capabilities\FileAssociations"; ValueType: string; ValueName: ".mpeg"; ValueData: "ENPlayer.Video"; Tasks: openwith
Root: HKA; Subkey: "Software\ENPlayer\Capabilities\FileAssociations"; ValueType: string; ValueName: ".3gp"; ValueData: "ENPlayer.Video"; Tasks: openwith
Root: HKA; Subkey: "Software\ENPlayer\Capabilities\FileAssociations"; ValueType: string; ValueName: ".mp3"; ValueData: "ENPlayer.Audio"; Tasks: openwith
Root: HKA; Subkey: "Software\ENPlayer\Capabilities\FileAssociations"; ValueType: string; ValueName: ".flac"; ValueData: "ENPlayer.Audio"; Tasks: openwith
Root: HKA; Subkey: "Software\ENPlayer\Capabilities\FileAssociations"; ValueType: string; ValueName: ".m4a"; ValueData: "ENPlayer.Audio"; Tasks: openwith
Root: HKA; Subkey: "Software\ENPlayer\Capabilities\FileAssociations"; ValueType: string; ValueName: ".aac"; ValueData: "ENPlayer.Audio"; Tasks: openwith
Root: HKA; Subkey: "Software\ENPlayer\Capabilities\FileAssociations"; ValueType: string; ValueName: ".ogg"; ValueData: "ENPlayer.Audio"; Tasks: openwith
Root: HKA; Subkey: "Software\ENPlayer\Capabilities\FileAssociations"; ValueType: string; ValueName: ".opus"; ValueData: "ENPlayer.Audio"; Tasks: openwith
Root: HKA; Subkey: "Software\ENPlayer\Capabilities\FileAssociations"; ValueType: string; ValueName: ".wav"; ValueData: "ENPlayer.Audio"; Tasks: openwith
Root: HKA; Subkey: "Software\ENPlayer\Capabilities\FileAssociations"; ValueType: string; ValueName: ".wma"; ValueData: "ENPlayer.Audio"; Tasks: openwith
Root: HKA; Subkey: "Software\RegisteredApplications"; ValueType: string; ValueName: "ENPlayer"; ValueData: "Software\ENPlayer\Capabilities"; Flags: uninsdeletevalue; Tasks: openwith

[Run]
Filename: "{app}\bin\ENPlayer.exe"; WorkingDir: "{app}\bin"; \
  Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Library database and thumbnails live in %LOCALAPPDATA%\NEPLAYER; removed only if the user agrees (see code).

[Code]
function IsEnplayerBundle: Boolean;
begin
  Result := FileExists(ExpandConstant('{app}\enplayer.ico')) and
            FileExists(ExpandConstant('{app}\bin\pythonw.exe')) and
            FileExists(ExpandConstant('{app}\unins000.exe'));
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    if DirExists(ExpandConstant('{localappdata}\NEPLAYER')) then
      if MsgBox('Also delete your ENPlayer library data (watch history, favorites and thumbnails)?' + #13#10 +
                'Your video files are never touched.', mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(ExpandConstant('{localappdata}\NEPLAYER'), True, True, True);
end;
