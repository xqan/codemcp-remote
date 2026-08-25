[CmdletBinding()]
param(
    [ValidateSet("Prepare", "Start", "Cleanup", "Reset")]
    [string]$Action = "Prepare",
    [string]$InstallerPath,
    [string]$ExpectedInstallerSha256,
    [ValidateSet("cloudflare", "openai-tunnel")]
    [string]$Transport = "cloudflare",
    [string]$PublicUrl,
    [string]$AuthorizationServerIssuer,
    [string]$CanonicalResourceUri,
    [string]$ValidationResourceId = "codemcp-resource",
    [string]$OriginUrl = "http://127.0.0.1:46200/mcp",
    [string]$MetricsAddr = "127.0.0.1:46202",
    [string]$TunnelId,
    [string]$ProjectId = "phase5-clean",
    [string]$ProjectRoot
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$UninstallKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{A26B4BA3-1D96-4F1A-95C4-9984C941A1E1}_is1"
$DefaultProjectRoot = Join-Path $env:LOCALAPPDATA "codemcp-remote-phase5\project"
$Phase5StateFile = Join-Path $env:LOCALAPPDATA "codemcp-remote\phase5-validation.json"

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

function Invoke-JsonCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [string[]]$ArgumentList
    )

    $output = (& $FilePath @ArgumentList 2>&1 | Out-String).Trim()
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        throw "$FilePath $($ArgumentList -join ' ') failed with exit code $exitCode`n$output"
    }
    try {
        return $output | ConvertFrom-Json
    } catch {
        throw "Command did not return valid JSON: $FilePath $($ArgumentList -join ' ')`n$output"
    }
}

function Require-CleanAcceptanceHost {
    if ($env:OS -ne "Windows_NT") {
        throw "Phase 5 clean-machine validation must run on Windows"
    }
    if (-not [Environment]::Is64BitOperatingSystem) {
        throw "Phase 5 currently supports only x64-compatible Windows"
    }
    if (Test-Path -LiteralPath $UninstallKey) {
        $existing = Get-ItemProperty -LiteralPath $UninstallKey -ErrorAction Stop
        throw "codemcp-remote is already installed at '$($existing.InstallLocation)'; use a fresh Windows host/VM"
    }
}

function Resolve-Git {
    $git = Get-Command git.exe -ErrorAction SilentlyContinue
    if ($null -eq $git) {
        throw "Git for Windows is required by the v0.1.0 release contract but was not found"
    }
    return $git.Source
}

function Get-InstalledRelease {
    if (-not (Test-Path -LiteralPath $UninstallKey)) {
        throw "codemcp-remote is not installed; run Action=Prepare first"
    }
    $registration = Get-ItemProperty -LiteralPath $UninstallKey -ErrorAction Stop
    $installDir = [System.IO.Path]::GetFullPath([string]$registration.InstallLocation)
    $exe = Join-Path $installDir "codemcp-remote.exe"
    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
        throw "installed codemcp-remote.exe is missing: $exe"
    }
    return [ordered]@{
        install_dir = $installDir
        exe = $exe
    }
}

function Set-RuntimeIsolationPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$InstallDir,
        [Parameter(Mandatory = $true)]
        [string]$GitPath
    )

    $entries = @(
        $InstallDir,
        (Split-Path -Parent $GitPath),
        (Join-Path $env:SystemRoot "System32")
    )
    $unique = New-Object System.Collections.Generic.List[string]
    foreach ($entry in $entries) {
        if (-not [string]::IsNullOrWhiteSpace($entry) -and -not $unique.Contains($entry)) {
            $unique.Add($entry)
        }
    }
    $env:PATH = $unique -join ";"

    foreach ($forbidden in @("python.exe", "py.exe", "uv.exe", "pwsh.exe")) {
        if ($null -ne (Get-Command $forbidden -ErrorAction SilentlyContinue)) {
            throw "runtime isolation failed: $forbidden is still visible on PATH"
        }
    }
}

