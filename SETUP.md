# Setup Guide

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| [Claude Code](https://claude.ai/code) | CLI, desktop app, or IDE extension |
| Python 3.10+ | Must be on PATH in your project's venv |
| `ruff` | `pip install ruff` — used by quality gate hook |
| `mypy` | `pip install mypy` — used by quality gate hook |
| Jira MCP (optional) | Required for Jira integration — see below |
| Slack MCP (optional) | Required for deploy notifications |

## Installation

### 1. Clone shipwright

```bash
git clone https://github.com/HarshDhussa1008/shipwright
```

### 2. Run the installer

**macOS / Linux:**
```bash
cd shipwright
chmod +x install.sh
./install.sh --project-dir /path/to/your/project
```

**Windows:**
```powershell
cd shipwright
.\install.ps1 -ProjectDir C:\path\to\your\project
```

### 3. Configure your project

Edit `.claude/framework.json` in your project root:

```json
{
  "project_name": "payments-api",
  "jira_project_key": "PAY",
  "jira_integration": true,
  "slack_mcp_channel": "#deployments",
  "slack_integration": false,
  "build_command": "./build.sh staging",
  "sdd_path": "docs/sdd",
  "languages": ["python"]
}
```

**Config fields:**

| Field | Default | Description |
|-------|---------|-------------|
| `project_name` | `"my-project"` | Display name used in reports and Jira comments |
| `jira_project_key` | `null` | Jira project key (e.g., `"PAY"`, `"BACKEND"`) |
| `jira_integration` | `false` | Enable/disable all Jira steps |
| `slack_mcp_channel` | `null` | Slack channel for deploy notifications |
| `slack_integration` | `false` | Enable/disable Slack notifications |
| `build_command` | (echo stub) | Shell command to build and deploy |
| `test_command` | pytest | Test suite command, run by /ship Gate 1 |
| `lint_command` | ruff | Linter with a `{file}` placeholder. `null` to skip |
| `typecheck_command` | mypy | Type checker with a `{file}` placeholder. `null` to skip |
| `gate_extensions` | `[".py"]` | File extensions the quality gate applies to |
| `budget_alert_threshold` | `95` | Rate-limit percentage that trips the checkpoint directive |
| `sdd_path` | `"docs/sdd"` | Directory where SDDs are saved (relative to project root) |
| `memory_path` | `null` | Override memory directory (auto-derived if null) |
| `languages` | `["python"]` | Informational tag for the project's languages |

### 4. Fill in CLAUDE.md

`CLAUDE.md` was copied from the template. Replace all `<PLACEHOLDER>` sections with your project's actual details. Claude Code reads this file at the start of every session.

### 5. Verify hooks and the statusline are wired

Open `.claude/settings.json` and confirm:
- `UserPromptSubmit` → `session_start.py`
- `PostToolUse` (Edit|Write) → `quality_gate.py`
- `Stop` → `stop_checklist.py`
- `statusLine` → `budget_sentinel.py`

If you already had a `settings.json`, merge both the `hooks` and `statusLine` sections manually.

The `statusLine` entry is not cosmetic: it is the only surface that receives `rate_limits`, so without it the 95% budget alert never fires.

### 5b. Non-Python projects

The quality gate is command-driven. Point it at your toolchain:

```json
{
  "lint_command": "npx eslint --fix {file}",
  "typecheck_command": "npx tsc --noEmit",
  "gate_extensions": [".ts", ".tsx"]
}
```

Set either command to `null` to skip that check entirely.

## Jira MCP Setup (optional)

1. Follow the [Atlassian MCP setup guide](https://github.com/anthropics/anthropic-tools/tree/main/mcp-atlassian)
2. Set `jira_integration: true` in `framework.json`
3. Set `jira_project_key` to your Jira project key

The framework uses these MCP tools: `getJiraIssue`, `createJiraIssue`, `transitionJiraIssue`, `addCommentToJiraIssue`, `searchJiraIssuesUsingJql`.

## How the memory system works

Claude Code automatically creates a project memory directory at:
```
~/.claude/projects/<project-slug>/memory/
```

The `project-slug` is derived from your project's absolute path (path separators replaced with `-`). The `session_start.py` hook auto-detects this path — you don't need to configure it unless you want to override it with `memory_path` in `framework.json`.

Memories are `.md` files with YAML frontmatter (`type: user|feedback|project|reference`). The `/retro` and `/design` skills write them automatically. You can also write them manually with the `/remember` command.

## The dashboard

```bash
python .claude/tools/dashboard.py            # write .claude/dashboard.html
python .claude/tools/dashboard.py --serve    # localhost, 10s auto-refresh
```

Or just `/dashboard`. It is read-only, stdlib-only, and binds to `127.0.0.1`. Files dropped in `.claude/inbox/` are listed with repo-relative paths ready to reference in a prompt.

## Branch naming convention

The `/breakdown` skill derives the Jira ticket ID from the git branch name. For example:
- Branch `PROJ-123` → parent Jira key `PROJ-123`
- Branch `feature/PROJ-123-add-rate-limiting` → also works (regex extracts `PROJ-123`)

If your branch name doesn't contain a Jira ticket ID and `jira_integration: true`, `/breakdown` will ask you for one.

## Adding a custom skill

1. Create a directory: `~/.claude/skills/<skill-name>/SKILL.md`
2. Write your skill as a Markdown file (role, interaction protocol, rules)
3. It will be available as `/<skill-name>` in Claude Code immediately

See the existing `skills/` directory for examples of how to structure a skill.
