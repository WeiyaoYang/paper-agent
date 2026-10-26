param([switch]$Personal)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\env.ps1"
Set-Location $paperAgentRoot
$portableExisting = Join-Path $paperAgentRoot 'dist/portable/AgentWorkbench'
if ((Test-Path (Join-Path $portableExisting 'data/results')) -or (Test-Path (Join-Path $portableExisting 'config/.env.local'))) {
    throw 'The existing portable folder contains user data or credentials. Move it to a safe location before rebuilding.'
}
# Do not resolve native DLLs from unrelated applications installed on the build host.
$env:PATH = "$env:SystemRoot\System32;$env:SystemRoot;$paperAgentRoot\.venv\Scripts"
& '.\.venv\Scripts\python.exe' -m PyInstaller --noconfirm --workpath 'build/portable' --distpath 'dist/portable' scripts/portable.spec
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed. See build/portable.' }
& '.\.venv\Scripts\python.exe' scripts/sanitize-portable.py
if ($LASTEXITCODE -ne 0) { throw 'Portable DLL sanitization failed.' }
$portableTarget = Join-Path $paperAgentRoot 'dist/portable/AgentWorkbench'
foreach ($portableFolder in @('schemas','prompts','behaviors','templates')) {
    Copy-Item -LiteralPath (Join-Path $paperAgentRoot $portableFolder) -Destination $portableTarget -Recurse -Force
}
foreach ($portableFolder in @('config','assets')) {
    New-Item -ItemType Directory -Path (Join-Path $portableTarget $portableFolder) -Force | Out-Null
}
foreach ($portableFile in @('config/model.toml','config/planning.toml','config/.env.example','assets/default-agent.svg')) {
    Copy-Item -LiteralPath (Join-Path $paperAgentRoot $portableFile) -Destination (Join-Path $portableTarget $portableFile) -Force
}
if ($Personal) {
    foreach ($portableFile in @('assets/app-icon-cutout.ico','assets/welcome-character-hd.png')) {
        Copy-Item -LiteralPath (Join-Path $paperAgentRoot $portableFile) -Destination (Join-Path $portableTarget $portableFile) -Force
    }
}
Copy-Item -LiteralPath 'docs/portable.md' -Destination (Join-Path $portableTarget 'README.txt') -Force
Write-Host $portableTarget
Write-Host 'Copy the entire folder. API keys and user data are not included.'