function Prepare-AcceptanceProject {
    param(
        [Parameter(Mandatory = $true)]
        [string]$GitPath,
        [Parameter(Mandatory = $true)]
        [string]$Root
    )

    if (Test-Path -LiteralPath $Root) {
        throw "Phase 5 disposable project already exists: $Root"
    }
    New-Item -ItemType Directory -Force -Path $Root | Out-Null

    & $GitPath -C $Root init -q --initial-branch=main
    if ($LASTEXITCODE -ne 0) { throw "git init failed" }
    & $GitPath -C $Root config user.name "codemcp-remote Phase 5"
    if ($LASTEXITCODE -ne 0) { throw "git user.name configuration failed" }
    & $GitPath -C $Root config user.email "phase5@localhost.invalid"
    if ($LASTEXITCODE -ne 0) { throw "git user.email configuration failed" }

    @"
# codemcp-remote Phase 5 clean-machine acceptance

This disposable repository exists only to validate the packaged Windows release.
"@ | Set-Content -LiteralPath (Join-Path $Root "README.md") -Encoding UTF8

    @"
[project]
name = "codemcp-remote-phase5-acceptance"
version = "0.0.0"
"@ | Set-Content -LiteralPath (Join-Path $Root "pyproject.toml") -Encoding ASCII

    "phase5-clean-machine" | Set-Content -LiteralPath (Join-Path $Root "PHASE5_ACCEPTANCE.txt") -Encoding ASCII

    & $GitPath -C $Root add README.md pyproject.toml PHASE5_ACCEPTANCE.txt
    if ($LASTEXITCODE -ne 0) { throw "git add failed" }
    & $GitPath -C $Root commit -q -m "chore: create phase5 acceptance baseline"
    if ($LASTEXITCODE -ne 0) { throw "git baseline commit failed" }

    $head = (& $GitPath -C $Root rev-parse HEAD | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $head -notmatch "^[0-9a-f]{40,64}$") {
        throw "git rev-parse HEAD failed"
    }
    return $head
}

function Assert-DoctorContract {
    param(
        [Parameter(Mandatory = $true)]
        $Doctor
    )

    if ($Doctor.status -ne "ok") {
        throw "doctor did not report status=ok"
    }
    if ($Doctor.checks.configuration.worker_mode -ne "local") {
        throw "clean-machine release is not using the native local worker"
    }
    if ($Doctor.checks.git.status -ne "ok") {
        throw "doctor cannot find Git after runtime PATH isolation"
    }

    $provider = [string]$Doctor.checks.transport.provider
    if ($provider -eq "cloudflare") {
        if ($Doctor.checks.cloudflare_settings.status -ne "ok") {
            throw "doctor did not validate Cloudflare transport settings"
        }
        if ([string]$Doctor.checks.cloudflare_settings.origin_url -ne "http://127.0.0.1:46200/mcp") {
            throw "Cloudflare origin is not the fixed loopback MCP endpoint"
        }
        if ($Doctor.checks.cloudflared.status -ne "ok") {
            throw "doctor cannot find the bundled cloudflared"
        }
        if (
            $Doctor.checks.tunnel_token.status -ne "ok" -or
            $Doctor.checks.tunnel_token.source -ne "windows-dpapi"
        ) {
            throw "doctor did not prove Cloudflare tunnel-token DPAPI recovery"
        }
        if (
            $Doctor.checks.auth.status -ne "ok" -or
            $Doctor.checks.auth.mode -ne "oauth-resource-server" -or
            $Doctor.checks.auth.verification_contract -ne "mcp-rs-verification-v1" -or
            $Doctor.checks.auth.secret_source -ne "windows-dpapi"
        ) {
            throw "doctor did not prove the external OAuth Resource Server contract and DPAPI secret recovery"
        }
        if ([string]$Doctor.checks.auth.resource -ne [string]$Doctor.checks.cloudflare_settings.public_url) {
            throw "OAuth canonical resource does not match the Cloudflare public MCP URL"
        }
        return
    }

    if ($provider -ne "openai-tunnel") {
        throw "doctor reported an unsupported transport provider: $provider"
    }
    if ($Doctor.checks.api_key.status -ne "ok" -or $Doctor.checks.api_key.source -ne "windows-dpapi") {
        throw "doctor did not prove Windows DPAPI secret recovery"
    }
    if ($Doctor.checks.tunnel_client.status -ne "ok") {
        throw "doctor cannot find the bundled tunnel-client"
    }
}

