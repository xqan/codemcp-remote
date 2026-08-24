[CmdletBinding()]
param(
    [string]$OutputDir,
    [string]$ISCCPath,
    [string]$AppVersion = "0.1.0",
    [string]$TunnelClientVersion = "v0.0.12",
    [switch]$SkipAppBuild,
    [switch]$SkipSmoke,
    [switch]$ForceTunnelDownload
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($env:OS -ne "Windows_NT") {
    throw "Windows installer builds must run on Windows"
}

$repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$appDir = Join-Path $repositoryRoot ".local\dist\codemcp-remote"
$mainExe = Join-Path $appDir "codemcp-remote.exe"
$installerScript = Join-Path $repositoryRoot "scripts\codemcp-remote.iss"

if ([string]::IsNullOrWhiteSpace($OutputDir)) {
    $OutputDir = Join-Path $repositoryRoot ".local\installer-dist"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)

function Resolve-ISCC {
    param([string]$RequestedPath)

    if (-not [string]::IsNullOrWhiteSpace($RequestedPath)) {
        $resolved = [System.IO.Path]::GetFullPath($RequestedPath)
        if (-not (Test-Path -LiteralPath $resolved -PathType Leaf)) {
            throw "ISCC.exe was not found: $resolved"
        }
        return $resolved
    }

    foreach ($name in @("ISCC.exe", "ISCC")) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($null -ne $command) {
            return $command.Source
        }
    }

    $candidates = @()
    if (-not [string]::IsNullOrWhiteSpace($env:ProgramFiles)) {
        $candidates += Join-Path $env:ProgramFiles "Inno Setup 7\ISCC.exe"
    }
    if (-not [string]::IsNullOrWhiteSpace(${env:ProgramFiles(x86)})) {
        $candidates += Join-Path ${env:ProgramFiles(x86)} "Inno Setup 7\ISCC.exe"
    }
    if (-not [string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        $candidates += Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 7\ISCC.exe"
    }
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return $candidate
        }
    }

    throw @"
Inno Setup 7 ISCC.exe was not found.
Install the official 64-bit Inno Setup 7 compiler and rerun this command:
  winget install --id JRSoftware.InnoSetup.7 -e -s winget -i
"@
}

if (-not $SkipAppBuild) {
    & pwsh -NoLogo -NoProfile -NonInteractive -File (Join-Path $repositoryRoot "scripts\build-windows-exe.ps1")
    if ($LASTEXITCODE -ne 0) {
        throw "Phase 3 executable build failed with exit code $LASTEXITCODE"
    }
}
if (-not (Test-Path -LiteralPath $mainExe -PathType Leaf)) {
    throw "packaged codemcp-remote.exe was not found: $mainExe"
}

$prepareArgs = @(
    "-NoLogo",
    "-NoProfile",
    "-NonInteractive",
    "-File", (Join-Path $repositoryRoot "scripts\prepare-tunnel-client.ps1"),
    "-DestinationDir", $appDir,
    "-Version", $TunnelClientVersion
)
if ($ForceTunnelDownload) {
    $prepareArgs += "-ForceDownload"
}
$tunnelJson = (& pwsh @prepareArgs | Out-String).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "tunnel-client preparation failed with exit code $LASTEXITCODE"
}
try {
    $tunnelInfo = $tunnelJson | ConvertFrom-Json
} catch {
    throw "tunnel-client preparation did not return valid JSON: $tunnelJson"
}
if ($tunnelInfo.status -ne "ok") {
    throw "tunnel-client preparation did not report status=ok"
}

$forbiddenPayloadPaths = @(
    (Join-Path $appDir "config\tunnel-profile.local.env"),
    (Join-Path $appDir "secrets\control-plane-api-key.dpapi"),
    (Join-Path $appDir "run\state.json"),
    (Join-Path $appDir "data\bridge.sqlite3"),
    (Join-Path $appDir ".local\bridge.sqlite3"),
    (Join-Path $appDir "bridge.sqlite3")
)
$forbiddenPayload = @(
    $forbiddenPayloadPaths | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf }
)
if ($forbiddenPayload.Count -gt 0) {
    throw "installer payload contains runtime/secret files: $($forbiddenPayload -join ', ')"
}

$iscc = Resolve-ISCC -RequestedPath $ISCCPath
Remove-Item -LiteralPath $OutputDir -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$isccArgs = @(
    "/Qp",
    ("/DSourceDir={0}" -f $appDir),
    ("/DOutputDir={0}" -f $OutputDir),
    ("/DAppVersion={0}" -f $AppVersion),
    $installerScript
)
& $iscc @isccArgs
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup compiler failed with exit code $LASTEXITCODE"
}

