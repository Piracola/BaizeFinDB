param(
    [string]$Name = "BaizeFinDB-Windows-Client",
    [string]$AppVersion = "0.1.0-preview",
    [string]$SourceDir,
    [string]$OutputDir,
    [string]$SetupBaseName = "BaizeFinDB-Windows-Client-Setup",
    [string]$InnoScriptPath,
    [switch]$DryRun,
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..\..")

if ([string]::IsNullOrWhiteSpace($SourceDir)) {
    $SourceDir = Join-Path $ScriptDir (Join-Path "dist" $Name)
}

if ([string]::IsNullOrWhiteSpace($OutputDir)) {
    $OutputDir = Join-Path $ScriptDir (Join-Path "dist" "installer")
}

if ([string]::IsNullOrWhiteSpace($InnoScriptPath)) {
    $InnoScriptPath = Join-Path $ScriptDir (Join-Path "installer" "BaizeFinDB-Windows-Client.iss")
}

Set-Location $RepoRoot

function Get-AbsolutePathText {
    param([string]$Path)

    if ([string]::IsNullOrWhiteSpace($Path)) {
        return $null
    }

    return [System.IO.Path]::GetFullPath($Path)
}

function Format-CommandArgument {
    param([string]$Argument)

    if ($Argument -match '^[A-Za-z0-9_./:=\\-]+$') {
        return $Argument
    }

    return "'" + ($Argument -replace "'", "''") + "'"
}

function Resolve-InnoSetupCompiler {
    $Command = Get-Command "iscc" -ErrorAction SilentlyContinue
    if ($null -ne $Command) {
        return $Command.Source
    }

    $KnownPaths = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
    )

    foreach ($Path in $KnownPaths) {
        if ((-not [string]::IsNullOrWhiteSpace($Path)) -and (Test-Path $Path)) {
            return $Path
        }
    }

    return $null
}

$AbsoluteSourceDir = Get-AbsolutePathText $SourceDir
$AbsoluteOutputDir = Get-AbsolutePathText $OutputDir
$AbsoluteInnoScriptPath = Get-AbsolutePathText $InnoScriptPath
$ExpectedClientExe = Join-Path $AbsoluteSourceDir "$Name.exe"
$ExpectedInstaller = Join-Path $AbsoluteOutputDir "$SetupBaseName.exe"

$IsccPath = Resolve-InnoSetupCompiler
if ($DryRun -and [string]::IsNullOrWhiteSpace($IsccPath)) {
    $IsccPath = "ISCC.exe"
}

$InnoArgs = @(
    "/DAppVersion=$AppVersion",
    "/DSourceDir=$AbsoluteSourceDir",
    "/DOutputDir=$AbsoluteOutputDir",
    "/DSetupBaseName=$SetupBaseName",
    $AbsoluteInnoScriptPath
)

if ($DryRun) {
    $Command = (Format-CommandArgument $IsccPath) + " " + (($InnoArgs | ForEach-Object { Format-CommandArgument $_ }) -join " ")
    Write-Output $Command
    exit 0
}

if ([string]::IsNullOrWhiteSpace($IsccPath)) {
    Write-Error "Inno Setup compiler is not installed. Install Inno Setup 6 or run: choco install innosetup --no-progress --yes"
    exit 1
}

if (-not (Test-Path $AbsoluteInnoScriptPath)) {
    Write-Error "Inno Setup script was not found: $AbsoluteInnoScriptPath"
    exit 1
}

if ($CheckOnly) {
    Write-Output "Inno Setup compiler is available: $IsccPath"
    Write-Output "Inno Setup script is available: $AbsoluteInnoScriptPath"
    exit 0
}

if (-not (Test-Path $ExpectedClientExe)) {
    Write-Error "Packaged client exe was not found: $ExpectedClientExe. Build the PyInstaller onedir client first."
    exit 1
}

New-Item -ItemType Directory -Force -Path $AbsoluteOutputDir | Out-Null

& $IsccPath @InnoArgs
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

if (-not (Test-Path $ExpectedInstaller)) {
    Write-Error "Installer output was not found after Inno Setup completed: $ExpectedInstaller"
    exit 1
}

Write-Host "Packaged installer output: $ExpectedInstaller"
