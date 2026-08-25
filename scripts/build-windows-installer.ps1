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
$installerWorkDir = Join-Path $repositoryRoot ".local\installer-work"
$appDistDir = Join-Path $installerWorkDir "exe-dist"
$appWorkDir = Join-Path $installerWorkDir "pyinstaller"
$appDir = Join-Path $appDistDir "codemcp-remote"
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
    Remove-Item -LiteralPath $installerWorkDir -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $installerWorkDir | Out-Null
    & pwsh -NoLogo -NoProfile -NonInteractive `
        -File (Join-Path $repositoryRoot "scripts\build-windows-exe.ps1") `
        -DistDir $appDistDir `
        -WorkDir $appWorkDir
    if ($LASTEXITCODE -ne 0) {
        throw "Phase 3 executable staging build failed with exit code $LASTEXITCODE"
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

function Invoke-GuiProcessAndWait {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [string[]]$ArgumentList
    )

    $process = Start-Process -FilePath $FilePath -ArgumentList $ArgumentList -Wait -PassThru
    return $process.ExitCode
}

$smokeStatus = "skipped"
if (-not $SkipSmoke) {
    $uninstallKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{A26B4BA3-1D96-4F1A-95C4-9984C941A1E1}_is1"
    $smokeRoot = Join-Path $repositoryRoot ".local\installer-smoke"
    $installDir = Join-Path $smokeRoot "installed"
    $runtimeDir = Join-Path $smokeRoot "runtime"

    if (Test-Path -LiteralPath $uninstallKey) {
        $existingInstall = (Get-ItemProperty -LiteralPath $uninstallKey -ErrorAction Stop).InstallLocation
        $existingFullPath = if ([string]::IsNullOrWhiteSpace($existingInstall)) {
            ""
        } else {
            [System.IO.Path]::GetFullPath($existingInstall)
        }
        $smokePrefix = [System.IO.Path]::GetFullPath($smokeRoot).TrimEnd("\") + "\"
        if (-not $existingFullPath.StartsWith($smokePrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "installer smoke requires no existing installed codemcp-remote copy; use a clean host or -SkipSmoke"
        }
        Write-Host "Removing stale isolated installer smoke state: $existingFullPath"
        Remove-Item -LiteralPath $uninstallKey -Recurse -Force
        if (Test-Path -LiteralPath $existingFullPath) {
            Remove-Item -LiteralPath $existingFullPath -Recurse -Force
        }
        if (Test-Path -LiteralPath $uninstallKey) {
            throw "failed to remove stale installer smoke registration: $uninstallKey"
        }
    }

    Remove-Item -LiteralPath $smokeRoot -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $smokeRoot | Out-Null
    $setupLog = Join-Path $smokeRoot "setup.log"

    try {
        $setupExit = Invoke-GuiProcessAndWait `
            -FilePath $setupPath `
            -ArgumentList @(
                "/VERYSILENT",
                "/SUPPRESSMSGBOXES",
                "/NORESTART",
                "/NOSTOPLIFECYCLE",
                ('/DIR="{0}"' -f $installDir),
                ('/LOG="{0}"' -f $setupLog),
                "/MERGETASKS=!addtopath"
            )
        if ($setupExit -ne 0) {
            throw "silent installer smoke failed with exit code $setupExit; log=$setupLog"
        }
        if (-not (Test-Path -LiteralPath $uninstallKey)) {
            throw "installer smoke did not create the expected uninstall registration; log=$setupLog"
        }

        $installedLocation = (Get-ItemProperty -LiteralPath $uninstallKey -ErrorAction Stop).InstallLocation
        if ([string]::IsNullOrWhiteSpace($installedLocation)) {
            throw "installer smoke uninstall registration has no InstallLocation; log=$setupLog"
        }
        $installedLocation = [System.IO.Path]::GetFullPath($installedLocation)
        $expectedLocation = [System.IO.Path]::GetFullPath($installDir)
        if ($installedLocation.TrimEnd("\") -ne $expectedLocation.TrimEnd("\")) {
            $unexpectedUninstallers = @(
                Get-ChildItem -LiteralPath $installedLocation -File -Filter "unins*.exe" -ErrorAction SilentlyContinue
            )
            if ($unexpectedUninstallers.Count -eq 1) {
                $null = Invoke-GuiProcessAndWait `
                    -FilePath $unexpectedUninstallers[0].FullName `
                    -ArgumentList @(
                        "/VERYSILENT",
                        "/SUPPRESSMSGBOXES",
                        "/NORESTART",
                        "/NOSTOPLIFECYCLE"
                    )
            }
            throw "installer smoke installed to unexpected location: $installedLocation; expected: $expectedLocation; log=$setupLog"
        }

        $installedMain = Join-Path $installedLocation "codemcp-remote.exe"
        $installedTunnel = Join-Path $installedLocation "tunnel-client.exe"
        $requiredFiles = @(
            $installedMain,
            $installedTunnel,
            (Join-Path $installedLocation "LICENSE"),
            (Join-Path $installedLocation "THIRD_PARTY_NOTICES.txt"),
            (Join-Path $installedLocation "THIRD_PARTY\tunnel-client\LICENSE")
        )
        foreach ($required in $requiredFiles) {
            if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
                throw "installer smoke missing required file: $required; log=$setupLog"
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
            Get-ChildItem -LiteralPath $installedLocation -File -Filter "unins*.exe"
        )
        if ($uninstallers.Count -ne 1) {
            throw "expected exactly one Inno Setup uninstaller"
        }
        $uninstallExit = Invoke-GuiProcessAndWait `
            -FilePath $uninstallers[0].FullName `
            -ArgumentList @(
                "/VERYSILENT",
                "/SUPPRESSMSGBOXES",
                "/NORESTART",
                "/NOSTOPLIFECYCLE"
            )
        if ($uninstallExit -ne 0) {
            throw "silent uninstaller smoke failed with exit code $uninstallExit"
        }
        if (Test-Path -LiteralPath $installedMain -PathType Leaf) {
            throw "silent uninstall left codemcp-remote.exe behind"
        }
        $smokeStatus = "passed"
    } finally {
        if ($smokeStatus -eq "passed") {
            Remove-Item -LiteralPath $smokeRoot -Recurse -Force -ErrorAction SilentlyContinue
        } else {
            Write-Warning "Installer smoke artifacts were preserved for diagnosis: $smokeRoot"
        }
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