function Assert-NoEmbeddedAuthServerState {
    param(
        [Parameter(Mandatory = $true)]
        [string]$AppRoot
    )

    if (-not (Test-Path -LiteralPath $AppRoot -PathType Container)) {
        return
    }
    $forbiddenPatterns = @(
        "*mcp-auth-server*",
        "*signing-key*",
        "*private-key*",
        "*users*.sqlite*",
        "*clients*.sqlite*",
        "*refresh-token*"
    )
    foreach ($pattern in $forbiddenPatterns) {
        $found = Get-ChildItem -LiteralPath $AppRoot -Recurse -Force -ErrorAction Stop |
            Where-Object { $_.Name -like $pattern } |
            Select-Object -First 1
        if ($null -ne $found) {
            throw "codemcp-remote runtime unexpectedly contains auth-server private state: $($found.FullName)"
        }
    }
}

function Invoke-Start {
    $release = Get-InstalledRelease
    $gitPath = Resolve-Git
    Set-RuntimeIsolationPath -InstallDir $release.install_dir -GitPath $gitPath

    $env:CONTROL_PLANE_API_KEY = $null
    $env:TUNNEL_TOKEN = $null
    $env:CODEMCP_RS_VERIFICATION_SECRET = $null
    $doctor = Invoke-JsonCommand -FilePath $release.exe -ArgumentList @("doctor")
    Assert-DoctorContract -Doctor $doctor
    $appRoot = Join-Path $env:LOCALAPPDATA "codemcp-remote"
    Assert-NoEmbeddedAuthServerState -AppRoot $appRoot

    $start = Invoke-JsonCommand -FilePath $release.exe -ArgumentList @("start", "--startup-timeout", "45")
    if ($start.status -ne "ok") {
        throw "native lifecycle start failed"
    }
    $status = Invoke-JsonCommand -FilePath $release.exe -ArgumentList @("status")
    if ($status.status -ne "running") {
        throw "native lifecycle did not reach running state"
    }
    if (-not $status.bridge.owned -or $status.bridge.health.status -ne "ok") {
        throw "Bridge is not healthy and owned"
    }
    if (-not $status.tunnel.owned -or $status.tunnel.health.status -ne "ok") {
        throw "Tunnel is not healthy and owned"
    }

    $phase5 = $null
    if (Test-Path -LiteralPath $Phase5StateFile -PathType Leaf) {
        try {
            $phase5 = Get-Content -LiteralPath $Phase5StateFile -Raw -Encoding UTF8 | ConvertFrom-Json
        } catch {
            throw "Phase 5 validation state is unreadable: $Phase5StateFile"
        }
    }

    $provider = [string]$doctor.checks.transport.provider
    $transportSecretSource = if ($provider -eq "cloudflare") {
        [string]$doctor.checks.tunnel_token.source
    } else {
        [string]$doctor.checks.api_key.source
    }
    $transportClientPath = if ($provider -eq "cloudflare") {
        [string]$doctor.checks.cloudflared.path
    } else {
        [string]$doctor.checks.tunnel_client.path
    }

    [ordered]@{
        status = "ready-for-remote-verification"
        phase = "5.5.7"
        action = "start"
        install_dir = $release.install_dir
        app_root = (Join-Path $env:LOCALAPPDATA "codemcp-remote")
        project_id = if ($null -ne $phase5) { [string]$phase5.project_id } else { $null }
        project_root = if ($null -ne $phase5) { [string]$phase5.project_root } else { $null }
        baseline_head = if ($null -ne $phase5) { [string]$phase5.baseline_head } else { $null }
        worker_mode = [string]$doctor.checks.configuration.worker_mode
        git_path = $gitPath
        transport = $provider
        transport_secret_source = $transportSecretSource
        transport_client_path = $transportClientPath
        public_url = if ($provider -eq "cloudflare") { [string]$doctor.checks.cloudflare_settings.public_url } else { $null }
        auth_issuer = if ($provider -eq "cloudflare") { [string]$doctor.checks.auth.issuer } else { $null }
        canonical_resource_uri = if ($provider -eq "cloudflare") { [string]$doctor.checks.auth.resource } else { $null }
        auth_secret_source = if ($provider -eq "cloudflare") { [string]$doctor.checks.auth.secret_source } else { $null }
        bridge_health = [string]$status.bridge.health.status
        tunnel_health = [string]$status.tunnel.health.status
        python_visible_on_isolated_path = ($null -ne (Get-Command python.exe -ErrorAction SilentlyContinue))
        uv_visible_on_isolated_path = ($null -ne (Get-Command uv.exe -ErrorAction SilentlyContinue))
        pwsh_visible_on_isolated_path = ($null -ne (Get-Command pwsh.exe -ErrorAction SilentlyContinue))
        wsl_command_visible = ($null -ne (Get-Command wsl.exe -ErrorAction SilentlyContinue))
        next = "Use the ChatGPT connector through the authenticated Cloudflare MCP URL and run the Phase 5.5.7 remote contract before cleanup."
    } | ConvertTo-Json -Depth 7
}

