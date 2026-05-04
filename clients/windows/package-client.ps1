param(
    [string]$Name = "BaizeFinDB-Windows-Client",
    [string]$DistPath,
    [string]$WorkPath,
    [switch]$Clean,
    [switch]$DryRun,
    [switch]$CheckOnly,
    [string]$CheckJsonOutput,
    [switch]$SkipPreflight
)

$ErrorActionPreference = "Stop"

if ((-not [string]::IsNullOrWhiteSpace($CheckJsonOutput)) -and (-not $CheckOnly)) {
    Write-Error "-CheckJsonOutput can only be used with -CheckOnly."
    exit 2
}

if ($CheckOnly -and $SkipPreflight) {
    Write-Error "-CheckOnly cannot be used with -SkipPreflight because check-only mode must run the packaging preflight."
    exit 2
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..\..")

if ([string]::IsNullOrWhiteSpace($DistPath)) {
    $DistPath = Join-Path $ScriptDir "dist"
}

if ([string]::IsNullOrWhiteSpace($WorkPath)) {
    $WorkPath = Join-Path $ScriptDir "build"
}

$SpecPath = Join-Path $WorkPath "spec"
$LauncherPath = Join-Path $WorkPath "baizefindb_client_launcher.py"

Set-Location $RepoRoot

function Get-AbsolutePathText {
    param([string]$Path)

    if ([string]::IsNullOrWhiteSpace($Path)) {
        return $null
    }

    return [System.IO.Path]::GetFullPath($Path)
}

function New-CheckEvidence {
    param(
        [string]$Status,
        [string]$EvidencePath
    )

    return [ordered]@{
        schema_version = 1
        status = $Status
        checks = [ordered]@{
            python = [ordered]@{
                status = "not_run"
                required_version = "3.12"
                version = $null
            }
            tkinter = [ordered]@{
                status = "not_run"
                available = $false
            }
            gui_module = [ordered]@{
                status = "not_run"
                module = "clients.windows.baizefindb_client"
                available = $false
            }
            pyinstaller = [ordered]@{
                status = "not_run"
                available = $false
            }
        }
        command = [ordered]@{
            script = "clients/windows/package-client.ps1"
            mode = "check-only"
            name = $Name
            clean = [bool]$Clean
            target_module = "clients.windows.baizefindb_client"
            pyinstaller_module = "PyInstaller"
        }
        output_paths = [ordered]@{
            dist_path = Get-AbsolutePathText $DistPath
            work_path = Get-AbsolutePathText $WorkPath
            spec_path = Get-AbsolutePathText $SpecPath
            check_json_output = Get-AbsolutePathText $EvidencePath
        }
    }
}

function Set-CheckResult {
    param(
        [System.Collections.IDictionary]$Evidence,
        [string]$Name,
        [string]$Status,
        [hashtable]$Fields = @{}
    )

    $Evidence.checks[$Name].status = $Status
    foreach ($Key in $Fields.Keys) {
        $Evidence.checks[$Name][$Key] = $Fields[$Key]
    }
}

function Write-CheckEvidence {
    param(
        [System.Collections.IDictionary]$Evidence,
        [string]$OutputPath
    )

    if ([string]::IsNullOrWhiteSpace($OutputPath)) {
        return
    }

    $AbsoluteOutputPath = Get-AbsolutePathText $OutputPath
    $OutputDirectory = Split-Path -Parent $AbsoluteOutputPath
    if (-not [string]::IsNullOrWhiteSpace($OutputDirectory)) {
        New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
    }

    $Evidence.output_paths.check_json_output = $AbsoluteOutputPath
    $Utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText(
        $AbsoluteOutputPath,
        ($Evidence | ConvertTo-Json -Depth 6),
        $Utf8NoBom
    )
}

$CheckEvidence = $null
if ($CheckOnly) {
    $CheckEvidence = New-CheckEvidence -Status "running" -EvidencePath $CheckJsonOutput
}

$PyInstallerArgs = @(
    "-m",
    "PyInstaller",
    "--noconfirm",
    "--onedir",
    "--windowed",
    "--name",
    $Name,
    "--distpath",
    $DistPath,
    "--workpath",
    $WorkPath,
    "--specpath",
    $SpecPath,
    "--paths",
    $RepoRoot,
    $LauncherPath
)

if ($Clean) {
    $PyInstallerArgs = @("-m", "PyInstaller", "--clean") + $PyInstallerArgs[2..($PyInstallerArgs.Count - 1)]
}

function Format-CommandArgument {
    param([string]$Argument)

    if ($Argument -match '^[A-Za-z0-9_./:=\\-]+$') {
        return $Argument
    }

    return "'" + ($Argument -replace "'", "''") + "'"
}

if ($DryRun) {
    $Command = "python " + (($PyInstallerArgs | ForEach-Object { Format-CommandArgument $_ }) -join " ")
    Write-Output $Command
    exit 0
}

if (-not $SkipPreflight) {
    $PreflightReportPath = [System.IO.Path]::GetTempFileName()
    $PreflightCode = @'
import importlib
import importlib.util
import json
import pathlib
import sys

repo_root = pathlib.Path(sys.argv[1]).resolve()
report_path = pathlib.Path(sys.argv[2])
report = {
    "python": {
        "status": "pass",
        "required_version": "3.12",
        "version": sys.version.split()[0],
    },
    "tkinter": {"status": "not_run", "available": False},
    "gui_module": {
        "status": "not_run",
        "module": "clients.windows.baizefindb_client",
        "available": False,
    },
}

if sys.version_info[:2] != (3, 12):
    report["python"]["status"] = "fail"
else:
    try:
        importlib.import_module("tkinter")
        report["tkinter"] = {"status": "pass", "available": True}
    except Exception as exc:
        report["tkinter"] = {
            "status": "fail",
            "available": False,
            "error_type": type(exc).__name__,
        }

sys.path.insert(0, str(repo_root))
if report["tkinter"]["status"] == "pass":
    try:
        if importlib.util.find_spec("clients.windows.baizefindb_client") is None:
            report["gui_module"]["status"] = "fail"
        else:
            report["gui_module"]["status"] = "pass"
            report["gui_module"]["available"] = True
    except Exception as exc:
        report["gui_module"] = {
            "status": "fail",
            "module": "clients.windows.baizefindb_client",
            "available": False,
            "error_type": type(exc).__name__,
        }

report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
sys.exit(0 if all(item["status"] == "pass" for item in report.values()) else 1)
'@
    $PreviousPreflightReportEnv = $env:BAIZE_PACKAGE_PREFLIGHT_REPORT
    $env:BAIZE_PACKAGE_PREFLIGHT_REPORT = $PreflightReportPath
    try {
        & python -c $PreflightCode $RepoRoot $PreflightReportPath
        $PreflightExitCode = $LASTEXITCODE
    }
    finally {
        if ($null -eq $PreviousPreflightReportEnv) {
            Remove-Item Env:\BAIZE_PACKAGE_PREFLIGHT_REPORT -ErrorAction SilentlyContinue
        }
        else {
            $env:BAIZE_PACKAGE_PREFLIGHT_REPORT = $PreviousPreflightReportEnv
        }
    }

    if (($null -ne $CheckEvidence) -and (Test-Path $PreflightReportPath)) {
        $PreflightReport = Get-Content $PreflightReportPath -Raw | ConvertFrom-Json
        Set-CheckResult $CheckEvidence "python" $PreflightReport.python.status @{
            required_version = $PreflightReport.python.required_version
            version = $PreflightReport.python.version
        }
        Set-CheckResult $CheckEvidence "tkinter" $PreflightReport.tkinter.status @{
            available = [bool]$PreflightReport.tkinter.available
        }
        Set-CheckResult $CheckEvidence "gui_module" $PreflightReport.gui_module.status @{
            module = $PreflightReport.gui_module.module
            available = [bool]$PreflightReport.gui_module.available
        }
    }

    Remove-Item -Force -ErrorAction SilentlyContinue $PreflightReportPath

    if ($LASTEXITCODE -ne 0) {
        if ($null -ne $CheckEvidence) {
            $CheckEvidence.status = "fail"
            Write-CheckEvidence $CheckEvidence $CheckJsonOutput
        }
        Write-Error "Packaging preflight failed."
        exit $PreflightExitCode
    }
}

$PyInstallerCheck = @(
    "-c",
    "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('PyInstaller') else 1)"
)
& python @PyInstallerCheck
if ($LASTEXITCODE -ne 0) {
    if ($null -ne $CheckEvidence) {
        $CheckEvidence.status = "fail"
        Set-CheckResult $CheckEvidence "pyinstaller" "fail" @{ available = $false }
        Write-CheckEvidence $CheckEvidence $CheckJsonOutput
    }
    Write-Error "PyInstaller is not installed. Sync the optional packaging group first: uv sync --group package"
    exit $LASTEXITCODE
}

if ($CheckOnly) {
    $CheckEvidence.status = "ok"
    Set-CheckResult $CheckEvidence "pyinstaller" "pass" @{ available = $true }
    Write-CheckEvidence $CheckEvidence $CheckJsonOutput
    Write-Output "Packaging prerequisites are available."
    exit 0
}

New-Item -ItemType Directory -Force -Path $WorkPath, $DistPath, $SpecPath | Out-Null

$LauncherSource = @'
import runpy

runpy.run_module("clients.windows.baizefindb_client", run_name="__main__")
'@

$Utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($LauncherPath, $LauncherSource, $Utf8NoBom)

& python @PyInstallerArgs
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "Packaged onedir output: $(Join-Path $DistPath $Name)"
