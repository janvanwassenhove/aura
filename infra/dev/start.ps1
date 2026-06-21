<#
.SYNOPSIS
    Start (and optionally rebuild) the AURA dev stack with Podman Compose.

.PARAMETER Build
    Rebuild container images before starting. Pass a service name to rebuild
    only that service, or omit to rebuild all.

.PARAMETER Clean
    Stop and remove all containers before starting (forces a fresh stack).

.PARAMETER NoOpen
    Skip opening the browser after the stack is healthy.

.EXAMPLE
    .\start.ps1                      # Start (or restart) without rebuilding
    .\start.ps1 -Build               # Rebuild all images, then start
    .\start.ps1 -Build orchestrator  # Rebuild only the orchestrator image
    .\start.ps1 -Clean -Build        # Fresh start with full rebuild
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Build = "",   # "" = no rebuild; "all" or service name

    [switch]$Clean,
    [switch]$NoOpen
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$DevDir = $PSScriptRoot
Push-Location $DevDir

# ---------------------------------------------------------------------------
# Helper: coloured output
# ---------------------------------------------------------------------------
function Write-Step  { param($msg) Write-Host "  → $msg" -ForegroundColor Cyan }
function Write-OK    { param($msg) Write-Host "  ✓ $msg" -ForegroundColor Green }
function Write-Warn  { param($msg) Write-Host "  ⚠ $msg" -ForegroundColor Yellow }
function Write-Fail  { param($msg) Write-Host "  ✗ $msg" -ForegroundColor Red }

Write-Host ""
Write-Host "╔══════════════════════════════════════╗" -ForegroundColor Magenta
Write-Host "║   AURA Dev Stack — start.ps1          ║" -ForegroundColor Magenta
Write-Host "╚══════════════════════════════════════╝" -ForegroundColor Magenta
Write-Host ""

# ---------------------------------------------------------------------------
# Pull API keys from Machine / User scope if not already in the session.
# Keys stored via setx or System Properties land in Machine or User scope
# but do NOT automatically appear in $env: for existing sessions.
# ---------------------------------------------------------------------------
foreach ($keyName in @("OPENAI_API_KEY", "OPENROUTER_API_KEY", "GEMINI_API_KEY")) {
    if (-not (Get-Item -LiteralPath "Env:$keyName" -ErrorAction SilentlyContinue)) {
        $val = [System.Environment]::GetEnvironmentVariable($keyName, "Machine")
        if (-not $val) {
            $val = [System.Environment]::GetEnvironmentVariable($keyName, "User")
        }
        if ($val) {
            [System.Environment]::SetEnvironmentVariable($keyName, $val, "Process")
            Write-Step "Loaded $keyName from system environment"
        }
    }
}

# ---------------------------------------------------------------------------
# Verify podman-compose is available
# ---------------------------------------------------------------------------
if (-not (Get-Command podman-compose -ErrorAction SilentlyContinue)) {
    Write-Fail "podman-compose not found. Install it with: pip install podman-compose"
    exit 1
}

# ---------------------------------------------------------------------------
# Optional: clean (stop + remove containers)
# ---------------------------------------------------------------------------
if ($Clean) {
    Write-Step "Stopping and removing existing containers..."
    podman-compose --env-file .env down --remove-orphans 2>&1 | Out-Null
    Write-OK "Containers removed"
}

# ---------------------------------------------------------------------------
# Optional: rebuild images
# ---------------------------------------------------------------------------
if ($Build -ne "") {
    $buildTarget = if ($Build -eq $true -or $Build -eq "all") { "" } else { $Build }
    if ($buildTarget -ne "") {
        Write-Step "Rebuilding image: $buildTarget"
        & "$PSScriptRoot\build.ps1" $buildTarget
    } else {
        Write-Step "Rebuilding all images..."
        & "$PSScriptRoot\build.ps1"
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Build failed — check errors above"
        exit $LASTEXITCODE
    }
    Write-OK "Build complete"
}

# ---------------------------------------------------------------------------
# Start the stack
# ---------------------------------------------------------------------------
Write-Step "Starting AURA dev stack with podman-compose..."
# When a build was performed, force-recreate containers so the new image is used.
# podman-compose up -d alone will NOT replace a running container with a newer image.
if ($Build -ne "") {
    podman-compose --env-file .env up -d --force-recreate
} else {
    podman-compose --env-file .env up -d
}
if ($LASTEXITCODE -ne 0) {
    Write-Fail "podman-compose up failed"
    exit $LASTEXITCODE
}

# ---------------------------------------------------------------------------
# Health check: poll each service until healthy
# ---------------------------------------------------------------------------
$services = @(
    @{ Name = "robot-runtime";        Url = "http://localhost:8001/health" },
    @{ Name = "conversation-runtime"; Url = "http://localhost:8002/health" },
    @{ Name = "orchestrator";         Url = "http://localhost:8003/health" },
    @{ Name = "connector-service";    Url = "http://localhost:8004/connector/health" },
    @{ Name = "memory-service";       Url = "http://localhost:8005/health" },
    @{ Name = "identity-service";     Url = "http://localhost:8006/health" }
)

$maxWait  = 60   # seconds
$interval = 2    # seconds between polls

Write-Host ""
Write-Step "Waiting for services to become healthy (timeout: ${maxWait}s)..."

$allHealthy = $true
foreach ($svc in $services) {
    $elapsed = 0
    $healthy = $false
    while ($elapsed -lt $maxWait) {
        try {
            $resp = Invoke-WebRequest -Uri $svc.Url -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
            if ($resp.StatusCode -eq 200) { $healthy = $true; break }
        } catch { }
        Start-Sleep -Seconds $interval
        $elapsed += $interval
    }
    if ($healthy) {
        Write-OK "$($svc.Name)"
    } else {
        Write-Warn "$($svc.Name) — not responding after ${maxWait}s (may still be starting)"
        $allHealthy = $false
    }
}

# ---------------------------------------------------------------------------
# Smoke test: LLM config endpoint
# ---------------------------------------------------------------------------
Write-Host ""
Write-Step "Smoke test: GET /orchestrator/config/llm"
try {
    $llm = Invoke-RestMethod -Uri "http://localhost:8003/orchestrator/config/llm" -TimeoutSec 5
    Write-OK "provider=$($llm.provider)  model=$($llm.model)"
    $okKey = if ($llm.provider -eq "openai")     { $llm.openai_key_set }
            elseif ($llm.provider -eq "openrouter") { $llm.openrouter_key_set }
            elseif ($llm.provider -eq "gemini")     { $llm.gemini_key_set }
            else                                     { $true }
    if ($okKey) {
        Write-OK "API key detected for provider '$($llm.provider)'"
    } else {
        Write-Warn "API key NOT detected for provider '$($llm.provider)' — set the env var and restart"
    }
} catch {
    Write-Warn "Could not reach orchestrator LLM config endpoint: $_"
}

# ---------------------------------------------------------------------------
# Open browser (operator console)
# ---------------------------------------------------------------------------
if (-not $NoOpen) {
    Write-Host ""
    Write-Step "Opening operator console at http://localhost:5173 ..."
    Start-Process "http://localhost:5173"
}

Write-Host ""
if ($allHealthy) {
    Write-OK "Stack is up and healthy. Happy developing!"
} else {
    Write-Warn "Stack started but some services may still be initialising."
    Write-Host "     Run: podman-compose --env-file .env logs -f" -ForegroundColor DarkGray
}
Write-Host ""

Pop-Location
