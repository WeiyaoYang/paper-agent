$ErrorActionPreference = 'Stop'
$agentProjectRoot = Split-Path -Parent $PSScriptRoot
$agentLauncher = Get-ChildItem -LiteralPath $agentProjectRoot -Filter '*.pyw' | Select-Object -First 1
$agentPython = Join-Path $agentProjectRoot '.venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $agentPython)) { throw 'Run scripts/install.ps1 first.' }
$agentDesktop = [Environment]::GetFolderPath('Desktop')
$agentShell = New-Object -ComObject WScript.Shell
$agentShortcut = $agentShell.CreateShortcut((Join-Path $agentDesktop 'Agent Workbench.lnk'))
$agentShortcut.TargetPath = $agentPython
$agentShortcut.Arguments = '"' + $agentLauncher.FullName + '"'
$agentShortcut.WorkingDirectory = $agentProjectRoot
$agentShortcut.IconLocation = $agentPython + ',0'
$agentShortcut.Save()
Write-Host 'Created Agent Workbench shortcut on your desktop.'
