# Install shipwright into your project
# Usage: .\install.ps1 [-ProjectDir C:\path\to\your\project]

param(
    [string]$ProjectDir = (Get-Location).Path
)

$FrameworkDir = $PSScriptRoot
$SkillsSrc = Join-Path $FrameworkDir "skills"
$UserSkillsDir = Join-Path $HOME ".claude\skills"

Write-Host "=== shipwright installer ===" -ForegroundColor Cyan
Write-Host "Framework: $FrameworkDir"
Write-Host "Project:   $ProjectDir"
Write-Host ""

# 1. Copy skills to ~/.claude/skills/ (user-level)
Write-Host "Installing skills to $UserSkillsDir ..."
if (-not (Test-Path $UserSkillsDir)) { New-Item -ItemType Directory -Force $UserSkillsDir | Out-Null }

Get-ChildItem $SkillsSrc -Directory | ForEach-Object {
    $skillName = $_.Name
    $dest = Join-Path $UserSkillsDir $skillName
    if (Test-Path $dest) {
        Write-Host "  [SKIP] $skillName already exists at $dest (delete it first to reinstall)" -ForegroundColor Yellow
    } else {
        Copy-Item -Recurse $_.FullName $dest
        Write-Host "  [OK]   $skillName -> $dest" -ForegroundColor Green
    }
}

# 2. Copy .claude/ into project
Write-Host ""
Write-Host "Installing hooks and config to $ProjectDir\.claude ..."
$claudeDir = Join-Path $ProjectDir ".claude"
$hooksDir = Join-Path $claudeDir "hooks"
if (-not (Test-Path $hooksDir)) { New-Item -ItemType Directory -Force $hooksDir | Out-Null }

# Copy hooks
Get-ChildItem (Join-Path $FrameworkDir ".claude\hooks") -Filter "*.py" | ForEach-Object {
    $dest = Join-Path $hooksDir $_.Name
    if (Test-Path $dest) {
        Write-Host "  [SKIP] hooks\$($_.Name) already exists" -ForegroundColor Yellow
    } else {
        Copy-Item $_.FullName $dest
        Write-Host "  [OK]   hooks\$($_.Name)" -ForegroundColor Green
    }
}

# Copy framework.json
$frameworkJsonDest = Join-Path $claudeDir "framework.json"
if (-not (Test-Path $frameworkJsonDest)) {
    Copy-Item (Join-Path $FrameworkDir ".claude\framework.json") $frameworkJsonDest
    Write-Host "  [OK]   framework.json" -ForegroundColor Green
} else {
    Write-Host "  [SKIP] framework.json already exists" -ForegroundColor Yellow
}

# Copy empty state files and .gitignore
"checkpoint.json", "task_state.json", "anti_pattern_registry.json", ".gitignore" | ForEach-Object {
    $dest = Join-Path $claudeDir $_
    if (-not (Test-Path $dest)) {
        Copy-Item (Join-Path $FrameworkDir ".claude\$_") $dest
        Write-Host "  [OK]   $_" -ForegroundColor Green
    }
}

# Copy settings.json
$settingsDest = Join-Path $claudeDir "settings.json"
if (-not (Test-Path $settingsDest)) {
    Copy-Item (Join-Path $FrameworkDir ".claude\settings.json") $settingsDest
    Write-Host "  [OK]   settings.json" -ForegroundColor Green
} else {
    Write-Host "  [SKIP] settings.json already exists — merge hooks manually if needed" -ForegroundColor Yellow
    Write-Host "         See $FrameworkDir\.claude\settings.json for the hook config" -ForegroundColor Yellow
}

# Copy CLAUDE.md template
$claudeMdDest = Join-Path $ProjectDir "CLAUDE.md"
if (-not (Test-Path $claudeMdDest)) {
    Copy-Item (Join-Path $FrameworkDir "CLAUDE.md.template") $claudeMdDest
    Write-Host "  [OK]   CLAUDE.md (from template — fill in placeholders)" -ForegroundColor Green
} else {
    Write-Host "  [SKIP] CLAUDE.md already exists" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== Next steps ===" -ForegroundColor Cyan
Write-Host "1. Edit $claudeDir\framework.json with your project settings"
Write-Host "   - Set project_name, jira_project_key (or jira_integration: false)"
Write-Host "   - Set build_command to your deploy command"
Write-Host "2. Fill in $claudeMdDest placeholders"
Write-Host "3. Open Claude Code in $ProjectDir — skills will be available as /design, /breakdown, /ship, /standup, /retro"
Write-Host ""
Write-Host "Optional: install Jira MCP for full Jira integration"
Write-Host "  https://github.com/anthropics/anthropic-tools/tree/main/mcp-atlassian"
