# /retro — Structured Feature Retrospective

## Role

You facilitate a structured retrospective, offered as soon as implementation finishes — before `/ship`, not after. You capture learnings as durable memories, update CLAUDE.md, and flag stale memories. Minimum output: 3 new memory files.

**Jira status transitions are not your job.** `/ship` owns Jira lifecycle exclusively (staging → "In Review", prod → "Done"), gated by an actual deploy. `/retro` runs before a deploy has necessarily happened — transitioning tickets to "Done" here would close work that hasn't shipped, and would fight `/ship`'s own transition on the next deploy. If `jira_integration` is true, `/retro` only ever adds a wrap-up comment — it never calls a transition.

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

### Step 6 — Comment on Jira (only if `jira_integration: true`, no status transitions)
Add a comment on the **parent ticket** (`parent_jira_key`) — never transition its status, that's `/ship`'s call to make on an actual deploy:
```
🔄 *Retro run — build complete, not yet shipped*
Branch: <branch>
Memories written: <count>
Next: /ship <env> when ready to deploy — Jira will transition then, not here.
```

### Step 7 — Summary
Print:
```
Retro complete. Wrote <N> memories. CLAUDE.md updated. <M> stale memories flagged.
Jira: comment posted on <parent_jira_key> (no status change — /ship owns that).
Next: /ship <env> when ready to deploy.
```
(Omit the Jira line if `jira_integration: false`.)

## Rules
- Never skip the 4 questions even if context is long — use `/compact` to free up space first
- Write positive feedback memories (what worked) — not just corrections
- Do not write memories for things already in CLAUDE.md "Do Not Do" section
- **Never call a Jira transition from this skill.** Comment only. `/ship` is the single owner of Jira status — two skills racing to set status on the same ticket is exactly the kind of drift this framework exists to prevent.
