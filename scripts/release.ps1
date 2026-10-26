# Export an explicit allowlist, never the current data/config directory recursively.
$ErrorActionPreference = 'Stop'
$releaseRoot = Split-Path -Parent $PSScriptRoot
$releaseOutput = Join-Path $releaseRoot 'dist'
$releaseStage = Join-Path $releaseOutput ('paper-agent-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $releaseStage -Force | Out-Null
foreach ($releaseFolder in @('src','tests','schemas','prompts','behaviors','templates','scripts','docs')) {
    Get-ChildItem -LiteralPath (Join-Path $releaseRoot $releaseFolder) -File -Recurse |
        Where-Object { $_.FullName -notmatch '[\\/](__pycache__|[^\\/]+\.egg-info)[\\/]' -and $_.Extension -ne '.pyc' } |
        ForEach-Object {
            $releaseRelative = $_.FullName.Substring($releaseRoot.Length + 1)
            $releaseTarget = Join-Path $releaseStage $releaseRelative
            New-Item -ItemType Directory -Path (Split-Path -Parent $releaseTarget) -Force | Out-Null
            Copy-Item -LiteralPath $_.FullName -Destination $releaseTarget
        }
}
foreach ($releaseFile in @('README.md','pyproject.toml','requirements.txt','uv.toml','.gitignore','data/README.md','config/.env.example','config/model.toml','config/planning.toml','assets/default-agent.svg')) {
    $releaseTarget = Join-Path $releaseStage $releaseFile
    New-Item -ItemType Directory -Path (Split-Path -Parent $releaseTarget) -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $releaseRoot $releaseFile) -Destination $releaseTarget
}
Get-ChildItem -LiteralPath $releaseRoot -File | Where-Object { $_.Extension -in '.pyw','.vbs' } | Copy-Item -Destination $releaseStage
$releaseArchive = Join-Path $releaseOutput 'paper-agent-source.zip'
Compress-Archive -Path (Join-Path $releaseStage '*') -DestinationPath $releaseArchive -Force
Write-Host $releaseStage
Write-Host $releaseArchive
