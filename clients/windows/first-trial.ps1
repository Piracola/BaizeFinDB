param(
    [string]$ServerUrl = "http://127.0.0.1:8000",
    [string]$UserKey = "default",
    [ValidateRange(1, 168)]
    [int]$SmokeLookbackHours = 24,
    [string]$SmokeJsonOutput,
    [string]$SmokeCompactJsonOutput,
    [string]$DeployCheckJsonOutput,
    [string]$DeployCheckBackupJsonOutput,
    [string]$DatabaseInventoryJsonOutput,
    [string]$SeedDemoDataJsonOutput,
    [switch]$DeployCheckServerComposeContract,
    [switch]$DeployCheckM5Smoke,
    [switch]$DeployCheckRequireRadarAnalysisSample,
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

function Invoke-DeployCheck {
    param(
        [Parameter(Mandatory = $true)]
        [string]$JsonOutput,
        [string]$BackupJsonOutput,
        [switch]$IncludeServerComposeContract,
        [switch]$IncludeM5Smoke,
        [switch]$RequireRadarAnalysisSample
    )

    $DeployCheckArgs = @(
        "infra/scripts/server_deploy_check.py",
        "--check-containers",
        "--check-api",
        "--json-output",
        $JsonOutput
    )

    if ($IncludeServerComposeContract) {
        $DeployCheckArgs += "--check-server-compose-contract"
    }

    if ($IncludeM5Smoke) {
        $DeployCheckArgs += "--check-m5-smoke"
    }

    if ($RequireRadarAnalysisSample) {
        $DeployCheckArgs += "--require-radar-signal-analysis-sample"
    }

    if (-not [string]::IsNullOrWhiteSpace($BackupJsonOutput)) {
        $DeployCheckArgs += @("--check-backup", "--backup-check-json-output", $BackupJsonOutput)
    }

    & python @DeployCheckArgs
    if ($LASTEXITCODE -ne 0) {
        [Console]::Error.WriteLine("Server deploy preflight failed with exit code $LASTEXITCODE")
        exit $LASTEXITCODE
    }
}

function Invoke-DatabaseInventory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$JsonOutput
    )

    $InventoryArgs = @(
        "infra/scripts/database_inventory.py",
        "--json-output",
        $JsonOutput
    )

    & python @InventoryArgs
    if ($LASTEXITCODE -ne 0) {
        [Console]::Error.WriteLine("Database inventory failed with exit code $LASTEXITCODE")
        exit $LASTEXITCODE
    }
}

function Invoke-DemoSeed {
    param(
        [Parameter(Mandatory = $true)]
        [string]$JsonOutput
    )

    $SeedArgs = @(
        "infra/scripts/seed_demo_data.py",
        "--json-output",
        $JsonOutput
    )

    & python @SeedArgs
    if ($LASTEXITCODE -ne 0) {
        [Console]::Error.WriteLine("Demo seed failed with exit code $LASTEXITCODE")
        exit $LASTEXITCODE
    }
}

if (-not [string]::IsNullOrWhiteSpace($DeployCheckJsonOutput) -and -not $StartDockerBackend) {
    [Console]::Error.WriteLine("-DeployCheckJsonOutput requires -StartDockerBackend")
    exit 2
}

if (-not [string]::IsNullOrWhiteSpace($SeedDemoDataJsonOutput) -and -not $StartDockerBackend) {
    [Console]::Error.WriteLine("-SeedDemoDataJsonOutput requires -StartDockerBackend")
    exit 2
}

if (-not [string]::IsNullOrWhiteSpace($DatabaseInventoryJsonOutput) -and -not $StartDockerBackend) {
    [Console]::Error.WriteLine("-DatabaseInventoryJsonOutput requires -StartDockerBackend")
    exit 2
}

if ($DeployCheckM5Smoke -and [string]::IsNullOrWhiteSpace($DeployCheckJsonOutput)) {
    [Console]::Error.WriteLine("-DeployCheckM5Smoke requires -DeployCheckJsonOutput")
    exit 2
}

if ($DeployCheckRequireRadarAnalysisSample -and -not $DeployCheckM5Smoke) {
    [Console]::Error.WriteLine("-DeployCheckRequireRadarAnalysisSample requires -DeployCheckM5Smoke")
    exit 2
}

if ($DeployCheckServerComposeContract -and [string]::IsNullOrWhiteSpace($DeployCheckJsonOutput)) {
    [Console]::Error.WriteLine("-DeployCheckServerComposeContract requires -DeployCheckJsonOutput")
    exit 2
}

if (-not [string]::IsNullOrWhiteSpace($DeployCheckBackupJsonOutput) -and [string]::IsNullOrWhiteSpace($DeployCheckJsonOutput)) {
    [Console]::Error.WriteLine("-DeployCheckBackupJsonOutput requires -DeployCheckJsonOutput")
    exit 2
}

if ($StartDockerBackend) {
    Set-Location $RepoRoot
    Invoke-BackendCompose -ComposeArgs @("build", "api")
    Invoke-BackendCompose -ComposeArgs @("up", "-d", "postgres", "redis")
    Invoke-BackendCompose -ComposeArgs @("run", "--rm", "api", "alembic", "upgrade", "head")
    Invoke-BackendCompose -ComposeArgs @("up", "-d", "api", "worker", "beat")
    Wait-BackendHealth -HealthUrl (Join-HealthUrl -BaseUrl $ServerUrl) -TimeoutSeconds $BackendHealthTimeoutSeconds -PollIntervalSeconds $BackendHealthPollIntervalSeconds

    if (-not [string]::IsNullOrWhiteSpace($SeedDemoDataJsonOutput)) {
        Invoke-DemoSeed -JsonOutput $SeedDemoDataJsonOutput
    }

    if (-not [string]::IsNullOrWhiteSpace($DatabaseInventoryJsonOutput)) {
        Invoke-DatabaseInventory -JsonOutput $DatabaseInventoryJsonOutput
    }

    if (-not [string]::IsNullOrWhiteSpace($DeployCheckJsonOutput)) {
        Invoke-DeployCheck `
            -JsonOutput $DeployCheckJsonOutput `
            -BackupJsonOutput $DeployCheckBackupJsonOutput `
            -IncludeServerComposeContract:$DeployCheckServerComposeContract `
            -IncludeM5Smoke:$DeployCheckM5Smoke `
            -RequireRadarAnalysisSample:$DeployCheckRequireRadarAnalysisSample
    }
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
