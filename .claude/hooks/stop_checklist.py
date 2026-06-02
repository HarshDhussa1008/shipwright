"""
Stop hook — runs when Claude finishes responding.
Checks: unstaged files, open tasks, unwritten memories in anti_pattern_registry, last-memory-write age.
Outputs a markdown checklist so Claude sees it at the start of the next turn.
Always exits 0.
"""

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TASK_STATE_PATH = REPO_ROOT / ".claude" / "task_state.json"
REGISTRY_PATH = REPO_ROOT / ".claude" / "anti_pattern_registry.json"
MEMORY_NUDGE_HOURS = 4


def get_unstaged_files() -> list[str]:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, cwd=REPO_ROOT
        )
        lines = [l.strip() for l in result.stdout.splitlines() if l.strip()]
        return [l for l in lines if l.endswith(".py") or l.endswith(".md") or l.endswith(".json")]
    except Exception:
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

    unstaged = get_unstaged_files()
    if unstaged:
        items.append(f"[ ] {len(unstaged)} file(s) modified but not committed: {', '.join(unstaged[:3])}{'...' if len(unstaged) > 3 else ''}")

    open_tasks = get_open_tasks()
    if open_tasks:
        items.append(f"[ ] {len(open_tasks)} task(s) still open: {', '.join(open_tasks)}")

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