function Invoke-Cleanup {
    if (-not (Test-Path -LiteralPath $UninstallKey)) {
        [ordered]@{
            status = "ok"
            phase = "5"
            action = "cleanup"
            note = "codemcp-remote is not installed"
        } | ConvertTo-Json -Depth 5
        return
    }

    $release = Get-InstalledRelease
    & $release.exe stop | Out-Host

    $uninstallers = @(Get-ChildItem -LiteralPath $release.install_dir -File -Filter "unins*.exe" -ErrorAction SilentlyContinue)
    if ($uninstallers.Count -ne 1) {
        throw "expected exactly one Inno Setup uninstaller in $($release.install_dir)"
    }
    $exitCode = Invoke-GuiProcessAndWait -FilePath $uninstallers[0].FullName -ArgumentList @(
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART"
    )
    if ($exitCode -ne 0) {
        throw "clean-machine uninstall failed with exit code $exitCode"
    }
    if (Test-Path -LiteralPath $UninstallKey) {
        throw "uninstall registration still exists after cleanup"
    }

    [ordered]@{
        status = "ok"
        phase = "5"
        action = "cleanup"
        install_dir = $release.install_dir
        note = "installer removed; runtime data and disposable project are intentionally preserved"
    } | ConvertTo-Json -Depth 5
}

function Remove-Phase5AcceptanceTree {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $fullPath = [System.IO.Path]::GetFullPath($Path).TrimEnd("\")
    $allowedPaths = @(
        [System.IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA "codemcp-remote")).TrimEnd("\"),
        [System.IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA "codemcp-remote-phase5")).TrimEnd("\")
    )
    if ($allowedPaths -notcontains $fullPath) {
        throw "Reset refused to remove a path outside the fixed Phase 5 acceptance roots: $fullPath"
    }
    if (-not (Test-Path -LiteralPath $fullPath)) {
        return
    }

    $item = Get-Item -LiteralPath $fullPath -Force
    if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Reset refused to remove a reparse-point acceptance root: $fullPath"
    }
    Remove-Item -LiteralPath $fullPath -Recurse -Force
}

function Invoke-Reset {
    if (Test-Path -LiteralPath $UninstallKey) {
        throw "Reset requires codemcp-remote to be uninstalled first; run Action=Cleanup"
    }

    $appRoot = Join-Path $env:LOCALAPPDATA "codemcp-remote"
    $acceptanceRoot = Join-Path $env:LOCALAPPDATA "codemcp-remote-phase5"
    Remove-Phase5AcceptanceTree -Path $appRoot
    Remove-Phase5AcceptanceTree -Path $acceptanceRoot

    [ordered]@{
        status = "ok"
        phase = "5"
        action = "reset"
        removed = @($appRoot, $acceptanceRoot)
        note = "Phase 5 acceptance-only runtime and disposable project state removed"
    } | ConvertTo-Json -Depth 5
}

if ($Action -eq "Start") {
    Invoke-Start
    exit 0
}
if ($Action -eq "Cleanup") {
    Invoke-Cleanup
    exit 0
}
if ($Action -eq "Reset") {
    Invoke-Reset
    exit 0
}

Require-CleanAcceptanceHost

