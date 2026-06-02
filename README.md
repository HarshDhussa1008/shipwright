# shipwright

A structured engineering pipeline for [Claude Code](https://claude.ai/code). Design → Break down → Implement → Review → Ship — with optional Jira integration at every step.

## What it is

A set of Claude Code **skills** (slash commands), **hooks** (automatic quality enforcement), and **state files** that turn Claude Code into a full engineering pipeline:

```
/design  →  /breakdown  →  implement  →  /review  →  /ship
              (Jira sync)                              (Jira close)
```

### Skills

| Command | What it does |
|---------|-------------|
| `/design` | Generate a System Design Document from a requirement or Jira ticket ID |
| `/breakdown` | Decompose an SDD into atomic tasks + Jira subtasks |
| `sdd-implementer` | Convert an SDD into production code |
| `/ship` | Gated deploy: tests → type check → review → build → Jira/Slack sync |
| `/standup` | Daily report from git history + task state + Jira drift detection |
| `/retro` | Structured retrospective → memories → CLAUDE.md update → Jira close |

### Hooks (automatic)

| Hook | Trigger | What it does |
|------|---------|-------------|
| `session_start.py` | First message of each session | Injects relevant memories + shows interrupted checkpoint |
| `quality_gate.py` | After every file edit | Runs linter + type checker, tracks anti-pattern registry |
| `stop_checklist.py` | When Claude finishes responding | Nudges for unstaged files, open tasks, unwritten memories |

## Prerequisites

- [Claude Code](https://claude.ai/code) installed and authenticated
- Python 3.10+ in your project's virtual environment
- `ruff` and `mypy` installed (for the quality gate hook)
- **Optional:** [Atlassian MCP](https://github.com/anthropics/anthropic-tools/tree/main/mcp-atlassian) for Jira integration
- **Optional:** Slack MCP for deploy notifications

## Installation

### macOS / Linux

```bash
git clone https://github.com/HarshDhussa1008/shipwright
cd shipwright
chmod +x install.sh
./install.sh
```

### Windows (PowerShell)

```powershell
git clone https://github.com/HarshDhussa1008/shipwright
cd shipwright
.\install.ps1
```

The installer:
1. Copies skills to `~/.claude/skills/` (user-level, available in all projects)
2. Copies the `.claude/` directory into your project (hooks + state files)
3. Patches `.claude/settings.json` with hook wiring

## Configuration

After installation, edit `.claude/framework.json` in your project root:

```json
{
  "project_name": "my-project",
  "jira_project_key": "PROJ",
  "jira_integration": true,
  "slack_mcp_channel": "#deployments",
  "slack_integration": false,
  "build_command": "./build.sh",
  "sdd_path": "docs/sdd",
  "languages": ["python"]
}
```

Set `jira_integration: false` to use the framework without Jira — all Jira steps are skipped gracefully.

## Usage

### Full pipeline

```
# 1. Design: generate SDD from Jira ticket or plain requirement
/design PROJ-123
/design "Add rate limiting to the payments API"

# 2. Break down: decompose SDD into tasks (+ Jira subtasks if configured)
/breakdown docs/sdd/rate-limiting.md

# 3. Implement: guided code generation from SDD
(invoke sdd-implementer skill)

# 4. Review + deploy
/ship staging
/ship prod

# 5. End of feature
/retro
```

### Daily workflow

```
/standup          # what did I do, what's next, any Jira drift?
/resume           # continue an interrupted session from checkpoint
```

## Project CLAUDE.md

Copy `CLAUDE.md.template` to your project root as `CLAUDE.md` and fill in the placeholders. Claude Code reads this file at the start of every session to understand your project's conventions.

## How it works

- **Skills** are Markdown files that Claude Code loads as slash commands. They contain role definitions, step-by-step protocols, and quality rules.
- **Hooks** are Python scripts that Claude Code executes automatically on specific events (file edits, session start, response end).
- **State files** (`checkpoint.json`, `task_state.json`) persist pipeline state across sessions so work survives interruptions.
- **Memory** files in `~/.claude/projects/<slug>/memory/` persist learnings across all sessions for a project.

## License

MIT
