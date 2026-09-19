# shipwright

A structured engineering pipeline for [Claude Code](https://claude.ai/code). Design → Break down → Implement → Ship — with optional Jira integration at every step.

## What it is

A set of Claude Code **skills** (slash commands), **hooks** (automatic enforcement), a **statusline sentinel**, and **state files** that turn Claude Code into a full engineering pipeline:

```
/design  →  /breakdown  →  implement  →  /retro   →  /ship
(harden)     (Jira sync)   (bug loop)    (offered    (gates + Jira
                                          on done)     transitions)
```

`/ship` is the sole owner of Jira status transitions — staging moves subtasks to "In Review," prod moves them to "Done." `/retro` runs before a deploy has necessarily happened, so it only ever comments, never transitions; closing tickets there would fight `/ship`'s own transition on the next deploy.

The design principle: **you type commands only at the few moments you deliberately step back.** Everything else — capturing learnings, keeping the design doc honest, detecting drift, protecting work against a rate-limit breach — runs passively in hooks while you stay in the implementation loop.

### Skills

| Command | What it does |
|---------|-------------|
| `/design` | Generate an SDD, then harden it: a fresh-context subagent attacks it against 10 failure classes until it converges |
| `/breakdown` | Decompose a hardened SDD into atomic tasks + Jira subtasks. Refuses un-hardened SDDs |
| `sdd-implementer` | Convert an SDD into production code, with the bug loop as a first-class state |
| `/ship` | Gated deploy: docs → tests → type check → review → build → Jira transition + Slack sync |
| `/retro` | Offered automatically once all tasks complete. Structured retrospective → memories → CLAUDE.md update → Jira comment (never a status transition — that's `/ship`'s job) |
| `/dashboard` | Read-only visual view of pipeline state, risks, amendments, budget |

There is deliberately **no `/standup`** and **no `/evolve`** — their value is delivered passively by hooks instead of requiring you to remember a command.

### Hooks and the sentinel (automatic)

| Component | Trigger | What it does |
|-----------|---------|-------------|
| `session_start.py` | First message of each session | Injects context-relevant memories, the interrupted checkpoint, and budget-reset status |
| `quality_gate.py` | After every file edit | Runs the configured linter + type checker, tracks the anti-pattern registry |
| `stop_checklist.py` | When Claude finishes responding | Budget directive, staged amendments, task drift, unstaged files, memory nudges |
| `budget_sentinel.py` | Statusline, every render | Reads `rate_limits` and trips an alert at 95% so work is checkpointed before a breach |

## How it stays honest

- **The SDD is a living document.** When a bug reveals a design gap, `sdd-implementer` stages an amendment and folds it in at the next pause — no interruption mid-loop, no silently rotting doc. Past 5 amendments it forces compaction into the body.
- **Amendments can invalidate the plan.** A gap found in task 3 flags task 4 with `needs_recheck` rather than leaving the task graph stale.
- **Design is hardened before code exists.** The adversarial pass runs in a subagent that sees only the SDD, so it cannot converge on its own reasoning. Coverage of all 10 failure classes is the exit condition, capped at 3 passes.
- **Evolution is passive.** Style corrections and repeated anti-patterns accumulate as memories and re-enter at design time. Nothing rewrites its own skill files.
- **Human in the loop at design, autonomous at implementation.** `approved: false` in `task_state.json` blocks code generation until you confirm the plan; after that, implementation runs without process questions.

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
./install.sh --project-dir /path/to/your/project
```

### Windows (PowerShell)

```powershell
git clone https://github.com/HarshDhussa1008/shipwright
cd shipwright
.\install.ps1 -ProjectDir C:\path\to\your\project
```

The installer:
1. Copies skills to `~/.claude/skills/` (user-level, available in all projects)
2. Copies the `.claude/` directory into your project (hooks + state files)
3. Copies `.claude/settings.json` with hook wiring (if one already exists, prints instructions to merge manually)

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
  "test_command": "python -m pytest . -v --tb=short",
  "lint_command": "python -m ruff check --fix {file}",
  "typecheck_command": "python -m mypy {file} --ignore-missing-imports --no-error-summary",
  "gate_extensions": [".py"],
  "budget_alert_threshold": 95,
  "sdd_path": "docs/sdd",
  "languages": ["python"]
}
```

Set `jira_integration: false` to use the framework without Jira — all Jira steps are skipped gracefully.

`lint_command` / `typecheck_command` take a `{file}` placeholder, so the quality gate works on any toolchain — swap in `eslint`, `tsc`, `golangci-lint`, `clippy`, whatever your project uses, and set `gate_extensions` to match. Set either to `null` to skip it.

## Usage

### Full pipeline

```
# 1. Design: generate an SDD and harden it against 10 failure classes
/design PROJ-123
/design "Add rate limiting to the payments API"

# 2. Break down: decompose the hardened SDD into tasks (+ Jira subtasks)
/breakdown docs/sdd/rate-limiting.md

# 3. Approve: review the task list, then just say "approved"
#    (this flips approved:true — there is no /approve command)

# 4. Implement: sdd-implementer runs task-by-task, staying in the bug loop

# 5. Deploy, when there is an actual deploy to make
/ship staging
/ship prod

# 6. End of feature
/retro
```

You never need to remember what comes next: every skill ends with the literal next command to type, and `session_start` replays it from the checkpoint if you were interrupted.

### While working

```
/dashboard        # visual state: risks, tasks, amendments, budget
/resume           # continue an interrupted session from checkpoint
```

Drop files into `.claude/inbox/` and they appear in the dashboard with paths ready to reference — the CLI's file-upload gap, bridged without any upload plumbing.

## Surviving a rate-limit breach

`budget_sentinel.py` runs as the statusline, which is the only local surface that receives `rate_limits` (hooks do not get them). It records 5-hour and 7-day headroom to `budget.json` on every render and trips at `budget_alert_threshold`. The Stop hook relays that once as a directive to checkpoint immediately with the literal next action — file and line — so the session can be resumed cold after the window resets. `session_start` then reports whether the window has actually reset.

Requires a claude.ai Pro or Max subscription; without one the sentinel degrades to context-window and git info only.

## Project CLAUDE.md

Copy `CLAUDE.md.template` to your project root as `CLAUDE.md` and fill in the placeholders. Claude Code reads this file at the start of every session to understand your project's conventions.

## How it works

- **Skills** are Markdown files that Claude Code loads as slash commands. They contain role definitions, step-by-step protocols, and quality rules.
- **Hooks** are Python scripts that Claude Code executes automatically on specific events (file edits, session start, response end).
- **State files** (`checkpoint.json`, `task_state.json`) persist pipeline state across sessions so work survives interruptions.
- **Memory** files in `~/.claude/projects/<slug>/memory/` persist learnings across all sessions for a project.

## License

MIT
