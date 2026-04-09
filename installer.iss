; ============================================================
;  Photo Organizer - Inno Setup Installer Script
;  To build: install Inno Setup, open this file, click Build
; ============================================================

#define AppName      "Photo Organizer"
#define AppVersion   "1.1.0"
#define AppPublisher "Your Name"
#define AppURL       "https://github.com/Nonflavored/photo-organizer"
#define AppExeName   "Photo Organizer.exe"

[Setup]
AppId={{8F3A2B1C-4D5E-6F7A-8B9C-0D1E2F3A4B5C}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes
LicenseFile=
OutputDir=installer_output
OutputBaseFilename=PhotoOrganizer_Setup_v{#AppVersion}
SetupIconFile=icon.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern
; Makes it look clean and modern
WizardSmallImageFile=
WizardImageFile=
DisableWelcomePage=no
DisableDirPage=no
DisableProgramGroupPage=yes
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExeName}
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon";    Description: "Create a &desktop shortcut";     GroupDescription: "Additional shortcuts:"; Flags: checked
Name: "startmenuicon";  Description: "Create a &Start Menu shortcut";  GroupDescription: "Additional shortcuts:"; Flags: checked

[Files]
Source: "dist\Photo Organizer.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}";           Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{commondesktop}\{#AppName}";   Filename: "{app}\{#AppExeName}"; Tasks: desktopicon
Name: "{commonstartmenu}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: startmenuicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Messages]
WelcomeLabel2=This will install [name/ver] on your computer.%n%nSimply click Next to continue, or Cancel if you'd like to exit.
FinishedHeadingLabel=Setup complete!
FinishedLabel=Photo Organizer has been installed.%n%nClick Finish to launch it now.
