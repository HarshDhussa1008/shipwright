"""
UserPromptSubmit hook — fires on every user message.
1. Budget breach second-chance: relays stop_checklist.py's checkpoint directive if the
   Stop hook never got a clean turn boundary to fire it in (runs every prompt).
2. Once per session, on the first message: injects top-3 relevant memories from the
   project's MEMORY.md, and shows a [CHECKPOINT] banner if checkpoint.json is non-empty
   and < 48h old. Uses a session_id temp file to fire only once per session.
Always exits 0.
"""

import json
import os
import re
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
CHECKPOINT_PATH = REPO_ROOT / ".claude" / "checkpoint.json"
SESSION_ID_PATH = REPO_ROOT / ".claude" / "session_id"
BUDGET_PATH = REPO_ROOT / ".claude" / "budget.json"
CHECKPOINT_MAX_AGE_HOURS = 48
MAX_MEMORIES = 3


def get_session_id() -> str:
    return os.environ.get("CLAUDE_SESSION_ID", "unknown")


def already_fired() -> bool:
    session_id = get_session_id()
    if SESSION_ID_PATH.exists():
        stored = SESSION_ID_PATH.read_text().strip()
        if stored == session_id:
            return True
    SESSION_ID_PATH.write_text(session_id)
    return False


def get_current_branch() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, cwd=REPO_ROOT, check=False,
        )
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def load_framework_config() -> dict:
    config_path = REPO_ROOT / ".claude" / "framework.json"
    if config_path.exists():
        try:
            return json.loads(config_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def get_memory_dir(config: dict) -> Path:
    if config.get("memory_path"):
        return Path(config["memory_path"])
    # Derive from repo root using Claude Code's slug algorithm
    slug = re.sub(r"[/\\:.]", "-", str(REPO_ROOT))
    slug = re.sub(r"-+", "-", slug).strip("-")
    return Path.home() / ".claude" / "projects" / slug / "memory"


STOPWORDS = {
    "the", "and", "for", "with", "into", "from", "that", "this", "add", "use",
    "run", "new", "not", "all", "any", "out", "via", "per", "its", "was", "are",
}


def context_keywords(branch: str, project_name: str, config: dict) -> set[str]:
    """Score memories against the work in flight, not just the branch name.

    Branch names are a weak signal (often 'master'), and passive memory injection is the
    framework's only evolution path, so a bad selector silently disables it.
    """
    words = {branch.lower(), project_name.lower()}

    state = {}
    try:
        state = json.loads((REPO_ROOT / ".claude" / "task_state.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        pass

    for task in state.get("tasks", []):
        words.update(re.findall(r"[a-z]{4,}", str(task.get("title", "")).lower()))

    sdd_rel = state.get("sdd_path")
    sdd_path = (REPO_ROOT / sdd_rel) if sdd_rel else None
    if sdd_path is None:
        sdd_dir = REPO_ROOT / config.get("sdd_path", "docs/sdd")
        if sdd_dir.is_dir():
            recent = sorted(sdd_dir.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)
            sdd_path = recent[0] if recent else None
    if sdd_path is not None and sdd_path.is_file():
        try:
            head = sdd_path.read_text(encoding="utf-8")[:1200].lower()
        except OSError:
            head = ""
        words.update(re.findall(r"[a-z]{4,}", head))
        words.add(sdd_path.stem.lower())

    return {w for w in words if w and w not in STOPWORDS} - {"master", "main", "develop"}


def load_relevant_memories(memory_dir: Path, keywords: set[str]) -> list[tuple[str, str]]:
    if not memory_dir.exists():
        return []

    memories = []

    for md_file in sorted(memory_dir.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True):
        if md_file.name == "MEMORY.md":
            continue
        try:
            content = md_file.read_text()
            lines = content.splitlines()
            desc = ""
            for line in lines:
                if line.startswith("description:"):
                    desc = line.split(":", 1)[1].strip()
                    break
            mem_type = ""
            for line in lines:
                if line.strip().startswith("type:"):
                    mem_type = line.split(":", 1)[1].strip()
                    break
            body_lines = [l for l in lines if l and not l.startswith("---") and not l.startswith("#") and ":" not in l[:20]]
            snippet = body_lines[0].strip() if body_lines else desc

            text = (desc + " " + snippet + " " + md_file.stem).lower()
            score = sum(1 for kw in keywords if kw in text)
            # Style and correction memories apply regardless of which feature is in flight.
            if mem_type in {"feedback", "user"}:
                score += 1
            if score == 0:
                continue
            memories.append((score, md_file.stat().st_mtime, desc or md_file.stem, snippet[:100]))
        except OSError:
            continue

    memories.sort(key=lambda m: (m[0], m[1]), reverse=True)
    return [(title, snippet) for _, _, title, snippet in memories[:MAX_MEMORIES]]


def load_checkpoint() -> dict | None:
    if not CHECKPOINT_PATH.exists():
        return None
    try:
        data = json.loads(CHECKPOINT_PATH.read_text())
        if not data or "active_skill" not in data:
            return None
        ts = data.get("timestamp")
        if ts:
            age = datetime.now(timezone.utc) - datetime.fromisoformat(ts)
            if age.total_seconds() > CHECKPOINT_MAX_AGE_HOURS * 3600:
                return None
        return data
    except (json.JSONDecodeError, OSError, ValueError):
        return None


def budget_directive() -> str | None:
    """Second chance for the Stop-hook relay in stop_checklist.py: if a rate-limit window
    gets crossed mid-response with no clean turn boundary before the hard limit hits, Stop
    may never fire in that session. UserPromptSubmit fires on every message (not just the
    first), so it catches an unacknowledged breach the next time the user sends anything --
    including after Claude Code's own auto-continue resumes the session post-reset."""
    try:
        budget = json.loads(BUDGET_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None

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
        f"\n**BUDGET {alert.get('used_percentage', 0):.0f}% of {alert.get('window')} limit "
        f"(threshold {alert.get('threshold')}%)** — window resets {resets}.\n"
        "[ ] Write checkpoint.json NOW with the literal next action (file and line), "
        "finish only the edit in hand, and stop starting new work."
    )


def budget_banner() -> str | None:
    """Surface whether a breached rate-limit window has since reset, so a resume is safe."""
    try:
        budget = json.loads((REPO_ROOT / ".claude" / "budget.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None

    alert = budget.get("alert") or {}
    if not alert.get("tripped"):
        return None

    resets_at = alert.get("resets_at")
    window = alert.get("window", "rate limit")
    if isinstance(resets_at, (int, float)):
        if datetime.now(timezone.utc).timestamp() >= resets_at:
            return f"[BUDGET] {window} window has reset - prior checkpoint is safe to resume."
        return (
            f"[BUDGET] {window} still at {alert.get('used_percentage', 0):.0f}% "
            f"until {alert.get('resets_at_iso', 'unknown')} - keep this session short."
        )
    return None


def main() -> None:
    # Runs on every prompt, not gated by already_fired -- see budget_directive() docstring.
    if directive := budget_directive():
        print(directive)

    if already_fired():
        return

    config = load_framework_config()
    branch = get_current_branch()
    project_name = config.get("project_name", "")
    memory_dir = get_memory_dir(config)

    if banner := budget_banner():
        print(banner)

    memories = load_relevant_memories(memory_dir, context_keywords(branch, project_name, config))
    for title, snippet in memories:
        print(f"[MEMORY] {title}: {snippet}")

    checkpoint = load_checkpoint()
    if checkpoint:
        ts = checkpoint.get("timestamp", "")
        skill = checkpoint.get("active_skill", "unknown")
        task_id = checkpoint.get("active_task_id", "")
        phase_label = checkpoint.get("phase_label", f"Phase {checkpoint.get('phase', '?')}")
        modified = ", ".join(checkpoint.get("files_modified_this_session", []))
        next_step = checkpoint.get("next_step", "")
        notes = checkpoint.get("notes", "")

        print(f"\n[CHECKPOINT] Interrupted session detected ({ts[:16] if ts else 'unknown time'})")
        print(f"  Skill: /{skill} | Task: {task_id}")
        print(f"  Phase: {phase_label}")
        if modified:
            print(f"  Modified: {modified}")
        if next_step:
            print(f"  Next: {next_step}")
        if notes:
            print(f"  Deferred: {notes}")
        print("  Type /resume to continue, or /checkpoint clear to discard.")


if __name__ == "__main__":
    main()
