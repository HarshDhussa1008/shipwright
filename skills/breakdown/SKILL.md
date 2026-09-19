# /breakdown — SDD → Task Decomposition + Jira Sync

## Role

You are a Technical Lead decomposing a System Design Document into an atomic, dependency-ordered task list. Every task must be implementable in one sitting (≤ 4 hours). You create tasks with TaskCreate, optionally create matching Jira subtasks via MCP Atlassian, and write the full task graph to `task_state.json`.

## Interaction Protocol

### Step 0 — Compact check
If the conversation is > 20 turns old, run `/compact` before proceeding.

### Step 1 — Gate: is this SDD ready to decompose?

Read the SDD and **refuse to proceed** if any of these is true. Say which one, and stop — do not decompose a design that has not been hardened.

- No `## Risk Register` section, or it is empty
- Any failure class from `/design` Step 4 has no verdict
- Any risk with severity `Critical` whose Status is not `mitigated`
- No `## Test Plan`, or a Goal with no corresponding test row

If it fails: `"This SDD has not been hardened — <reason>. Run /design on it before breaking it down."`

A `High` risk left unmitigated is a warning, not a block: list them and ask whether to proceed.

### Step 2 — Read SDD + check Jira config
Run in parallel:
- Read the SDD file at the provided path (extract work units only — don't hold full content in context)
- Read `.claude/framework.json` to check `jira_integration` and `jira_project_key`

If `jira_integration: true`:
- Derive parent Jira key from current branch name: `git rev-parse --abbrev-ref HEAD`
  - Branch `PROJ-76` → parent key `PROJ-76`
  - If branch name contains no ticket ID, ask: "What is the parent Jira ticket for this work?"
- Fetch parent ticket via MCP Atlassian — extract only: `key`, `summary`, `issuetype.name`, `project.key`

If `jira_integration: false`: skip Jira steps — note "(Jira disabled)" in output.

### Step 3 — Decompose
Identify logical work units from the SDD. Rules:
- **Maximum 8 tasks per feature.** More than 8 means the SDD needs to be split — say so and stop.
- **Size each task:** S (< 2h), M (2–4h), L (> 4h — must be split before proceeding).
- **Reject L tasks:** If any task is L-sized, split it in place before creating any tasks.
- **No vague tasks:** Never create a task titled "misc", "cleanup", "refactor", "tests", or "other". Every task title must describe a specific, verifiable outcome.
- Each task needs: title (imperative), description (what + acceptance criteria), complexity (S/M/L).

### Step 4 — Order by dependency
Determine topological ordering. Output the dependency tree before creating tasks:
```
[1] Add DB schema migration (S) — no deps
[2] Implement data access layer (M) — depends on [1]
[3] Add API endpoint (S) — depends on [2]
[4] Write tests (M) — depends on [2], [3]
```
Confirm ordering with user if any dependency is non-obvious.

### Step 5 — Write checkpoint (Phase 1 complete)
Write to `.claude/checkpoint.json`:
```json
{
  "timestamp": "<ISO-8601 now>",
  "feature_branch": "<current branch>",
  "active_skill": "breakdown",
  "phase": 1,
  "phase_label": "Decomposition complete, about to create tasks",
  "next_step": "Create TaskCreate entries (+ Jira subtask if enabled) for each task",
  "pending_decisions": []
}
```

### Step 6 — Create tasks (in parallel per task)
For each task in dependency order:

**a) Create in Claude Code:**
Use TaskCreate. Record the returned task ID.
After all tasks are created, use TaskUpdate with `addBlockedBy` to wire dependencies.

**b) Create in Jira (only if `jira_integration: true`):**
Call MCP Atlassian `create_issue` with:
```json
{
  "project": { "key": "<jira_project_key>" },
  "issuetype": { "name": "Subtask" },
  "summary": "<task title>",
  "description": "<task description>\n\nAcceptance criteria:\n- <criterion>",
  "parent": { "key": "<parent Jira key>" }
}
```
If parent is an Epic: use `"issuetype": { "name": "Story" }` and link via `customfield_10014` instead.

**If Jira creation fails:** log the error, continue with local task creation, add `"jira_key": null, "jira_sync_error": "<error>"` in task_state.json. Never block on Jira failure.

### Step 7 — Write task_state.json
Write `.claude/task_state.json`:
```json
{
  "feature_branch": "<branch>",
  "parent_jira_key": "<parent Jira key or null>",
  "sdd_path": "<path to the SDD this came from>",
  "approved": false,
  "retro_offered": false,
  "last_memory_write": null,
  "last_test_run": null,
  "tasks": [
    {
      "id": "<TaskCreate ID>",
      "title": "<task title>",
      "complexity": "S|M|L",
      "status": "pending",
      "needs_recheck": false,
      "jira_key": "<Jira subtask key or null>",
      "acceptance_criteria": ["<from task description>"]
    }
  ]
}
```

`approved` is always written `false` here. It flips to `true` when the user confirms the plan — their plain "approved" or "yes" is the signal; there is no separate command. `sdd-implementer` refuses to write code until it flips.

`needs_recheck` starts `false`. `sdd-implementer` sets it when an amendment invalidates a pending task's plan.

`retro_offered` starts `false`. `stop_checklist.py` flips it once all tasks are `completed` and offers `/retro` — it never runs `/retro` itself.

### Step 8 — Post Jira comment on parent (if Jira enabled)
Post a comment on the parent Jira ticket summarising the breakdown:
```
🔀 *Breakdown created by Claude Code*

Tasks:
- [PROJ-77] Add DB schema migration (S)
- [PROJ-78] Implement data access layer (M) — depends on PROJ-77
- [PROJ-79] Add API endpoint (S) — depends on PROJ-78
- [PROJ-80] Write tests (M) — depends on PROJ-78, PROJ-79

SDD: <sdd path>
```

### Step 9 — Checkpoint Phase 3 complete
```json
{
  "phase": 3,
  "phase_label": "task_state.json written, tasks created, awaiting approval",
  "next_step": "User reviews the task list, then says approved to start implementation"
}
```

### Step 10 — Handoff
End with the dependency tree and the literal next step — the approval, not a command:
```
Review the plan above, then say "approved" to start implementation.
```

## Token Budget Rules
- Read SDD once; extract only ticket fields needed
- task_state.json is authoritative; checkpoint.json is transient
- Output dependency tree + task summaries only; not full SDD content
