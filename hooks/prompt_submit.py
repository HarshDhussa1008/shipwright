"""UserPromptSubmit hook -- fires on every user message; plain stdout reaches Claude.

1. Approval capture. When a plan is awaiting approval and the *user* replies "approved"
   (or "approve" / "lgtm"), this hook -- not Claude -- flips task_state.approved. Paired
   with approval_gate.py, which denies Claude's own attempts to flip it, the human
   checkpoint between design and code is enforced rather than requested.
2. Budget relay fallback. If the statusline tripped the budget alert and the Stop hook
   never got to deliver it, deliver it here.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    Project,
    age_seconds,
    now_iso,
    project_root,
    read_json,
    read_payload,
    record_metric,
    run_safely,
    write_json,
)

APPROVAL_RE = re.compile(r"^\s*(approved?|lgtm)\b", re.IGNORECASE)


def capture_approval(project: Project, prompt: str) -> str | None:
    if not APPROVAL_RE.match(prompt or ""):
        return None
    state = read_json(project.task_state)
    if not state.get("tasks") or state.get("approved") is True:
        return None
    state["approved"] = True
    state["approved_at"] = now_iso()
    state["approved_by"] = "user-prompt"
    write_json(project.task_state, state)
    latency = age_seconds(state.get("tasks_created_at"))
    record_metric(project, "approval", task_count=len(state["tasks"]),
                  latency_seconds=round(latency) if latency is not None else None)
    return (
        f"[APPROVAL] The user approved the plan ({len(state['tasks'])} tasks). "
        "task_state.approved is now true -- implementation may begin."
    )


def budget_directive(project: Project) -> str | None:
    budget = read_json(project.budget)
    alert = budget.get("alert") or {}
    if not alert.get("tripped") or alert.get("acknowledged"):
        return None
    alert["acknowledged"] = True
    budget["alert"] = alert
    write_json(project.budget, budget)
    return (
        f"[BUDGET] {float(alert.get('used_percentage', 0)):.0f}% of the {alert.get('window')} limit "
        f"(threshold {alert.get('threshold')}%), resets {alert.get('resets_at_iso') or 'unknown'}. "
        "Write .claude/checkpoint.json NOW with the literal next action (file and line), finish only "
        "the edit in hand, and do not start new work."
    )


def main() -> None:
    payload = read_payload()
    project = Project(project_root(payload))
    if not project.enabled:
        return
    out = [msg for msg in (budget_directive(project), capture_approval(project, str(payload.get("prompt", "")))) if msg]
    if out:
        print("\n".join(out))


if __name__ == "__main__":
    run_safely(main)
