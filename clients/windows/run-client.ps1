param(
    [string]$ServerUrl = $env:BAIZEFINDB_SERVER_URL
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..\..")

if ([string]::IsNullOrWhiteSpace($ServerUrl)) {
    $ServerUrl = "http://127.0.0.1:8000"
}

$env:BAIZEFINDB_SERVER_URL = $ServerUrl
Set-Location $RepoRoot

python -m clients.windows.baizefindb_client
