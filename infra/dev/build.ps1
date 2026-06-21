#!/usr/bin/env pwsh
# Build all AURA service images using podman build from the repo root.
#
# podman-compose 1.5.0 has a Windows bug where absolute context paths
# (e.g. C:\...) are incorrectly treated as git URLs, causing the -f flag
# to be omitted. This script calls podman build directly, which works correctly.
#
# Usage (from any directory):
#   .\infra\dev\build.ps1              # build all services
#   .\infra\dev\build.ps1 orchestrator # build a single service by name

param(
    [string]$Service = ""
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path "$PSScriptRoot\..\..")

$services = [ordered]@{
    "robot-runtime"       = @{ dockerfile = "services/robot-runtime/Dockerfile";       context = "." }
    "conversation-runtime"= @{ dockerfile = "services/conversation-runtime/Dockerfile"; context = "." }
    "connector-service"   = @{ dockerfile = "services/connector-service/Dockerfile";    context = "." }
    "memory-service"      = @{ dockerfile = "services/memory-service/Dockerfile";       context = "." }
    "identity-service"    = @{ dockerfile = "services/identity-service/Dockerfile";     context = "." }
    "orchestrator"        = @{ dockerfile = "services/orchestrator/Dockerfile";         context = "." }
    "operator-console"    = @{ dockerfile = "apps/operator-console/Dockerfile"; context = "apps/operator-console" }
}

Push-Location $root
try {
    $targets = if ($Service) { @($Service) } else { $services.Keys }

    foreach ($name in $targets) {
        if (-not $services.Contains($name)) {
            Write-Error "Unknown service: $name. Valid: $($services.Keys -join ', ')"
        }
        $cfg  = $services[$name]
        $tag  = "aura/$name`:dev"
        Write-Host "Building $tag ..." -ForegroundColor Cyan
        podman build -f $cfg.dockerfile -t $tag $cfg.context
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Build failed for $name (exit $LASTEXITCODE)"
        }
        Write-Host "OK: $tag" -ForegroundColor Green
    }
    Write-Host "`nAll images built. Run 'podman-compose up' from infra/dev/ to start the stack." -ForegroundColor Green
} finally {
    Pop-Location
}
