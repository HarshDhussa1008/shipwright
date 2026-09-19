#!/usr/bin/env bash
# Install shipwright into your project
# Usage: ./install.sh [--project-dir /path/to/your/project]

set -euo pipefail

FRAMEWORK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_SRC="$FRAMEWORK_DIR/skills"
USER_SKILLS_DIR="$HOME/.claude/skills"

# Determine target project directory
PROJECT_DIR="${1:-$(pwd)}"
if [[ "$1" == "--project-dir" && -n "${2:-}" ]]; then
  PROJECT_DIR="$2"
fi

echo "=== shipwright installer ==="
echo "Framework: $FRAMEWORK_DIR"
echo "Project:   $PROJECT_DIR"
echo ""

# 1. Copy skills to ~/.claude/skills/ (user-level)
echo "Installing skills to $USER_SKILLS_DIR ..."
mkdir -p "$USER_SKILLS_DIR"
for skill_dir in "$SKILLS_SRC"/*/; do
  skill_name=$(basename "$skill_dir")
  dest="$USER_SKILLS_DIR/$skill_name"
  if [[ -d "$dest" ]]; then
    echo "  [SKIP] $skill_name already exists at $dest (delete it first to reinstall)"
  else
    cp -r "$skill_dir" "$dest"
    echo "  [OK]   $skill_name → $dest"
  fi
done

# 2. Copy .claude/ directory into project
echo ""
echo "Installing hooks and config to $PROJECT_DIR/.claude ..."
mkdir -p "$PROJECT_DIR/.claude/hooks"

# Copy hooks (don't overwrite existing)
for hook in "$FRAMEWORK_DIR/.claude/hooks/"*.py; do
  hook_name=$(basename "$hook")
  dest="$PROJECT_DIR/.claude/hooks/$hook_name"
  if [[ -f "$dest" ]]; then
    echo "  [SKIP] hooks/$hook_name already exists"
  else
    cp "$hook" "$dest"
    echo "  [OK]   hooks/$hook_name"
  fi
done

# Copy tools (dashboard)
mkdir -p "$PROJECT_DIR/.claude/tools"
for tool in "$FRAMEWORK_DIR/.claude/tools/"*.py; do
  tool_name=$(basename "$tool")
  dest="$PROJECT_DIR/.claude/tools/$tool_name"
  if [[ -f "$dest" ]]; then
    echo "  [SKIP] tools/$tool_name already exists"
  else
    cp "$tool" "$dest"
    echo "  [OK]   tools/$tool_name"
  fi
done

# Copy framework.json if not present
if [[ ! -f "$PROJECT_DIR/.claude/framework.json" ]]; then
  cp "$FRAMEWORK_DIR/.claude/framework.json" "$PROJECT_DIR/.claude/framework.json"
  echo "  [OK]   framework.json"
else
  echo "  [SKIP] framework.json already exists"
fi

# Copy empty state files and .gitignore if not present
for state_file in checkpoint.json task_state.json anti_pattern_registry.json amendments_pending.json .gitignore; do
  if [[ ! -f "$PROJECT_DIR/.claude/$state_file" ]]; then
    cp "$FRAMEWORK_DIR/.claude/$state_file" "$PROJECT_DIR/.claude/$state_file"
    echo "  [OK]   $state_file"
  fi
done

# Copy settings.json if not present
if [[ ! -f "$PROJECT_DIR/.claude/settings.json" ]]; then
  cp "$FRAMEWORK_DIR/.claude/settings.json" "$PROJECT_DIR/.claude/settings.json"
  echo "  [OK]   settings.json"
else
  echo "  [SKIP] settings.json already exists — merge hooks manually if needed"
  echo "         See $FRAMEWORK_DIR/.claude/settings.json for the hooks AND statusLine config"
  echo "         The statusLine block is required for budget alerts — it is the only"
  echo "         surface that exposes rate_limits (hooks do not receive them)."
fi

# 3. Copy CLAUDE.md template if project doesn't have one
if [[ ! -f "$PROJECT_DIR/CLAUDE.md" ]]; then
  cp "$FRAMEWORK_DIR/CLAUDE.md.template" "$PROJECT_DIR/CLAUDE.md"
  echo "  [OK]   CLAUDE.md (from template — fill in placeholders)"
else
  echo "  [SKIP] CLAUDE.md already exists"
fi

echo ""
echo "=== Next steps ==="
echo "1. Edit $PROJECT_DIR/.claude/framework.json with your project settings"
echo "   - Set project_name, jira_project_key (or jira_integration: false)"
echo "   - Set build_command to your deploy command"
echo "2. Fill in $PROJECT_DIR/CLAUDE.md placeholders"
echo "3. Open Claude Code in $PROJECT_DIR — skills: /design, /breakdown, /ship, /retro, /dashboard"
echo ""
echo "Optional: install Jira MCP for full Jira integration"
echo "  https://github.com/anthropics/anthropic-tools/tree/main/mcp-atlassian"
