# Dot-source this file before installing dependencies or running development tools.
$paperAgentRoot = Split-Path -Parent $PSScriptRoot
$env:HF_HOME = Join-Path $paperAgentRoot '.cache\huggingface'
$env:HF_HUB_CACHE = Join-Path $env:HF_HOME 'hub'
$env:HF_XET_CACHE = Join-Path $env:HF_HOME 'xet'
$env:TORCH_HOME = Join-Path $paperAgentRoot '.cache\torch'
$env:XDG_CACHE_HOME = Join-Path $paperAgentRoot '.cache'
$env:UV_CACHE_DIR = Join-Path $paperAgentRoot '.cache\uv'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $paperAgentRoot '.runtime\python'
$env:PIP_CACHE_DIR = Join-Path $paperAgentRoot '.cache\pip'
$env:TEMP = Join-Path $paperAgentRoot 'tmp'
$env:TMP = $env:TEMP
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONPATH = Join-Path $paperAgentRoot 'src'
foreach ($paperAgentPath in @($env:HF_HUB_CACHE, $env:HF_XET_CACHE, $env:TORCH_HOME, $env:UV_CACHE_DIR, $env:UV_PYTHON_INSTALL_DIR, $env:PIP_CACHE_DIR, $env:TEMP)) {
    New-Item -ItemType Directory -Path $paperAgentPath -Force | Out-Null
}