if ([string]::IsNullOrWhiteSpace($InstallerPath)) {
    throw "-InstallerPath is required for Action=Prepare"
}
if ($ExpectedInstallerSha256 -notmatch "^[0-9a-fA-F]{64}$") {
    throw "-ExpectedInstallerSha256 must be a 64-character SHA-256 digest"
}
if ($Transport -eq "cloudflare") {
    if ([string]::IsNullOrWhiteSpace($PublicUrl)) {
        throw "-PublicUrl is required for Cloudflare Action=Prepare"
    }
    if ([string]::IsNullOrWhiteSpace($AuthorizationServerIssuer)) {
        throw "-AuthorizationServerIssuer is required for Cloudflare Action=Prepare"
    }
    if ([string]::IsNullOrWhiteSpace($CanonicalResourceUri)) {
        $CanonicalResourceUri = $PublicUrl
    }
    if ([string]::IsNullOrWhiteSpace($env:TUNNEL_TOKEN)) {
        throw "Set TUNNEL_TOKEN in this process before Cloudflare Action=Prepare; never pass the secret on the command line"
    }
    if ([string]::IsNullOrWhiteSpace($env:CODEMCP_RS_VERIFICATION_SECRET)) {
        throw "Set CODEMCP_RS_VERIFICATION_SECRET in this process before Cloudflare Action=Prepare; never pass the secret on the command line"
    }
} else {
    if ([string]::IsNullOrWhiteSpace($TunnelId)) {
        throw "-TunnelId is required for openai-tunnel Action=Prepare"
    }
    if ([string]::IsNullOrWhiteSpace($env:CONTROL_PLANE_API_KEY)) {
        throw "Set CONTROL_PLANE_API_KEY in this process before openai-tunnel Action=Prepare; never pass the secret on the command line"
    }
}

$installer = (Resolve-Path -LiteralPath $InstallerPath).Path
$actualInstallerSha256 = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualInstallerSha256 -ne $ExpectedInstallerSha256.ToLowerInvariant()) {
    throw "installer SHA-256 mismatch: expected=$ExpectedInstallerSha256 actual=$actualInstallerSha256"
}

$gitPath = Resolve-Git
$projectRootPath = if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    $DefaultProjectRoot
} else {
    [System.IO.Path]::GetFullPath($ProjectRoot)
}

$setupExit = Invoke-GuiProcessAndWait -FilePath $installer -ArgumentList @(
    "/VERYSILENT",
    "/SUPPRESSMSGBOXES",
    "/NORESTART",
    "/MERGETASKS=!addtopath"
)
if ($setupExit -ne 0) {
    throw "clean-machine installer failed with exit code $setupExit"
}
if (-not (Test-Path -LiteralPath $UninstallKey)) {
    throw "installer did not create the expected uninstall registration"
}

$release = Get-InstalledRelease
$expectedInstallDir = [System.IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA "Programs\codemcp-remote"))
if ($release.install_dir.TrimEnd("\") -ne $expectedInstallDir.TrimEnd("\")) {
    throw "unexpected default install location: $($release.install_dir)"
}

$tunnelExe = Join-Path $release.install_dir "tunnel-client.exe"
$cloudflaredExe = Join-Path $release.install_dir "cloudflared.exe"
foreach ($required in @(
    $release.exe,
    $cloudflaredExe,
    $tunnelExe,
    (Join-Path $release.install_dir "LICENSE"),
    (Join-Path $release.install_dir "THIRD_PARTY_NOTICES.txt")
)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "installed release is missing required file: $required"
    }
}
foreach ($forbiddenBundledTool in @("python.exe", "uv.exe", "pwsh.exe", "wsl.exe")) {
    if (Test-Path -LiteralPath (Join-Path $release.install_dir $forbiddenBundledTool) -PathType Leaf) {
        throw "installer unexpectedly bundles $forbiddenBundledTool"
    }
}

Set-RuntimeIsolationPath -InstallDir $release.install_dir -GitPath $gitPath

$versionText = (& $release.exe --version 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $versionText -notmatch "0\.1\.0") {
    throw "installed codemcp-remote version check failed: $versionText"
}

$initArgs = if ($Transport -eq "cloudflare") {
    @(
        "init",
        "--transport", "cloudflare",
        "--public-url", $PublicUrl,
        "--origin-url", $OriginUrl,
        "--metrics-addr", $MetricsAddr,
        "--store-transport-secret",
        "--auth-mode", "oauth-resource-server",
        "--authorization-server-issuer", $AuthorizationServerIssuer,
        "--canonical-resource-uri", $CanonicalResourceUri,
        "--validation-resource-id", $ValidationResourceId,
        "--store-auth-secret"
    )
} else {
    @(
        "init",
        "--transport", "openai-tunnel",
        "--tunnel-id", $TunnelId,
        "--store-api-key"
    )
}
$init = Invoke-JsonCommand -FilePath $release.exe -ArgumentList $initArgs
if ($init.status -ne "ok") {
    throw "codemcp-remote init did not report status=ok"
}

