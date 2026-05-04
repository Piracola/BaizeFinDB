param(
    [string]$Name = "BaizeFinDB-Windows-Client",
    [string]$DistPath,
    [string]$WorkPath,
    [switch]$Clean,
    [switch]$DryRun,
    [switch]$SkipPreflight
)

$ErrorActionPreference = "Stop"

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
    $PreflightCode = @'
import importlib
import importlib.util
import pathlib
import sys

repo_root = pathlib.Path(sys.argv[1]).resolve()
if sys.version_info[:2] != (3, 12):
    raise SystemExit(f"Python 3.12 is required for packaging; found {sys.version.split()[0]}")

importlib.import_module("tkinter")
sys.path.insert(0, str(repo_root))
if importlib.util.find_spec("clients.windows.baizefindb_client") is None:
    raise SystemExit("Cannot resolve clients.windows.baizefindb_client from repo path")
'@
    & python -c $PreflightCode $RepoRoot
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

$PyInstallerCheck = @(
    "-c",
    "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('PyInstaller') else 1)"
)
& python @PyInstallerCheck
if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller is not installed. Install it only for packaging, for example: uv pip install pyinstaller"
    exit $LASTEXITCODE
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
