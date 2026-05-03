param(
    [string]$ServerUrl = $env:BAIZEFINDB_SERVER_URL,
    [string]$UserKey = $env:BAIZEFINDB_USER_KEY
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..\..")

if ([string]::IsNullOrWhiteSpace($ServerUrl)) {
    $ServerUrl = "http://127.0.0.1:8000"
}

$env:BAIZEFINDB_SERVER_URL = $ServerUrl
if ([string]::IsNullOrWhiteSpace($UserKey)) {
    $UserKey = "default"
}

$env:BAIZEFINDB_USER_KEY = $UserKey
Set-Location $RepoRoot

python -m clients.windows.baizefindb_client
