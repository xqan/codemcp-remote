[CmdletBinding()]
param(
    [string]$DestinationDir,
    [string]$CloudflaredVersion = "2026.7.3",
    [string]$OpenAITunnelClientVersion = "v0.0.12",
    [switch]$ForceDownload
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($env:OS -ne "Windows_NT") {
    throw "remote transport Windows packaging must run on Windows"
}

$repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
if ([string]::IsNullOrWhiteSpace($DestinationDir)) {
    $DestinationDir = Join-Path $repositoryRoot ".local\dist\codemcp-remote"
}
$DestinationDir = [System.IO.Path]::GetFullPath($DestinationDir)

function Invoke-PreparationScript {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ScriptPath,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [Parameter(Mandatory = $true)]
        [string]$Label
    )

    $output = (& pwsh -NoLogo -NoProfile -NonInteractive -File $ScriptPath @Arguments | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "$Label preparation failed with exit code $LASTEXITCODE"
    }
    try {
        $result = $output | ConvertFrom-Json
    } catch {
        throw "$Label preparation did not return valid JSON: $output"
    }
    if ($result.status -ne "ok") {
        throw "$Label preparation did not report status=ok"
    }
    return $result
}

$openAIArgs = @(
    "-DestinationDir", $DestinationDir,
    "-Version", $OpenAITunnelClientVersion
)
$cloudflareArgs = @(
    "-DestinationDir", $DestinationDir,
    "-Version", $CloudflaredVersion
)
if ($ForceDownload) {
    $openAIArgs += "-ForceDownload"
    $cloudflareArgs += "-ForceDownload"
}

$openAI = Invoke-PreparationScript `
    -ScriptPath (Join-Path $repositoryRoot "scripts\prepare-tunnel-client.ps1") `
    -Arguments $openAIArgs `
    -Label "OpenAI tunnel-client"
$cloudflare = Invoke-PreparationScript `
    -ScriptPath (Join-Path $repositoryRoot "scripts\prepare-cloudflared.ps1") `
    -Arguments $cloudflareArgs `
    -Label "cloudflared"

$notice = @"
Third-party software bundled with codemcp-remote

Cloudflare Tunnel client (cloudflared)
Version: $($cloudflare.version)
Source: https://github.com/cloudflare/cloudflared
License: Apache License 2.0
Installed license text: THIRD_PARTY\cloudflared\LICENSE
Installed cloudflared.exe SHA-256: $($cloudflare.executable_sha256)

OpenAI Secure MCP Tunnel client
Version: $($openAI.version)
Source: https://github.com/openai/tunnel-client
License: Apache License 2.0
Installed license text: THIRD_PARTY\tunnel-client\LICENSE
Installed tunnel-client.exe SHA-256: $($openAI.executable_sha256)

codemcp-remote is not affiliated with or endorsed by Cloudflare or OpenAI.
"@
$notice | Set-Content -LiteralPath (Join-Path $DestinationDir "THIRD_PARTY_NOTICES.txt") -Encoding utf8

[ordered]@{
    status = "ok"
    recommended_provider = "cloudflare"
    cloudflare = $cloudflare
    openai_tunnel = $openAI
    notices = Join-Path $DestinationDir "THIRD_PARTY_NOTICES.txt"
} | ConvertTo-Json -Depth 6
