# /retro — Structured Feature Retrospective

## Role

You facilitate a structured retrospective at the end of a feature branch. You capture learnings as durable memories, update CLAUDE.md, flag stale memories, and optionally close Jira tickets. Minimum output: 3 new memory files.

## Interaction Protocol

### Step 1 — Load config + build context (parallel)
Read `.claude/framework.json` to check `jira_integration` and `project_name`.

Run in parallel:
- `git log <default-branch>...HEAD --oneline` — what was actually shipped
- Read `.claude/task_state.json` — planned tasks + Jira keys

If `jira_integration: true`:
- MCP Atlassian batch fetch: `issue in (<all jira_keys>)` — get `key`, `status.name`, `resolution` for each subtask
  Diff planned tasks vs actual commits — note gaps (unimplemented tasks, unplanned commits).

### Step 2 — Ask 4 structured questions
Ask one at a time, waiting for each answer:

1. "What was harder than estimated, and why?"
   → Maps to **feedback memory** on effort estimation
2. "Is there anything you'd design differently now? (architecture, data model, API shape)"
   → Maps to **project memory** on design regrets
3. "Any patterns that should never be repeated? (code patterns, mistakes, wrong approaches)"
   → Maps to **feedback memory** as anti-patterns
4. "Any patterns that worked well and should be actively repeated?"
   → Maps to **positive feedback memory** (write these too — not just corrections)

### Step 3 — Write memories (minimum 3)
For each answer that yields an actionable insight:
- Derive project slug from REPO_ROOT or `memory_path` in framework.json
- Write to `~/.claude/projects/<project-slug>/memory/retro_<branch>_<slug>.md`
- Use correct type (feedback or project)
- Include **Why:** and **How to apply:** lines
- Update MEMORY.md index

Update `last_memory_write` in `task_state.json` to current ISO timestamp.

### Step 4 — Update CLAUDE.md
Append to the "Lessons Learned" section in `CLAUDE.md`:
```markdown
## Lessons Learned

### <branch> (<date>)
- <1-line summary of each anti-pattern or key decision>
```
Trim the section if it exceeds 20 entries (remove the oldest 5).

### Step 5 — Flag stale memories
Scan the project memory directory for `.md` files with `mtime` older than 90 days. For each:
- Print: `[STALE] <filename> — last modified <date>`
- Ask: "Archive, update, or keep?"

### Step 6 — Close Jira tickets (only if `jira_integration: true`)
For any subtask with `jira_key` not yet `Done` in Jira:
- Transition to **"Done"** via MCP Atlassian
- Add comment: `✅ Closed by /retro — feature branch complete`

Then transition the **parent ticket** (`parent_jira_key`) to **"Done"** (check available transitions first).
Add comment on parent:
```
🎉 *Feature complete — retro run*
Branch: <branch>
Subtasks closed: <count>
Memories written: <count>
```

### Step 7 — Summary
Print:
```
Retro complete. Wrote <N> memories. CLAUDE.md updated. <M> stale memories flagged.
Jira: <X> subtasks closed. Parent <parent_jira_key> → Done.
```
(Omit the Jira line if `jira_integration: false`.)

## Rules
- Never skip the 4 questions even if context is long — use `/compact` to free up space first
- Write positive feedback memories (what worked) — not just corrections
- Do not write memories for things already in CLAUDE.md "Do Not Do" section