$env:CONTROL_PLANE_API_KEY = $null
$env:TUNNEL_TOKEN = $null
$env:CODEMCP_RS_VERIFICATION_SECRET = $null
$doctor = Invoke-JsonCommand -FilePath $release.exe -ArgumentList @("doctor")
Assert-DoctorContract -Doctor $doctor

$baselineHead = Prepare-AcceptanceProject -GitPath $gitPath -Root $projectRootPath
$project = Invoke-JsonCommand -FilePath $release.exe -ArgumentList @(
    "project", "add", $ProjectId, $projectRootPath
)
if ($project.status -ne "ok") {
    throw "project registration failed"
}

$doctorAfterProject = Invoke-JsonCommand -FilePath $release.exe -ArgumentList @("doctor")
Assert-DoctorContract -Doctor $doctorAfterProject
if ([int]$doctorAfterProject.checks.configuration.projects -lt 1) {
    throw "doctor did not observe the registered Phase 5 project"
}
$appRoot = Join-Path $env:LOCALAPPDATA "codemcp-remote"
Assert-NoEmbeddedAuthServerState -AppRoot $appRoot

$provider = [string]$doctorAfterProject.checks.transport.provider
$transportSecretSource = if ($provider -eq "cloudflare") {
    [string]$doctorAfterProject.checks.tunnel_token.source
} else {
    [string]$doctorAfterProject.checks.api_key.source
}
$transportClientPath = if ($provider -eq "cloudflare") {
    [string]$doctorAfterProject.checks.cloudflared.path
} else {
    [string]$doctorAfterProject.checks.tunnel_client.path
}

$phase5State = [ordered]@{
    phase = "5.5.7"
    project_id = $ProjectId
    project_root = $projectRootPath
    baseline_head = $baselineHead
    installer_sha256 = $actualInstallerSha256
    install_dir = $release.install_dir
    transport = $provider
    public_url = if ($provider -eq "cloudflare") { [string]$doctorAfterProject.checks.cloudflare_settings.public_url } else { $null }
    auth_issuer = if ($provider -eq "cloudflare") { [string]$doctorAfterProject.checks.auth.issuer } else { $null }
    canonical_resource_uri = if ($provider -eq "cloudflare") { [string]$doctorAfterProject.checks.auth.resource } else { $null }
    validation_resource_id = if ($provider -eq "cloudflare") { [string]$doctorAfterProject.checks.auth.validation_resource_id } else { $null }
}
$stateParent = Split-Path -Parent $Phase5StateFile
New-Item -ItemType Directory -Force -Path $stateParent | Out-Null
$phase5State | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $Phase5StateFile -Encoding UTF8

[ordered]@{
    status = "ready-for-start"
    phase = "5.5.7"
    action = "prepare"
    installer_sha256 = $actualInstallerSha256
    install_dir = $release.install_dir
    app_root = $appRoot
    phase5_state_file = $Phase5StateFile
    project_id = $ProjectId
    project_root = $projectRootPath
    baseline_head = $baselineHead
    worker_mode = [string]$doctorAfterProject.checks.configuration.worker_mode
    git_path = $gitPath
    transport = $provider
    transport_secret_source = $transportSecretSource
    transport_client_path = $transportClientPath
    public_url = if ($provider -eq "cloudflare") { [string]$doctorAfterProject.checks.cloudflare_settings.public_url } else { $null }
    auth_issuer = if ($provider -eq "cloudflare") { [string]$doctorAfterProject.checks.auth.issuer } else { $null }
    canonical_resource_uri = if ($provider -eq "cloudflare") { [string]$doctorAfterProject.checks.auth.resource } else { $null }
    auth_secret_source = if ($provider -eq "cloudflare") { [string]$doctorAfterProject.checks.auth.secret_source } else { $null }
    python_visible_on_isolated_path = ($null -ne (Get-Command python.exe -ErrorAction SilentlyContinue))
    uv_visible_on_isolated_path = ($null -ne (Get-Command uv.exe -ErrorAction SilentlyContinue))
    pwsh_visible_on_isolated_path = ($null -ne (Get-Command pwsh.exe -ErrorAction SilentlyContinue))
    wsl_command_visible = ($null -ne (Get-Command wsl.exe -ErrorAction SilentlyContinue))
    next = "Run Action=Start, then connect ChatGPT to the authenticated Cloudflare MCP URL and execute the Phase 5.5.7 remote contract."
} | ConvertTo-Json -Depth 7
