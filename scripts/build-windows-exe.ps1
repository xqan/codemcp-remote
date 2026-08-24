[CmdletBinding()]
param(
    [string]$DistDir,
    [string]$WorkDir,
    [switch]$SkipSmoke
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($env:OS -ne "Windows_NT") {
    throw "Windows EXE builds must run on Windows"
}

$repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$bridgeProject = Join-Path $repositoryRoot "bridge"
$bridgeSrc = Join-Path $bridgeProject "src"
$entrypoint = Join-Path $repositoryRoot "scripts\windows_entrypoint.py"
$pyInstallerVersion = "6.22.2"

if ([string]::IsNullOrWhiteSpace($DistDir)) {
    $DistDir = Join-Path $repositoryRoot ".local\dist"
}
if ([string]::IsNullOrWhiteSpace($WorkDir)) {
    $WorkDir = Join-Path $repositoryRoot ".local\pyinstaller"
}

$uv = Get-Command uv -ErrorAction SilentlyContinue
if ($null -eq $uv) {
    throw "uv was not found on PATH"
}

New-Item -ItemType Directory -Force -Path $DistDir | Out-Null
New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null

$pyInstallerArgs = @(
    "run",
    "--project", $bridgeProject,
    "--with", ("pyinstaller=={0}" -f $pyInstallerVersion),
    "pyinstaller",
    "--noconfirm",
    "--clean",
    "--onedir",
    "--console",
    "--name", "codemcp-remote",
    "--paths", $bridgeSrc,
    "--collect-submodules", "codemcp",
    "--copy-metadata", "codemcp",
    "--distpath", $DistDir,
    "--workpath", $WorkDir,
    "--specpath", $WorkDir,
    $entrypoint
)

& $uv.Source @pyInstallerArgs
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed with exit code $LASTEXITCODE"
}

$appDir = Join-Path $DistDir "codemcp-remote"
$exePath = Join-Path $appDir "codemcp-remote.exe"
if (-not (Test-Path -LiteralPath $exePath -PathType Leaf)) {
    throw "expected executable was not created: $exePath"
}

$configDir = Join-Path $appDir "config"
New-Item -ItemType Directory -Force -Path $configDir | Out-Null
Copy-Item -LiteralPath (Join-Path $repositoryRoot "config\bridge.example.toml") -Destination $configDir -Force
Copy-Item -LiteralPath (Join-Path $repositoryRoot "config\projects.example.toml") -Destination $configDir -Force
Copy-Item -LiteralPath (Join-Path $repositoryRoot "LICENSE") -Destination $appDir -Force

if (-not $SkipSmoke) {
    & $exePath check `
        --bridge-config (Join-Path $repositoryRoot "config\bridge.example.toml") `
        --projects-config (Join-Path $repositoryRoot "config\projects.toml")
    if ($LASTEXITCODE -ne 0) {
        throw "frozen Bridge check failed with exit code $LASTEXITCODE"
    }
}

[ordered]@{
    status = "ok"
    pyinstaller_version = $pyInstallerVersion
    executable = $exePath
    distribution_dir = $appDir
    smoke = if ($SkipSmoke) { "skipped" } else { "passed" }
} | ConvertTo-Json -Depth 4
