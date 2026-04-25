$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Desktop = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $Desktop "SkillPool Console.lnk"
$Target = Join-Path $Root "open-console.cmd"
$IconPath = Join-Path $env:SystemRoot "System32\SHELL32.dll"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($ShortcutPath)
$shortcut.TargetPath = $Target
$shortcut.WorkingDirectory = $Root
$shortcut.Description = "Open SkillPool local console"
$shortcut.IconLocation = "$IconPath,220"
$shortcut.Save()

Write-Output "Desktop shortcut created: $ShortcutPath"
