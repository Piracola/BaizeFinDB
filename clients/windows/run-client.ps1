param(
    [string]$ServerUrl = $env:BAIZEFINDB_SERVER_URL,
    [string]$UserKey = $env:BAIZEFINDB_USER_KEY,
    [switch]$SmokeCheck,
    [string]$SmokeJsonOutput,
    [ValidateRange(1, 168)]
    [int]$SmokeLookbackHours = 24,
    [switch]$SmokeStrict
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

if ($SmokeCheck) {
    $SmokeArgs = @(
        "-m",
        "clients.windows.smoke_check",
        "--server-url",
        $ServerUrl,
        "--user-key",
        $UserKey,
        "--ops-readiness-lookback-hours",
        $SmokeLookbackHours
    )

    if (-not [string]::IsNullOrWhiteSpace($SmokeJsonOutput)) {
        $SmokeArgs += @("--json-output", $SmokeJsonOutput)
    }

    if ($SmokeStrict) {
        $SmokeArgs += "--fail-on-warning"
    }

    & python @SmokeArgs
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

python -m clients.windows.baizefindb_client
