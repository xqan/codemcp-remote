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

$exeSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $exePath).Hash.ToLowerInvariant()
$sha256File = Join-Path $appDir "SHA256SUMS.txt"
("{0}  codemcp-remote.exe" -f $exeSha256) | Set-Content -LiteralPath $sha256File -Encoding ascii

if (-not $SkipSmoke) {
    & $exePath --version
    if ($LASTEXITCODE -ne 0) {
        throw "frozen Bridge version check failed with exit code $LASTEXITCODE"
    }
    & $exePath check
    if ($LASTEXITCODE -ne 0) {
        throw "frozen Bridge check failed with exit code $LASTEXITCODE"
    }

    $workerSmoke = Join-Path $repositoryRoot "tests\integration\executable_smoke.py"
    & $uv.Source run --project $bridgeProject python $workerSmoke $exePath $repositoryRoot
    if ($LASTEXITCODE -ne 0) {
        throw "frozen worker mutation smoke failed with exit code $LASTEXITCODE"
    }
}

[ordered]@{
    status = "ok"
    pyinstaller_version = $pyInstallerVersion
    executable = $exePath
    distribution_dir = $appDir
    sha256 = $exeSha256
    sha256_file = $sha256File
    smoke = if ($SkipSmoke) { "skipped" } else { "passed" }
} | ConvertTo-Json -Depth 4
