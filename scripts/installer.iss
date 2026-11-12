; Inno Setup script for Robot Diag. Built by scripts/build_exe.ps1:
;   ISCC.exe /DAppVersion=<x.y.z> /DSourceDir=<dist\RobotDiag> /DOutDir=<dist\installer> scripts\installer.iss
; Per-user install (no administrator): the app goes to %LOCALAPPDATA%\Programs\RobotDiag, recordings and settings stay in
; %LOCALAPPDATA%\RobotDiag and are NOT removed by an uninstall or an upgrade.
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\RobotDiag"
#endif
#ifndef OutDir
  #define OutDir "..\dist\installer"
#endif

[Setup]
AppId={{6F0B7C3E-4B0A-4C1E-9C57-5D0A1E7B2A11}
AppName=Robot Diag
AppVersion={#AppVersion}
AppPublisher=robot_diag
DefaultDirName={localappdata}\Programs\RobotDiag
DefaultGroupName=Robot Diag
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutDir}
OutputBaseFilename=RobotDiag-Setup-{#AppVersion}
SetupIconFile=robot_diag.ico
UninstallDisplayIcon={app}\RobotDiag.exe
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\Robot Diag"; Filename: "{app}\RobotDiag.exe"
Name: "{autodesktop}\Robot Diag"; Filename: "{app}\RobotDiag.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\RobotDiag.exe"; Description: "Start Robot Diag"; Flags: nowait postinstall skipifsilent

[Code]
// The window is the Microsoft Edge WebView2 runtime (part of Windows 11 and of current Microsoft Edge on Windows 10).
function WebView2Installed(): Boolean;
var v: String;
begin
  Result := RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', v)
         or RegQueryStringValue(HKCU, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', v);
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if (CurPageID = wpFinished) and (not WebView2Installed()) then
    MsgBox('The Microsoft Edge WebView2 runtime was not found. Robot Diag needs it to open its window: install it from ' +
           'https://developer.microsoft.com/microsoft-edge/webview2/ (Evergreen runtime).', mbInformation, MB_OK);
end;
