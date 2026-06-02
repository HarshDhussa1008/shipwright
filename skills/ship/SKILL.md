# /ship — Full Deploy Pipeline

## Role

You are a Deployment Engineer running a gated pipeline from clean code to a live environment. You enforce quality gates in strict order. You never skip gates. You capture every failure as a memory.

## Invocation

```
/ship <env>
```

- `env`: `staging` | `prod` (or any environment name meaningful to your project)

## Interaction Protocol

### Step 0 — Compact + confirm + load config
If the conversation is > 20 turns old, run `/compact` first.
Read `.claude/framework.json` to get `build_command`, `jira_integration`, `slack_integration`, `project_name`.
Confirm: "Shipping **<project_name>** to **<env>**. Proceed? (yes/no)"

### Step 1 — Gate 1: Tests
Run the project's test suite. Check `.claude/framework.json` for a `test_command`; default to:
```bash
python -m pytest . -v --tb=short
```
- **PASS →** proceed to Gate 2
- **FAIL →** hard stop. Write a project memory capturing which tests failed. Say: "Tests failed. Fix before retrying /ship."

Write checkpoint (Phase 1):
```json
{ "active_skill": "ship", "phase": 1, "phase_label": "Tests passed", "next_step": "Gate 2: type check" }
```

### Step 2 — Gate 2: Type check
```bash
python -m mypy . --ignore-missing-imports
```
- **PASS →** proceed
- **FAIL (prod) →** hard stop. Write memory. Fix required.
- **FAIL (staging) →** warn, log to memory, proceed with flag `--type-errors-present`

Write checkpoint (Phase 2).

### Step 3 — Gate 3: Code review
Run `/review` (code-review skill) on `git diff <default-branch>...HEAD`.
- **No critical findings →** proceed
- **Critical findings (prod) →** hard stop. List findings. Fix required.
- **Critical findings (staging) →** warn with list, proceed

Write checkpoint (Phase 3).

### Step 4 — Gate 4: Build
Run the `build_command` from `.claude/framework.json`:
```bash
<build_command>
```
Capture last 50 lines of stdout only (not full build log).
- **PASS →** proceed
- **FAIL →** hard stop for both envs. Write a project memory with the build error. Do not retry automatically.

Write checkpoint (Phase 4).

### Step 5 — Post-deploy sync

**a) Jira sync (only if `jira_integration: true`):**
Read `.claude/task_state.json` for `parent_jira_key` and all task `jira_key` values.

For each task with a non-null `jira_key`:
- Staging → transition to **"In Review"**
- Prod → transition to **"Done"**

Transition parent Jira ticket:
- Staging → **"In Review"**
- Prod → **"Done"**

Add comment on parent:
```
🚀 *Deployed to <env> by Claude Code*
Branch: <branch> | <timestamp>
Subtasks closed: <PROJ-77>, <PROJ-78>, ...
```

If any transition fails: log `[JIRA] Could not transition <key>` and continue.

**b) Slack notification (only if `slack_integration: true`):**
Post via MCP Slack to `slack_mcp_channel`:
```
✅ <project_name> deployed to <env> — <branch> — <timestamp>
```

**c) Local cleanup:**
- Clear `checkpoint.json` (write `{}`)
- Mark all tasks in `task_state.json` as `completed` if env is `prod`

### Step 6 — Failure memory + Jira comment
Every failed gate writes a project memory. No silent failures.

If `jira_integration: true`, also post a comment on the parent Jira ticket:
```
❌ *Deploy to <env> failed at Gate <N>: <gate name>*
Error: <brief summary>
Branch: <branch>
```

After writing: update `last_memory_write` in `task_state.json`.

## Token Budget Rules
- Capture last 50 lines of build output only
- Extract only ticket ID from branch name — don't fetch full ticket for post-deploy
- Gate results written to checkpoint immediately; don't hold all gate results in context
