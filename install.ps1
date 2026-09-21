# Install (or update) shipwright in your project
# Usage: .\install.ps1 [-ProjectDir C:\path\to\your\project] [-Update]
#
# Default: first-time install. Never overwrites anything that already exists --
# every file is treated as "seed once, then it's yours."
#
# -Update: re-run against an already-installed project to pick up framework fixes.
# Only framework-owned files (hooks/*.py, tools/*.py, skills) are force-overwritten.
# Your config and state (framework.json, settings.json, task_state.json, checkpoint.json,
# anti_pattern_registry.json, amendments_pending.json, CLAUDE.md) are NEVER touched by
# -Update -- those are yours from the moment they're first created.
# .claude/.gitignore is a third case: merged, not overwritten -- any new framework
# patterns (e.g. a new state file added in a later shipwright version) get appended,
# anything you added on top of it stays.

param(
    [string]$ProjectDir = (Get-Location).Path,
    [switch]$Update
)

$FrameworkDir = $PSScriptRoot
$SkillsSrc = Join-Path $FrameworkDir "skills"
$UserSkillsDir = Join-Path $HOME ".claude\skills"

function Merge-GitIgnore {
    param([string]$SrcPath, [string]$DestPath)
    if (-not (Test-Path $DestPath)) {
        Copy-Item $SrcPath $DestPath
        Write-Host "  [OK]   .gitignore" -ForegroundColor Green
        return
    }
    $destLines = Get-Content $DestPath
    $destSet = [System.Collections.Generic.HashSet[string]]::new([string[]]$destLines)
    $added = @()
    foreach ($line in (Get-Content $SrcPath)) {
        $trimmed = $line.Trim()
        if ($trimmed -eq "" -or $trimmed.StartsWith("#")) { continue }
        if (-not $destSet.Contains($line)) { $added += $line }
    }
    if ($added.Count -gt 0) {
        Add-Content -Path $DestPath -Value ""
        Add-Content -Path $DestPath -Value $added
        Write-Host "  [MERGE] .gitignore - added $($added.Count) missing pattern(s)" -ForegroundColor Green
    } else {
        Write-Host "  [SKIP] .gitignore already up to date" -ForegroundColor Yellow
    }
}

Write-Host "=== shipwright installer $(if ($Update) { '(update mode)' }) ===" -ForegroundColor Cyan
Write-Host "Framework: $FrameworkDir"
Write-Host "Project:   $ProjectDir"
Write-Host ""

# 1. Skills (~/.claude/skills/, user-level) -- framework-owned, force-overwritten on -Update
Write-Host "Installing skills to $UserSkillsDir ..."
if (-not (Test-Path $UserSkillsDir)) { New-Item -ItemType Directory -Force $UserSkillsDir | Out-Null }

Get-ChildItem $SkillsSrc -Directory | ForEach-Object {
    $skillName = $_.Name
    $dest = Join-Path $UserSkillsDir $skillName
    if (Test-Path $dest) {
        if ($Update) {
            Remove-Item -Recurse -Force $dest
            Copy-Item -Recurse $_.FullName $dest
            Write-Host "  [UPDATED] $skillName -> $dest" -ForegroundColor Green
        } else {
            Write-Host "  [SKIP] $skillName already exists at $dest (delete it first to reinstall, or use -Update)" -ForegroundColor Yellow
        }
    } else {
        Copy-Item -Recurse $_.FullName $dest
        Write-Host "  [OK]   $skillName -> $dest" -ForegroundColor Green
    }
}

# 2. Copy .claude/ into project
$claudeDir = Join-Path $ProjectDir ".claude"
Write-Host ""
Write-Host "Installing hooks and config to $claudeDir ..."
$hooksDir = Join-Path $claudeDir "hooks"
if (-not (Test-Path $hooksDir)) { New-Item -ItemType Directory -Force $hooksDir | Out-Null }

# Hooks -- framework-owned, force-overwritten on -Update
Get-ChildItem (Join-Path $FrameworkDir ".claude\hooks") -Filter "*.py" | ForEach-Object {
    $dest = Join-Path $hooksDir $_.Name
    if (Test-Path $dest) {
        if ($Update) {
            Copy-Item $_.FullName $dest -Force
            Write-Host "  [UPDATED] hooks\$($_.Name)" -ForegroundColor Green
        } else {
            Write-Host "  [SKIP] hooks\$($_.Name) already exists" -ForegroundColor Yellow
        }
    } else {
        Copy-Item $_.FullName $dest
        Write-Host "  [OK]   hooks\$($_.Name)" -ForegroundColor Green
    }
}

