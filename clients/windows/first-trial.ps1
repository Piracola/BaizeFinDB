param(
    [string]$ServerUrl = "http://127.0.0.1:8000",
    [string]$UserKey = "default",
    [ValidateRange(1, 168)]
    [int]$SmokeLookbackHours = 24,
    [string]$SmokeJsonOutput,
    [switch]$SmokeStrict
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RunClientPath = Join-Path $ScriptDir "run-client.ps1"

$RunParams = @{
    ServerUrl = $ServerUrl
    UserKey = $UserKey
    SmokeCheck = $true
    SmokeLookbackHours = $SmokeLookbackHours
}

if (-not [string]::IsNullOrWhiteSpace($SmokeJsonOutput)) {
    $RunParams.SmokeJsonOutput = $SmokeJsonOutput
}

if ($SmokeStrict) {
    $RunParams.SmokeStrict = $true
}

& $RunClientPath @RunParams
exit $LASTEXITCODE
