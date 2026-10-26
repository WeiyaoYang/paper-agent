$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\env.ps1"
Set-Location $paperAgentRoot
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw 'Install uv first: https://docs.astral.sh/uv/getting-started/installation/'
}
if (-not (Test-Path '.venv\Scripts\python.exe')) {
    uv venv --python 3.12 .venv
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
}
uv pip install --python '.venv\Scripts\python.exe' -e '.[models,desktop,docling]'
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& '.\.venv\Scripts\python.exe' -m paper_agent init
if ($LASTEXITCODE -ne 0) { throw 'Initialization failed.' }
Write-Host 'Ready. Double-click the VBS launcher in the project folder.'
