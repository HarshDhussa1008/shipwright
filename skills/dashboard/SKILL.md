# /dashboard — Read-only pipeline view

## Role

You open a visual view of pipeline state for the passes a terminal is bad at: scanning a risk register, seeing which tasks drifted, reading amendments in context, checking budget headroom.

It is read-only. It never edits code, never talks back to the agent, and never replaces the CLI loop.

## Invocation

```
/dashboard          # regenerate and open
/dashboard serve    # serve on localhost with 10s auto-refresh
```

## Protocol

### Step 1 — Render
```bash
python .claude/tools/dashboard.py
```
Writes `.claude/dashboard.html` and prints the path. Open it for the user (`start` on Windows, `open` on macOS, `xdg-open` on Linux).

For a live view while working:
```bash
python .claude/tools/dashboard.py --serve --port 7399
```
Run it in the background and give the user the URL. It binds to `127.0.0.1` only.

### Step 2 — Read the panels back
Do not just hand over a link. Call out anything the dashboard surfaces that needs action:
- unmitigated `Critical` / `High` risks
- tasks flagged `needs recheck` (an amendment may have invalidated their plan)
- staged amendments not yet folded into the SDD
- an amendment log past the 5-entry compaction threshold
- budget at or past the alert threshold
- `awaiting approval` when implementation is supposedly underway

### Step 3 — Inbox
`.claude/inbox/` is the file-drop bridge. Anything placed there is listed in the dashboard with a repo-relative path ready to reference — this is how screenshots, logs, and exports get into a CLI session without upload plumbing.

If the user mentions a file they want you to look at, check the inbox first.

## Rules
- Read-only. If the dashboard suggests a change, make it through the normal loop — never from here.
- Do not build features into the dashboard on request without saying what it will cost; it is deliberately a single stdlib script with no dependencies, and it should stay that way.
- The served directory is `.claude/`, which contains state files but no secrets. Do not bind it to `0.0.0.0`.
