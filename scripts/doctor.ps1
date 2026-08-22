[CmdletBinding()]
param(
    [string]$EnvFile,
    [string]$ProfileName,
    [string]$ProfileDir,
    [string]$BridgeUrl,
    [string]$TunnelHealthUrl,
    [switch]$SkipTunnel
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "tunnel-common.ps1")

$repositoryRoot = Get-Phase5RepositoryRoot
if ([string]::IsNullOrWhiteSpace($EnvFile)) {
    $EnvFile = Join-Path $repositoryRoot "config\tunnel-profile.local.env"
}
$settings = Get-Phase5Settings `
    -RepositoryRoot $repositoryRoot `
    -EnvFile $EnvFile `
    -ProfileName $ProfileName `
    -ProfileDir $ProfileDir `
    -BridgeUrl $BridgeUrl `
    -TunnelHealthUrl $TunnelHealthUrl

$report = [ordered]@{
    phase = "5"
    repository_root = $repositoryRoot
    bridge = [ordered]@{}
    tunnel = [ordered]@{}
}
$checksPassed = $true

$uv = Get-Command uv -ErrorAction SilentlyContinue
if ($null -eq $uv) {
    $report.bridge.doctor = @{ status = "missing_dependency"; error = "uv was not found on PATH" }
    $report.bridge.healthz = @{ status = "not_checked" }
    $checksPassed = $false
} else {
    $bridgeDoctorOutput = (& $uv.Source run --project (Join-Path $repositoryRoot "bridge") `
        codemcp-bridge doctor --strict --json 2>&1 | Out-String).Trim()
    $bridgeDoctorExit = $LASTEXITCODE
    $report.bridge.doctor = [ordered]@{
        status = if ($bridgeDoctorExit -eq 0) { "ok" } else { "failed" }
        exit_code = $bridgeDoctorExit
        output = Protect-Phase5DiagnosticText -Text $bridgeDoctorOutput
    }
    if ($bridgeDoctorExit -ne 0) {
        $checksPassed = $false
    }

    $bridgeUri = [Uri]$settings.BridgeUrl
    $bridgeHealthUrl = "{0}://{1}/healthz" -f $bridgeUri.Scheme, $bridgeUri.Authority
    $bridgeHealth = Test-Phase5HttpEndpoint -Url $bridgeHealthUrl
    $report.bridge.healthz = $bridgeHealth
    if ($bridgeHealth.status -ne "ok") {
        $checksPassed = $false
    }
}

if ($SkipTunnel) {
    $report.tunnel = @{ status = "skipped"; reason = "-SkipTunnel was supplied" }
} else {
    $tunnelClient = Get-Command tunnel-client -ErrorAction SilentlyContinue
    if ($null -eq $tunnelClient) {
        $report.tunnel = @{ status = "missing_dependency"; error = "tunnel-client was not found on PATH" }
        $checksPassed = $false
    } elseif (-not $settings.ApiKeyPresent -or [string]::IsNullOrWhiteSpace($settings.TunnelId)) {
        $report.tunnel = [ordered]@{
            status = "not_configured"
            error = "CONTROL_PLANE_TUNNEL_ID and CONTROL_PLANE_API_KEY are required"
        }
        $checksPassed = $false
    } else {
        try {
            Assert-Phase5TunnelId -TunnelId $settings.TunnelId
            $profilePath = Get-Phase5ProfilePath `
                -ProfileDir $settings.ProfileDir `
                -ProfileName $settings.ProfileName
            Assert-Phase5ProfileContract `
                -ProfilePath $profilePath `
                -TunnelId $settings.TunnelId `
                -BridgeUrl $settings.BridgeUrl

            $tunnelDoctorOutput = (& $tunnelClient.Source doctor `
                --profile $settings.ProfileName `
                --profile-dir $settings.ProfileDir `
                --health.listen-addr "127.0.0.1:0" `
                --explain --json 2>&1 | Out-String).Trim()
            $tunnelDoctorExit = $LASTEXITCODE
            $tunnelHealth = Test-Phase5HttpEndpoint -Url ("{0}/healthz" -f $settings.TunnelHealthUrl)
            $tunnelReady = Test-Phase5HttpEndpoint -Url ("{0}/readyz" -f $settings.TunnelHealthUrl)
            $report.tunnel = [ordered]@{
                status = if ($tunnelDoctorExit -eq 0 -and
                    $tunnelHealth.status -eq "ok" -and
                    $tunnelReady.status -eq "ok") { "ok" } else { "failed" }
                profile = $settings.ProfileName
                profile_path = $profilePath
                doctor = [ordered]@{
                    exit_code = $tunnelDoctorExit
                    output = Protect-Phase5DiagnosticText -Text $tunnelDoctorOutput
                }
                healthz = $tunnelHealth
                readyz = $tunnelReady
            }
            if ($report.tunnel.status -ne "ok") {
                $checksPassed = $false
            }
        } catch {
            $report.tunnel = [ordered]@{
                status = "invalid_configuration"
                error = $_.Exception.Message
            }
            $checksPassed = $false
        }
    }
}

$report.status = if ($checksPassed) { "ok" } else { "failed" }
$report | ConvertTo-Json -Depth 8
if (-not $checksPassed) {
    exit 1
}
exit 0
