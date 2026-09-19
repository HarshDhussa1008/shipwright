"""
Stop hook — runs when Claude finishes responding.
Checks: budget breach, staged amendments, task drift, unstaged files, open tasks,
unwritten anti-pattern memories, last-memory-write age.
Outputs a markdown checklist so Claude sees it at the start of the next turn.
Always exits 0.
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

if _reconfigure := getattr(sys.stdout, "reconfigure", None):
    try:
        _reconfigure(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        pass

REPO_ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = REPO_ROOT / ".claude"
TASK_STATE_PATH = STATE_DIR / "task_state.json"
REGISTRY_PATH = STATE_DIR / "anti_pattern_registry.json"
AMENDMENTS_PATH = STATE_DIR / "amendments_pending.json"
BUDGET_PATH = STATE_DIR / "budget.json"
MEMORY_NUDGE_HOURS = 4


def get_unstaged_files() -> list[str]:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, cwd=REPO_ROOT, check=False,
        )
        lines = [l.strip() for l in result.stdout.splitlines() if l.strip()]
        return [l for l in lines if l.endswith((".py", ".md", ".json"))]
    except (OSError, subprocess.SubprocessError):
        return []


def get_open_tasks() -> list[str]:
    if not TASK_STATE_PATH.exists():
        return []
    try:
        data = json.loads(TASK_STATE_PATH.read_text())
        return [
            t["id"] for t in data.get("tasks", [])
            if t.get("status") in ("in_progress", "pending")
        ]
    except (json.JSONDecodeError, OSError):
        return []


def get_unwritten_patterns() -> list[str]:
    if not REGISTRY_PATH.exists():
        return []
    try:
        registry = json.loads(REGISTRY_PATH.read_text())
        return [
            f"{code}×{v['count']}"
            for code, v in registry.items()
            if v["count"] >= 2 and not v.get("memory_written", False)
        ]
    except (json.JSONDecodeError, OSError):
        return []


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return {}


def budget_directive() -> str | None:
    """The statusline sentinel detects the breach; only a hook can tell Claude about it."""
    budget = read_json(BUDGET_PATH)
    alert = budget.get("alert") or {}
    if not alert.get("tripped") or alert.get("acknowledged"):
        return None

    budget["alert"]["acknowledged"] = True
    try:
        BUDGET_PATH.write_text(json.dumps(budget, indent=2), encoding="utf-8")
    except OSError:
        pass

    resets = alert.get("resets_at_iso") or "unknown"
    return (
        f"**BUDGET {alert.get('used_percentage', 0):.0f}% of {alert.get('window')} limit "
        f"(threshold {alert.get('threshold')}%)** — window resets {resets}.\n"
        "[ ] Write checkpoint.json NOW with the literal next action (file and line), "
        "finish only the edit in hand, and stop starting new work."
    )


def staged_amendments() -> list[str]:
    data = read_json(AMENDMENTS_PATH)
    items = []
    if candidates := data.get("candidates"):
        items.append(
            f"[ ] {len(candidates)} design-gap amendment(s) staged — fold into the SDD "
            "Amendments section, flag affected pending tasks with needs_recheck, then clear"
        )
    if styles := data.get("style_candidates"):
        items.append(
            f"[ ] {len(styles)} style correction(s) staged — write as user/feedback memory, then clear"
        )
    return items


def untracked_commits() -> str | None:
    """Drift: commits that map to no task in task_state.json. Replaces /standup's drift check."""
    state = read_json(TASK_STATE_PATH)
    tasks = state.get("tasks") or []
    if not tasks:
        return None
    try:
        result = subprocess.run(
            ["git", "log", "-15", "--format=%h %s"],
            capture_output=True, text=True, cwd=REPO_ROOT, timeout=5, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    keys = [str(t.get("id", "")) for t in tasks] + [str(t.get("jira_key") or "") for t in tasks]
    keys = [k for k in keys if k]
    titles = [str(t.get("title", "")).lower() for t in tasks]

    orphans = []
    for line in result.stdout.splitlines():
        subject = line.split(" ", 1)[1].lower() if " " in line else ""
        if not subject:
            continue
        if any(k.lower() in subject for k in keys):
            continue
        if any(word in subject for title in titles for word in title.split()[:3] if len(word) > 4):
            continue
        orphans.append(line)

    if len(orphans) >= 3:
        return f"[ ] {len(orphans)} recent commit(s) map to no task — scope drift, or task_state is stale?"
    return None


def retro_offer() -> str | None:
    """All tasks done -> offer /retro once. Never auto-run it: the 4 questions need a
    real answer from the user, not the agent grading its own design after the fact."""
    state = read_json(TASK_STATE_PATH)
    tasks = state.get("tasks") or []
    if not tasks or state.get("retro_offered"):
        return None
    if any(t.get("status") != "completed" for t in tasks):
        return None

    state["retro_offered"] = True
    try:
        TASK_STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except OSError:
        pass

    return f"[ ] All {len(tasks)} task(s) completed — run /retro? (feature-level reflection only you can answer)"


def memory_nudge_needed() -> bool:
    if not TASK_STATE_PATH.exists():
        return False
    try:
        data = json.loads(TASK_STATE_PATH.read_text())
        last_write = data.get("last_memory_write")
        if not last_write:
            return len(data.get("tasks", [])) > 0
        age = datetime.now(timezone.utc) - datetime.fromisoformat(last_write)
        return age.total_seconds() > MEMORY_NUDGE_HOURS * 3600
    except (json.JSONDecodeError, OSError, ValueError):
        return False


def main() -> None:
    items = []

    # Budget breach outranks everything else — it is the only item with a deadline.
    if directive := budget_directive():
        print("\n" + directive)

    items.extend(staged_amendments())

    if drift := untracked_commits():
        items.append(drift)

    unstaged = get_unstaged_files()
    if unstaged:
        items.append(f"[ ] {len(unstaged)} file(s) modified but not committed: {', '.join(unstaged[:3])}{'...' if len(unstaged) > 3 else ''}")

    open_tasks = get_open_tasks()
    if open_tasks:
        items.append(f"[ ] {len(open_tasks)} task(s) still open: {', '.join(open_tasks)}")
    elif offer := retro_offer():
        items.append(offer)

    patterns = get_unwritten_patterns()
    if patterns:
        items.append(f"[ ] anti_pattern_registry has unwritten memories: {', '.join(patterns)} — run /remember to capture")

    if memory_nudge_needed():
        items.append("[ ] No memory written this session (>4h) — did you make any non-obvious decisions?")

    if items:
        print("\n**Session Checklist:**")
        for item in items:
            print(item)


if __name__ == "__main__":
    main()