$setupPath = Join-Path $OutputDir "codemcp-remote-setup.exe"
if (-not (Test-Path -LiteralPath $setupPath -PathType Leaf)) {
    throw "expected installer was not created: $setupPath"
}

$setupSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $setupPath).Hash.ToLowerInvariant()
$checksumPath = Join-Path $OutputDir "SHA256SUMS.txt"
("{0}  codemcp-remote-setup.exe" -f $setupSha256) |
    Set-Content -LiteralPath $checksumPath -Encoding ascii

$signature = Get-AuthenticodeSignature -LiteralPath $setupPath
$signatureStatus = [string]$signature.Status
if ($signatureStatus -notin @("Valid", "NotSigned")) {
    throw "installer Authenticode status is unsafe: $signatureStatus"
}

$smokeStatus = "skipped"
if (-not $SkipSmoke) {
    $uninstallKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{A26B4BA3-1D96-4F1A-95C4-9984C941A1E1}_is1"
    if (Test-Path -LiteralPath $uninstallKey) {
        throw "installer smoke requires no existing installed codemcp-remote copy; use a clean host or -SkipSmoke"
    }
    $smokeRoot = Join-Path $repositoryRoot ".local\installer-smoke"
    $installDir = Join-Path $smokeRoot "installed"
    $runtimeDir = Join-Path $smokeRoot "runtime"
    Remove-Item -LiteralPath $smokeRoot -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $smokeRoot | Out-Null

    try {
        & $setupPath `
            "/VERYSILENT" `
            "/SUPPRESSMSGBOXES" `
            "/NORESTART" `
            "/NOSTOPLIFECYCLE" `
            ("/DIR={0}" -f $installDir) `
            "/MERGETASKS=!addtopath"
        if ($LASTEXITCODE -ne 0) {
            throw "silent installer smoke failed with exit code $LASTEXITCODE"
        }

        $installedMain = Join-Path $installDir "codemcp-remote.exe"
        $installedTunnel = Join-Path $installDir "tunnel-client.exe"
        $requiredFiles = @(
            $installedMain,
            $installedTunnel,
            (Join-Path $installDir "LICENSE"),
            (Join-Path $installDir "THIRD_PARTY_NOTICES.txt"),
            (Join-Path $installDir "THIRD_PARTY\tunnel-client\LICENSE")
        )
        foreach ($required in $requiredFiles) {
            if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
                throw "installer smoke missing required file: $required"
            }
        }

        & $installedMain --version
        if ($LASTEXITCODE -ne 0) {
            throw "installed codemcp-remote version smoke failed"
        }
        $installedTunnelVersion = (& $installedTunnel --version 2>&1 | Out-String).Trim()
        if ($LASTEXITCODE -ne 0 -or
            $installedTunnelVersion -notmatch [regex]::Escape($TunnelClientVersion.TrimStart("v"))) {
            throw "installed tunnel-client version smoke failed: $installedTunnelVersion"
        }
        & $installedMain status --app-root $runtimeDir
        if ($LASTEXITCODE -ne 0) {
            throw "installed lifecycle status smoke failed"
        }

        $uninstallers = @(
            Get-ChildItem -LiteralPath $installDir -File -Filter "unins*.exe"
        )
        if ($uninstallers.Count -ne 1) {
            throw "expected exactly one Inno Setup uninstaller"
        }
        & $uninstallers[0].FullName `
            "/VERYSILENT" `
            "/SUPPRESSMSGBOXES" `
            "/NORESTART" `
            "/NOSTOPLIFECYCLE"
        if ($LASTEXITCODE -ne 0) {
            throw "silent uninstaller smoke failed with exit code $LASTEXITCODE"
        }
        if (Test-Path -LiteralPath $installedMain -PathType Leaf) {
            throw "silent uninstall left codemcp-remote.exe behind"
        }
        $smokeStatus = "passed"
    } finally {
        Remove-Item -LiteralPath $smokeRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

[ordered]@{
    status = "ok"
    phase = "4"
    app_version = $AppVersion
    installer_builder = "Inno Setup 7"
    iscc = $iscc
    installer = $setupPath
    sha256 = $setupSha256
    sha256_file = $checksumPath
    authenticode_status = $signatureStatus
    tunnel_client_version = $TunnelClientVersion
    tunnel_client_sha256 = [string]$tunnelInfo.executable_sha256
    tunnel_client_license = [string]$tunnelInfo.license
    smoke = $smokeStatus
} | ConvertTo-Json -Depth 4
