# Forward all CLI arguments without depending on the shell's current directory.
. "$PSScriptRoot\env.ps1"
& "$paperAgentRoot\.venv\Scripts\python.exe" -m paper_agent @args
exit $LASTEXITCODE
