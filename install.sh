#!/usr/bin/env bash
# Install (or update) shipwright in your project
# Usage: ./install.sh [--project-dir /path/to/your/project] [--update]
#
# Default: first-time install. Never overwrites anything that already exists --
# every file is treated as "seed once, then it's yours."
#
# --update: re-run against an already-installed project to pick up framework fixes.
# Only framework-owned files (hooks/*.py, tools/*.py, skills) are force-overwritten.
# Your config and state (framework.json, settings.json, task_state.json, checkpoint.json,
# anti_pattern_registry.json, amendments_pending.json, CLAUDE.md) are NEVER touched by
# --update -- those are yours from the moment they're first created.
# .claude/.gitignore is a third case: merged, not overwritten -- any new framework
# patterns get appended, anything you added on top of it stays.

set -euo pipefail

FRAMEWORK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_SRC="$FRAMEWORK_DIR/skills"
USER_SKILLS_DIR="$HOME/.claude/skills"

PROJECT_DIR="$(pwd)"
UPDATE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-dir)
      PROJECT_DIR="$2"
      shift 2
      ;;
    --update)
      UPDATE=1
      shift
      ;;
    *)
      PROJECT_DIR="$1"
      shift
      ;;
  esac
done

merge_gitignore() {
  local src="$1" dest="$2"
  if [[ ! -f "$dest" ]]; then
    cp "$src" "$dest"
    echo "  [OK]   .gitignore"
    return
  fi
  local added=0
  while IFS= read -r line; do
    line="${line%$'\r'}"  # strip CRLF's \r -- read only strips \n, and comparisons below are \r-sensitive
    [[ -z "$line" || "$line" == \#* ]] && continue
    if ! grep -qxF "$line" "$dest"; then
      [[ $added -eq 0 ]] && echo "" >> "$dest"
      echo "$line" >> "$dest"
      added=$((added + 1))
    fi
  done < "$src"
  if [[ $added -gt 0 ]]; then
    echo "  [MERGE] .gitignore — added $added missing pattern(s)"
  else
    echo "  [SKIP] .gitignore already up to date"
  fi
}

if [[ $UPDATE -eq 1 ]]; then
  echo "=== shipwright installer (update mode) ==="
else
  echo "=== shipwright installer ==="
fi
echo "Framework: $FRAMEWORK_DIR"
echo "Project:   $PROJECT_DIR"
echo ""

# 1. Skills (~/.claude/skills/, user-level) -- framework-owned, force-overwritten on --update
echo "Installing skills to $USER_SKILLS_DIR ..."
mkdir -p "$USER_SKILLS_DIR"
for skill_dir in "$SKILLS_SRC"/*/; do
  skill_name=$(basename "$skill_dir")
  dest="$USER_SKILLS_DIR/$skill_name"
  if [[ -d "$dest" ]]; then
    if [[ $UPDATE -eq 1 ]]; then
      rm -rf "$dest"
      cp -r "$skill_dir" "$dest"
      echo "  [UPDATED] $skill_name -> $dest"
    else
      echo "  [SKIP] $skill_name already exists at $dest (delete it first to reinstall, or use --update)"
    fi
  else
    cp -r "$skill_dir" "$dest"
    echo "  [OK]   $skill_name -> $dest"
  fi
done

# 2. Copy .claude/ directory into project
echo ""
echo "Installing hooks and config to $PROJECT_DIR/.claude ..."
mkdir -p "$PROJECT_DIR/.claude/hooks"

# Hooks -- framework-owned, force-overwritten on --update
for hook in "$FRAMEWORK_DIR/.claude/hooks/"*.py; do
  hook_name=$(basename "$hook")
  dest="$PROJECT_DIR/.claude/hooks/$hook_name"
  if [[ -f "$dest" ]]; then
    if [[ $UPDATE -eq 1 ]]; then
      cp "$hook" "$dest"
      echo "  [UPDATED] hooks/$hook_name"
    else
      echo "  [SKIP] hooks/$hook_name already exists"
    fi
  else
    cp "$hook" "$dest"
    echo "  [OK]   hooks/$hook_name"
  fi
done

# Tools (dashboard) -- framework-owned, force-overwritten on --update
mkdir -p "$PROJECT_DIR/.claude/tools"
for tool in "$FRAMEWORK_DIR/.claude/tools/"*.py; do
  tool_name=$(basename "$tool")
  dest="$PROJECT_DIR/.claude/tools/$tool_name"
  if [[ -f "$dest" ]]; then
    if [[ $UPDATE -eq 1 ]]; then
      cp "$tool" "$dest"
      echo "  [UPDATED] tools/$tool_name"
    else
      echo "  [SKIP] tools/$tool_name already exists"
    fi
  else
    cp "$tool" "$dest"
    echo "  [OK]   tools/$tool_name"
  fi
done

# framework.json -- user-owned, never touched once it exists, --update included
if [[ ! -f "$PROJECT_DIR/.claude/framework.json" ]]; then
  cp "$FRAMEWORK_DIR/.claude/framework.json" "$PROJECT_DIR/.claude/framework.json"
  echo "  [OK]   framework.json"
else
  echo "  [SKIP] framework.json already exists (user-owned, never auto-updated)"
fi

# Empty state files -- user-owned runtime state, never touched once they exist
for state_file in checkpoint.json task_state.json anti_pattern_registry.json amendments_pending.json; do
  if [[ ! -f "$PROJECT_DIR/.claude/$state_file" ]]; then
    cp "$FRAMEWORK_DIR/.claude/$state_file" "$PROJECT_DIR/.claude/$state_file"
    echo "  [OK]   $state_file"
  else
    echo "  [SKIP] $state_file already exists (user-owned, never auto-updated)"
  fi
done

# .gitignore -- merged (new framework patterns added, your own entries kept), always
merge_gitignore "$FRAMEWORK_DIR/.claude/.gitignore" "$PROJECT_DIR/.claude/.gitignore"

# settings.json -- user-owned (often hand-merged), never touched once it exists
if [[ ! -f "$PROJECT_DIR/.claude/settings.json" ]]; then
  cp "$FRAMEWORK_DIR/.claude/settings.json" "$PROJECT_DIR/.claude/settings.json"
  echo "  [OK]   settings.json"
else
  echo "  [SKIP] settings.json already exists — merge hooks manually if needed"
  echo "         See $FRAMEWORK_DIR/.claude/settings.json for the hooks AND statusLine config"
  echo "         The statusLine block is required for budget alerts — it is the only"
  echo "         surface that exposes rate_limits (hooks do not receive them)."
fi

# 3. CLAUDE.md -- user-owned, never touched once it exists
if [[ ! -f "$PROJECT_DIR/CLAUDE.md" ]]; then
  cp "$FRAMEWORK_DIR/CLAUDE.md.template" "$PROJECT_DIR/CLAUDE.md"
  echo "  [OK]   CLAUDE.md (from template — fill in placeholders)"
else
  echo "  [SKIP] CLAUDE.md already exists"
fi

echo ""
if [[ $UPDATE -eq 1 ]]; then
  echo "=== Update complete ==="
  echo "Hooks, tools, and skills are current. Config and state were left untouched."
else
  echo "=== Next steps ==="
  echo "1. Edit $PROJECT_DIR/.claude/framework.json with your project settings"
  echo "   - Set project_name, jira_project_key (or jira_integration: false)"
  echo "   - Set build_command to your deploy command"
  echo "2. Fill in $PROJECT_DIR/CLAUDE.md placeholders"
  echo "3. Open Claude Code in $PROJECT_DIR — skills: /design, /breakdown, /ship, /retro, /dashboard"
  echo ""
  echo "Later, re-run with --update to pick up framework fixes without touching your config."
  echo ""
  echo "Optional: install Jira MCP for full Jira integration"
  echo "  https://github.com/anthropics/anthropic-tools/tree/main/mcp-atlassian"
fi