# Tools (dashboard) -- framework-owned, force-overwritten on -Update
$toolsDir = Join-Path $claudeDir "tools"
if (-not (Test-Path $toolsDir)) { New-Item -ItemType Directory -Force $toolsDir | Out-Null }
Get-ChildItem (Join-Path $FrameworkDir ".claude\tools") -Filter "*.py" | ForEach-Object {
    $dest = Join-Path $toolsDir $_.Name
    if (Test-Path $dest) {
        if ($Update) {
            Copy-Item $_.FullName $dest -Force
            Write-Host "  [UPDATED] tools\$($_.Name)" -ForegroundColor Green
        } else {
            Write-Host "  [SKIP] tools\$($_.Name) already exists" -ForegroundColor Yellow
        }
    } else {
        Copy-Item $_.FullName $dest
        Write-Host "  [OK]   tools\$($_.Name)" -ForegroundColor Green
    }
}

# framework.json -- user-owned, never touched once it exists, -Update included
$frameworkJsonDest = Join-Path $claudeDir "framework.json"
if (-not (Test-Path $frameworkJsonDest)) {
    Copy-Item (Join-Path $FrameworkDir ".claude\framework.json") $frameworkJsonDest
    Write-Host "  [OK]   framework.json" -ForegroundColor Green
} else {
    Write-Host "  [SKIP] framework.json already exists (user-owned, never auto-updated)" -ForegroundColor Yellow
}

# Empty state files -- user-owned runtime state, never touched once they exist
"checkpoint.json", "task_state.json", "anti_pattern_registry.json", "amendments_pending.json" | ForEach-Object {
    $dest = Join-Path $claudeDir $_
    if (-not (Test-Path $dest)) {
        Copy-Item (Join-Path $FrameworkDir ".claude\$_") $dest
        Write-Host "  [OK]   $_" -ForegroundColor Green
    } else {
        Write-Host "  [SKIP] $_ already exists (user-owned, never auto-updated)" -ForegroundColor Yellow
    }
}

# .gitignore -- merged (new framework patterns added, your own entries kept), always
Merge-GitIgnore (Join-Path $FrameworkDir ".claude\.gitignore") (Join-Path $claudeDir ".gitignore")

# settings.json -- user-owned (often hand-merged), never touched once it exists
$settingsDest = Join-Path $claudeDir "settings.json"
if (-not (Test-Path $settingsDest)) {
    Copy-Item (Join-Path $FrameworkDir ".claude\settings.json") $settingsDest
    Write-Host "  [OK]   settings.json" -ForegroundColor Green
} else {
    Write-Host "  [SKIP] settings.json already exists - merge hooks manually if needed" -ForegroundColor Yellow
    Write-Host "         See $FrameworkDir\.claude\settings.json for the hooks AND statusLine config" -ForegroundColor Yellow
    Write-Host "         The statusLine block is required for budget alerts - it is the only" -ForegroundColor Yellow
    Write-Host "         surface that exposes rate_limits (hooks do not receive them)." -ForegroundColor Yellow
}

# CLAUDE.md -- user-owned, never touched once it exists
$claudeMdDest = Join-Path $ProjectDir "CLAUDE.md"
if (-not (Test-Path $claudeMdDest)) {
    Copy-Item (Join-Path $FrameworkDir "CLAUDE.md.template") $claudeMdDest
    Write-Host "  [OK]   CLAUDE.md (from template - fill in placeholders)" -ForegroundColor Green
} else {
    Write-Host "  [SKIP] CLAUDE.md already exists" -ForegroundColor Yellow
}

Write-Host ""
if ($Update) {
    Write-Host "=== Update complete ===" -ForegroundColor Cyan
    Write-Host "Hooks, tools, and skills are current. Config and state were left untouched."
} else {
    Write-Host "=== Next steps ===" -ForegroundColor Cyan
    Write-Host "1. Edit $claudeDir\framework.json with your project settings"
    Write-Host "   - Set project_name, jira_project_key (or jira_integration: false)"
    Write-Host "   - Set build_command to your deploy command"
    Write-Host "2. Fill in $claudeMdDest placeholders"
    Write-Host "3. Open Claude Code in $ProjectDir - skills: /design, /breakdown, /ship, /retro, /dashboard"
    Write-Host ""
    Write-Host "Later, re-run with -Update to pick up framework fixes without touching your config."
    Write-Host ""
    Write-Host "Optional: install Jira MCP for full Jira integration"
    Write-Host "  https://github.com/anthropics/anthropic-tools/tree/main/mcp-atlassian"
}
