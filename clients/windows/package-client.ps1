param(
    [string]$Name = "BaizeFinDB-Windows-Client",
    [string]$DistPath,
    [string]$WorkPath,
    [switch]$Clean
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

& python @PyInstallerArgs
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "Packaged onedir output: $(Join-Path $DistPath $Name)"
