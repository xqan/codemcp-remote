[CmdletBinding()]
param(
    [string]$EnvFile,
    [string]$ProfileName,
    [string]$ProfileDir,
    [string]$BridgeUrl,
    [string]$HealthListenAddress,
    [switch]$Initialize,
    [switch]$Force
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
    -BridgeUrl $BridgeUrl
if ([string]::IsNullOrWhiteSpace($HealthListenAddress)) {
    $HealthListenAddress = $settings.HealthListenAddress
}
$HealthListenAddress = Assert-Phase5HealthListenAddress -Value $HealthListenAddress
Assert-Phase5TunnelId -TunnelId $settings.TunnelId
if (-not $settings.ApiKeyPresent) {
    throw "CONTROL_PLANE_API_KEY is not set; inject it from a secret store or process environment"
}

$tunnelClient = Get-Phase5TunnelClient
New-Item -ItemType Directory -Path $settings.ProfileDir -Force | Out-Null

if ($Initialize) {
    $initArguments = @(
        "init",
        "--sample", "sample_mcp_remote_no_auth",
        "--profile", $settings.ProfileName,
        "--profile-dir", $settings.ProfileDir,
        "--tunnel-id", $settings.TunnelId,
        "--mcp-server-url", $settings.BridgeUrl,
        "--health-listen-addr", $HealthListenAddress,
        "--control-plane-api-key-ref", "env:CONTROL_PLANE_API_KEY"
    )
    if ($Force) {
        $initArguments += "--force"
    }
    & $tunnelClient.Source @initArguments
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

$profilePath = Get-Phase5ProfilePath `
    -ProfileDir $settings.ProfileDir `
    -ProfileName $settings.ProfileName
Assert-Phase5ProfileContract `
    -ProfilePath $profilePath `
    -TunnelId $settings.TunnelId `
    -BridgeUrl $settings.BridgeUrl

$bridgeUri = [Uri]$settings.BridgeUrl
$bridgeHealthUrl = "{0}://{1}/healthz" -f $bridgeUri.Scheme, $bridgeUri.Authority
$bridgeHealth = Test-Phase5HttpEndpoint -Url $bridgeHealthUrl
if ($bridgeHealth.status -ne "ok") {
    throw "Bridge health check failed at $bridgeHealthUrl; start scripts/start-bridge.ps1 first"
}

$runArguments = @(
    "run",
    "--profile", $settings.ProfileName,
    "--profile-dir", $settings.ProfileDir,
    "--health.listen-addr", $HealthListenAddress
)
Write-Host ("Starting tunnel-client profile '{0}'. Health: http://127.0.0.1:{1}" -f `
        $settings.ProfileName, ($HealthListenAddress -replace '^127\.0\.0\.1:', ''))
& $tunnelClient.Source @runArguments
exit $LASTEXITCODE
