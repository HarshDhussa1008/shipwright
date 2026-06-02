# /standup — Daily Status Report

## Role

You generate a concise daily standup from git activity and task state. If Jira is configured, you also run a drift check to surface any mismatch between local and Jira status.

## Interaction Protocol

### Step 1 — Load config
Read `.claude/framework.json` to check `jira_integration`.

### Step 2 — Gather data (parallel)
Always:
- `git log --since=yesterday --oneline` (scoped to current repo, max 20 commits)
- Read `.claude/task_state.json` for task statuses and Jira keys

If `jira_integration: true`:
- MCP Atlassian: for each task with a non-null `jira_key`, fetch current Jira status.
  Batch into one JQL query: `issue in (PROJ-77, PROJ-78, ...)` — not individual fetches.
  Extract only: `key`, `fields.status.name`.

### Step 3 — Detect Jira drift (only if `jira_integration: true`)
Compare local `status` in task_state.json against Jira status for each task.

Common drift patterns:
| Local | Jira | Action |
|-------|------|--------|
| `completed` | `To Do` | Jira wasn't updated — transition it silently |
| `in_progress` | `Done` | Jira closed externally — flag it |
| `pending` | `In Progress` | Jira started elsewhere — update local |

Auto-fix: local `completed` but Jira `To Do` → transition Jira silently.
Ambiguous drift: list under "⚠️ Drift" section, don't auto-fix.

### Step 4 — Generate report
Output exactly 4 sections (skip a section only if genuinely empty):

```
**Done** (commits since yesterday)
- <commit message>

**In Progress** (tasks with status=in_progress)
- <task title> [<complexity>] — <jira_key or local id>

**Blocked** (tasks with a blocker note)
- <task title> — <blocker reason>

**Next** (next pending task by dependency order)
- <task title> [<complexity>] — <jira_key or local id>

⚠️ Drift (only if any, only if Jira enabled)
- <jira_key>: local=<status> / Jira=<status>
```

If "Blocked" section is non-empty: prompt "Write a memory for this blocker? (y/n)"
If yes: write a project memory and update `last_memory_write`.

### Step 5 — Post to Slack (only if `--post-slack` flag and `slack_integration: true`)
Post the formatted report (without Drift section) via MCP Slack to the configured channel.
Include drift as a separate follow-up message if present.

## Token Budget
- Read git log tail (max 20 commits)
- Read task_state.json once
- Batch Jira status fetch in one JQL query (not N individual fetches)
- Extract only `key` and `fields.status.name` from Jira response
