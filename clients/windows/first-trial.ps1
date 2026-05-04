param(
    [string]$ServerUrl = "http://127.0.0.1:8000",
    [string]$UserKey = "default",
    [ValidateRange(1, 168)]
    [int]$SmokeLookbackHours = 24,
    [string]$SmokeJsonOutput,
    [string]$SmokeCompactJsonOutput,
    [switch]$SmokeStrict,
    [switch]$SmokeOnly,
    [switch]$StartDockerBackend,
    [ValidateRange(1, 3600)]
    [int]$BackendHealthTimeoutSeconds = 120,
    [ValidateRange(1, 60)]
    [int]$BackendHealthPollIntervalSeconds = 2
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..\..")
$RunClientPath = Join-Path $ScriptDir "run-client.ps1"

function Invoke-BackendCompose {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$ComposeArgs
    )

    & docker compose -f docker-compose.yml -f docker-compose.server.yml @ComposeArgs
    if ($LASTEXITCODE -ne 0) {
        [Console]::Error.WriteLine("Docker compose command failed with exit code $LASTEXITCODE`: docker compose -f docker-compose.yml -f docker-compose.server.yml $($ComposeArgs -join ' ')")
        exit $LASTEXITCODE
    }
}

function Join-HealthUrl {
    param(
        [Parameter(Mandatory = $true)]
        [string]$BaseUrl
    )

    return "$($BaseUrl.TrimEnd('/'))/health"
}

function Wait-BackendHealth {
    param(
        [Parameter(Mandatory = $true)]
        [string]$HealthUrl,
        [Parameter(Mandatory = $true)]
        [int]$TimeoutSeconds,
        [Parameter(Mandatory = $true)]
        [int]$PollIntervalSeconds
    )

    $Deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -le $Deadline) {
        try {
            $Response = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec $PollIntervalSeconds
            if ($Response.StatusCode -ge 200 -and $Response.StatusCode -lt 300) {
                return
            }
        }
        catch {
            $LastError = $_.Exception.Message
        }

        if ((Get-Date) -lt $Deadline) {
            Start-Sleep -Seconds $PollIntervalSeconds
        }
    }

    if ([string]::IsNullOrWhiteSpace($LastError)) {
        $LastError = "health endpoint did not return HTTP 2xx"
    }
    Write-Error "Timed out after $TimeoutSeconds seconds waiting for $HealthUrl ($LastError)"
    exit 1
}

if ($StartDockerBackend) {
    Set-Location $RepoRoot
    Invoke-BackendCompose -ComposeArgs @("up", "-d", "postgres", "redis")
    Invoke-BackendCompose -ComposeArgs @("run", "--rm", "api", "alembic", "upgrade", "head")
    Invoke-BackendCompose -ComposeArgs @("up", "-d", "api", "worker", "beat")
    Wait-BackendHealth -HealthUrl (Join-HealthUrl -BaseUrl $ServerUrl) -TimeoutSeconds $BackendHealthTimeoutSeconds -PollIntervalSeconds $BackendHealthPollIntervalSeconds
}

$RunParams = @{
    ServerUrl = $ServerUrl
    UserKey = $UserKey
    SmokeCheck = $true
    SmokeLookbackHours = $SmokeLookbackHours
}

if (-not [string]::IsNullOrWhiteSpace($SmokeJsonOutput)) {
    $RunParams.SmokeJsonOutput = $SmokeJsonOutput
}

if (-not [string]::IsNullOrWhiteSpace($SmokeCompactJsonOutput)) {
    $RunParams.SmokeCompactJsonOutput = $SmokeCompactJsonOutput
}

if ($SmokeStrict) {
    $RunParams.SmokeStrict = $true
}

if ($SmokeOnly) {
    $RunParams.SmokeOnly = $true
}

& $RunClientPath @RunParams
exit $LASTEXITCODE
