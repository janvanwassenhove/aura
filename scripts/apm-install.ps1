# ==============================================================================
# APM Install — Install Cognitive Hub into a consumer repository (PowerShell)
#
# Usage:
#   .\scripts\apm-install.ps1 [-Force] [-NoCommitInstructions] [-Gitignore]
#
# Prerequisites:
#   - Windows 10+ (tar.exe built-in) or PowerShell 5.1+
#   - Internet access to api.github.com  (no gh CLI required)
#   - Optional: gh CLI for authenticated private-repo access
#
# Configuration:
#   Place .apm-consumer.yml in your repo root (or uses defaults).
# ==============================================================================

[CmdletBinding()]
param(
    [switch]$Force,
    [switch]$NoCommitInstructions,
    [switch]$Gitignore
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ConsumerRoot = (Get-Location).Path
$ConfigFile   = Join-Path $ConsumerRoot '.apm-consumer.yml'
$LockFile     = Join-Path $ConsumerRoot '.apm-lock.json'

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
function Write-Info    { param($msg) Write-Host "[APM] $msg" -ForegroundColor Cyan }
function Write-Success { param($msg) Write-Host "[APM] $msg" -ForegroundColor Green }
function Write-Warn    { param($msg) Write-Host "[APM] $msg" -ForegroundColor Yellow }
function Write-Err     { param($msg) Write-Host "[APM] $msg" -ForegroundColor Red }

function Read-Config {
    param([string]$Key, [string]$Default)
    if (Test-Path $ConfigFile) {
        $line = Get-Content $ConfigFile |
            Where-Object { $_ -match "^\s*${Key}:\s*(.+)" } |
            Select-Object -First 1
        if ($line -match "^\s*${Key}:\s*(.+)") {
            $val = $Matches[1].Trim().Trim('"').Trim("'")
            if ($val) { return $val }
        }
    }
    return $Default
}

function Get-Sha256 {
    param([string]$Path)
    return (Get-FileHash -Path $Path -Algorithm SHA256).Hash.ToLower()
}

# ---------------------------------------------------------------------------
# Read config
# ---------------------------------------------------------------------------
$SourceRepo          = Read-Config 'repo'                      'janvanwassenhove/CognitiveHub'
$TargetVersion       = Read-Config 'version'                   'latest'
$Provider            = Read-Config 'provider'                  'github-copilot'
$IncludeKnowledge    = Read-Config 'include-knowledge'         'true'
$IncludeCli          = Read-Config 'include-cli'               'false'
$MergeCopilot        = Read-Config 'merge-copilot-instructions' 'true'
$UpdateGitignore     = if ($Gitignore) { 'true' } else { Read-Config 'update-gitignore' 'false' }

Write-Info "Source:   $SourceRepo"
Write-Info "Version:  $TargetVersion"
Write-Info "Provider: $Provider"
Write-Info ""

# ---------------------------------------------------------------------------
# Resolve version and tarball URL
# ---------------------------------------------------------------------------
Write-Info "Resolving version..."

$useGh = $null -ne (Get-Command gh -ErrorAction SilentlyContinue)

if ($TargetVersion -eq 'latest') {
    if ($useGh) {
        $ResolvedVersion = gh release list --repo $SourceRepo --limit 1 --json tagName --jq '.[0].tagName' 2>$null
    } else {
        $apiUrl = "https://api.github.com/repos/$SourceRepo/releases/latest"
        $rel = Invoke-RestMethod -Uri $apiUrl -Headers @{ 'User-Agent' = 'apm-install' }
        $ResolvedVersion = $rel.tag_name
    }
    if (-not $ResolvedVersion) {
        Write-Err "Could not resolve latest release from $SourceRepo"
        exit 1
    }
} else {
    $ResolvedVersion = if ($TargetVersion.StartsWith('v')) { $TargetVersion } else { "v$TargetVersion" }
}

$VersionDisplay = $ResolvedVersion.TrimStart('v')
Write-Info "Resolved: v$VersionDisplay"

# ---------------------------------------------------------------------------
# Download release tarball
# ---------------------------------------------------------------------------
$TmpDir = Join-Path ([System.IO.Path]::GetTempPath()) "apm-install-$([System.Guid]::NewGuid().ToString('N'))"
New-Item -ItemType Directory -Path $TmpDir | Out-Null

try {
    Write-Info "Downloading v$VersionDisplay..."

    $TarballName = "cognitive-hub-${VersionDisplay}.tar.gz"
    $TarballPath = Join-Path $TmpDir $TarballName

    if ($useGh) {
        gh release download $ResolvedVersion --repo $SourceRepo --pattern "cognitive-hub-*.tar.gz" --dir $TmpDir
        $TarballPath = Get-ChildItem -Path $TmpDir -Filter 'cognitive-hub-*.tar.gz' | Select-Object -First 1 -ExpandProperty FullName
    } else {
        # Fall back to GitHub API asset download (no authentication needed for public repos)
        $apiUrl  = "https://api.github.com/repos/$SourceRepo/releases/tags/$ResolvedVersion"
        $release = Invoke-RestMethod -Uri $apiUrl -Headers @{ 'User-Agent' = 'apm-install' }
        $asset   = $release.assets | Where-Object { $_.name -like 'cognitive-hub-*.tar.gz' } | Select-Object -First 1
        if (-not $asset) {
            Write-Err "No tarball asset found in release $ResolvedVersion"
            exit 1
        }
        Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $TarballPath -UseBasicParsing
    }

    if (-not (Test-Path $TarballPath)) {
        Write-Err "Download failed — tarball not found at: $TarballPath"
        exit 1
    }

    # ---------------------------------------------------------------------------
    # Extract (tar.exe ships with Windows 10+)
    # ---------------------------------------------------------------------------
    Write-Info "Extracting..."
    $ExtractDir = Join-Path $TmpDir 'cognitive-hub'
    & tar -xzf $TarballPath -C $TmpDir
    if (-not (Test-Path $ExtractDir)) {
        Write-Err "Unexpected tarball structure — expected 'cognitive-hub/' root inside archive"
        exit 1
    }

    # ---------------------------------------------------------------------------
    # Install helpers
    # ---------------------------------------------------------------------------
    $InstalledFiles = [System.Collections.Generic.List[string]]::new()
    $SkippedFiles   = [System.Collections.Generic.List[string]]::new()

    # Load existing lock checksums
    $ExistingChecksums = @{}
    if (Test-Path $LockFile) {
        try {
            $lock = Get-Content $LockFile -Raw | ConvertFrom-Json
            foreach ($f in $lock.files) {
                $ExistingChecksums[$f.path] = $f.sha256
            }
        } catch { }
    }

    function Install-Path {
        param([string]$Src, [string]$Dest)

        if (-not (Test-Path $Src)) { return }

        if (Test-Path $Src -PathType Container) {
            $files = Get-ChildItem -Path $Src -Recurse -File
            foreach ($file in $files) {
                $rel    = $file.FullName.Substring($Src.Length).TrimStart('\', '/')
                $target = Join-Path $Dest $rel
                $consumerRel = $target.Substring($ConsumerRoot.Length).TrimStart('\', '/') -replace '\\','/'

                New-Item -ItemType Directory -Force -Path (Split-Path $target) | Out-Null

                $lockedHash = $ExistingChecksums[$consumerRel]
                if (-not $Force -and $lockedHash -and (Test-Path $target)) {
                    $currentHash = Get-Sha256 $target
                    if ($currentHash -ne $lockedHash) {
                        Write-Warn "Skipping locally modified: $consumerRel (use -Force to overwrite)"
                        $SkippedFiles.Add($consumerRel) | Out-Null
                        $InstalledFiles.Add($consumerRel) | Out-Null
                        continue
                    }
                }
                Copy-Item -Path $file.FullName -Destination $target -Force
                $InstalledFiles.Add($consumerRel) | Out-Null
            }
        } else {
            $consumerRel = $Dest.Substring($ConsumerRoot.Length).TrimStart('\', '/') -replace '\\','/'
            New-Item -ItemType Directory -Force -Path (Split-Path $Dest) | Out-Null

            $lockedHash = $ExistingChecksums[$consumerRel]
            if (-not $Force -and $lockedHash -and (Test-Path $Dest)) {
                $currentHash = Get-Sha256 $Dest
                if ($currentHash -ne $lockedHash) {
                    Write-Warn "Skipping locally modified: $consumerRel (use -Force to overwrite)"
                    $SkippedFiles.Add($consumerRel) | Out-Null
                    $InstalledFiles.Add($consumerRel) | Out-Null
                    return
                }
            }
            Copy-Item -Path $Src -Destination $Dest -Force
            $InstalledFiles.Add($consumerRel) | Out-Null
        }
    }

    # ---------------------------------------------------------------------------
    # Install everything under .github/ — no .apm/ or knowledge/ at root
    # ---------------------------------------------------------------------------
    Write-Info "Installing GitHub Copilot agents, prompts, and instructions..."
    Install-Path (Join-Path $ExtractDir '.github\agents')       (Join-Path $ConsumerRoot '.github\agents')
    Install-Path (Join-Path $ExtractDir '.github\prompts')      (Join-Path $ConsumerRoot '.github\prompts')
    Install-Path (Join-Path $ExtractDir '.github\instructions') (Join-Path $ConsumerRoot '.github\instructions')

    Write-Info "Installing skills, workflows, and contexts into .github\apm\..."
    Install-Path (Join-Path $ExtractDir '.apm\skills')    (Join-Path $ConsumerRoot '.github\apm\skills')
    Install-Path (Join-Path $ExtractDir '.apm\workflows') (Join-Path $ConsumerRoot '.github\apm\workflows')
    Install-Path (Join-Path $ExtractDir '.apm\contexts')  (Join-Path $ConsumerRoot '.github\apm\contexts')

    # Merge copilot-instructions.md
    if ($MergeCopilot -eq 'true' -and -not $NoCommitInstructions) {
        $CopilotSrc  = Join-Path $ExtractDir '.github\copilot-instructions.md'
        $CopilotDest = Join-Path $ConsumerRoot '.github\copilot-instructions.md'

        if (Test-Path $CopilotSrc) {
            New-Item -ItemType Directory -Force -Path (Split-Path $CopilotDest) | Out-Null
            $HubContent    = Get-Content $CopilotSrc -Raw
            $BeginMarker   = '<!-- BEGIN CognitiveHub APM -->'
            $EndMarker     = '<!-- END CognitiveHub APM -->'

            if (Test-Path $CopilotDest) {
                $existing = Get-Content $CopilotDest -Raw
                if ($existing -match [regex]::Escape($BeginMarker)) {
                    # Replace delimited block
                    $pattern  = "(?s)$([regex]::Escape($BeginMarker)).*?$([regex]::Escape($EndMarker))"
                    $replacement = "$BeginMarker`n$HubContent`n$EndMarker"
                    $existing -replace $pattern, $replacement | Set-Content $CopilotDest -NoNewline
                    Write-Info "Updated copilot-instructions.md (replaced hub section)."
                } else {
                    # Append delimited block
                    "`n$BeginMarker`n$HubContent`n$EndMarker" | Add-Content $CopilotDest
                    Write-Info "Updated copilot-instructions.md (appended hub section)."
                }
            } else {
                "$BeginMarker`n$HubContent`n$EndMarker" | Set-Content $CopilotDest
                Write-Info "Created copilot-instructions.md."
            }
            $InstalledFiles.Add('.github/copilot-instructions.md') | Out-Null
        }
    }

    # ---------------------------------------------------------------------------
    # Knowledge base — installed into .github/apm/knowledge/
    # ---------------------------------------------------------------------------
    if ($IncludeKnowledge -eq 'true') {
        Write-Info "Installing knowledge base into .github\apm\knowledge\..."
        Install-Path (Join-Path $ExtractDir 'knowledge') (Join-Path $ConsumerRoot '.github\apm\knowledge')
    }

    # ---------------------------------------------------------------------------
    # Rewrite internal paths in installed .github/ files
    # Hub source uses .apm/ and knowledge/ roots; consumer uses .github/apm/
    # ---------------------------------------------------------------------------
    Write-Info "Rewriting internal paths in agents and prompts..."
    $rewriteDirs = @(
        (Join-Path $ConsumerRoot '.github\agents')
        (Join-Path $ConsumerRoot '.github\prompts')
        (Join-Path $ConsumerRoot '.github\instructions')
    )
    foreach ($dir in $rewriteDirs) {
        if (-not (Test-Path $dir)) { continue }
        Get-ChildItem -Path $dir -Filter '*.md' -Recurse | ForEach-Object {
            $c = Get-Content $_.FullName -Raw
            $c = $c -replace [regex]::Escape('.apm/skills/'),    '.github/apm/skills/'
            $c = $c -replace [regex]::Escape('.apm/workflows/'), '.github/apm/workflows/'
            $c = $c -replace [regex]::Escape('.apm/contexts/'),  '.github/apm/contexts/'
            $c = $c -replace [regex]::Escape('.apm/agents/'),    '.github/agents/'
            # knowledge/ only when not already prefixed (avoid double-rewrite)
            $c = $c -replace '(?<!\.github/apm/)(?<![/\w])knowledge/', '.github/apm/knowledge/'
            Set-Content $_.FullName $c -NoNewline
        }
    }

    # ---------------------------------------------------------------------------
    # Claude Code provider
    # ---------------------------------------------------------------------------
    if ($Provider -eq 'claude-code' -or $Provider -eq 'all') {
        Write-Info "Installing Claude Code provider..."
        Install-Path (Join-Path $ExtractDir 'providers\claude-code') (Join-Path $ConsumerRoot 'providers\claude-code')
    }

    # ---------------------------------------------------------------------------
    # CLI runner
    # ---------------------------------------------------------------------------
    if ($IncludeCli -eq 'true') {
        Write-Info "Installing CLI runner..."
        Install-Path (Join-Path $ExtractDir 'providers\cli') (Join-Path $ConsumerRoot 'providers\cli')
    }

    # ---------------------------------------------------------------------------
    # Update .gitignore
    # ---------------------------------------------------------------------------
    if ($UpdateGitignore -eq 'true') {
        $GitignoreFile = Join-Path $ConsumerRoot '.gitignore'
        $BeginMarker   = '# BEGIN CognitiveHub APM'
        $EndMarker     = '# END CognitiveHub APM'

        $topLevelEntries = $InstalledFiles |
            ForEach-Object { ($_ -split '/')[0] } |
            Sort-Object -Unique |
            ForEach-Object {
                $top = Join-Path $ConsumerRoot $_
                if (Test-Path $top -PathType Container) { "/$_/" } else { "/$_" }
            }
        $topLevelEntries += '/.apm-lock.json'

        $newBlock = ($BeginMarker, ($topLevelEntries -join "`n"), $EndMarker) -join "`n"

        if (Test-Path $GitignoreFile) {
            $content = Get-Content $GitignoreFile -Raw
            if ($content -match [regex]::Escape($BeginMarker)) {
                $pattern = "(?s)$([regex]::Escape($BeginMarker)).*?$([regex]::Escape($EndMarker))"
                $content -replace $pattern, $newBlock | Set-Content $GitignoreFile -NoNewline
            } else {
                "`n$newBlock" | Add-Content $GitignoreFile
            }
        } else {
            $newBlock | Set-Content $GitignoreFile
        }
        Write-Info "Updated .gitignore."
    }

    # ---------------------------------------------------------------------------
    # Write lock file
    # ---------------------------------------------------------------------------
    Write-Info "Writing lock file..."
    $fileEntries = $InstalledFiles | ForEach-Object {
        $full = Join-Path $ConsumerRoot ($_ -replace '/', '\')
        if (Test-Path $full -PathType Leaf) {
            $hash = if ($SkippedFiles -contains $_ -and $ExistingChecksums[$_]) {
                $ExistingChecksums[$_]
            } else {
                Get-Sha256 $full
            }
            [PSCustomObject]@{ path = $_; sha256 = $hash }
        }
    } | Where-Object { $_ }

    [PSCustomObject]@{
        version   = $VersionDisplay
        source    = $SourceRepo
        provider  = $Provider
        installed = (Get-Date -Format 'yyyy-MM-ddTHH:mm:ssZ' -AsUTC)
        files     = $fileEntries
    } | ConvertTo-Json -Depth 5 | Set-Content $LockFile

    # ---------------------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------------------
    Write-Host ""
    Write-Success "Cognitive Hub v$VersionDisplay installed successfully!"
    Write-Host ""
    Write-Info "Installed $($InstalledFiles.Count) files."
    if ($SkippedFiles.Count -gt 0) {
        Write-Warn "Skipped $($SkippedFiles.Count) locally modified file(s). Use -Force to overwrite."
    }
    Write-Info "Lock file: .apm-lock.json"
    Write-Host ""
    Write-Info "Everything installed under .github/:"
    Write-Info "  .github/agents/        — @agents for Copilot Chat"
    Write-Info "  .github/prompts/       — /prompts for Copilot Chat"
    Write-Info "  .github/instructions/  — auto-applied instructions"
    Write-Info "  .github/apm/skills/    — skill definitions"
    Write-Info "  .github/apm/workflows/ — workflow definitions"
    Write-Info "  .github/apm/knowledge/ — principles and playbooks"
    Write-Host ""
    Write-Info "Next steps:"
    Write-Info "  1. Reload VS Code to activate agents and prompts"
    if ($UpdateGitignore -eq 'true') {
        Write-Info "  2. Commit: git add .apm-consumer.yml .apm-lock.json .gitignore"
    } else {
        Write-Info "  2. Commit: git add .github/ .apm/ .apm-consumer.yml .apm-lock.json knowledge/"
    }
    Write-Info "  3. Push to share with your team"

} finally {
    Remove-Item -Recurse -Force $TmpDir -ErrorAction SilentlyContinue
}
