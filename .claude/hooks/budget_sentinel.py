"""
statusLine command — receives session JSON on stdin every render.

Two jobs:
1. Render a compact status line (model, branch, context %, rate-limit %, pipeline phase).
2. Side effect: persist rate-limit headroom to budget.json and trip an alert at the
   configured threshold so the Stop hook can tell Claude to checkpoint and wrap up.

The statusline is the only local surface that exposes rate_limits; hooks do not get it.
Must never raise and never be slow — it runs on every render.
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = REPO_ROOT / ".claude"
BUDGET_PATH = STATE_DIR / "budget.json"
HISTORY_PATH = STATE_DIR / "budget_history.jsonl"
CHECKPOINT_PATH = STATE_DIR / "checkpoint.json"
CONFIG_PATH = STATE_DIR / "framework.json"

DEFAULT_THRESHOLD = 95.0
BAR_WIDTH = 8
HISTORY_MAX_SAMPLES = 60
HISTORY_MIN_INTERVAL_SECONDS = 60

# Windows consoles default to cp1252, which cannot encode the block/box glyphs.
# Without this the statusline raises on every render.
GLYPHS = {"full": "#", "empty": "-", "sep": " | "}
if _reconfigure := getattr(sys.stdout, "reconfigure", None):
    try:
        _reconfigure(encoding="utf-8", errors="replace")
        GLYPHS = {"full": "▓", "empty": "░", "sep": " │ "}
    except (OSError, ValueError):
        pass


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return {}


def write_atomic(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass


def git_branch() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, cwd=REPO_ROOT, timeout=2, check=False,
        )
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def bar(pct: float) -> str:
    filled = min(BAR_WIDTH, max(0, round(pct / 100 * BAR_WIDTH)))
    return GLYPHS["full"] * filled + GLYPHS["empty"] * (BAR_WIDTH - filled)


def append_history(now: datetime, context_pct: float | None, windows: dict) -> None:
    """Bounded trend log for the dashboard sparkline. Rewritten (not truly appended)
    each time to enforce the cap cheaply -- this runs on a statusline render cadence,
    not a hot path, so an O(n) rewrite of <= HISTORY_MAX_SAMPLES lines is fine."""
    samples: list[dict] = []
    try:
        samples = [json.loads(line) for line in HISTORY_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError, ValueError):
        samples = []

    if samples and now.timestamp() - samples[-1].get("t", 0) < HISTORY_MIN_INTERVAL_SECONDS:
        return  # statusline can render every few seconds; sample at most once a minute

    samples.append({
        "t": int(now.timestamp()),
        "ctx": context_pct,
        "5h": windows.get("five_hour", {}).get("used_percentage"),
        "7d": windows.get("seven_day", {}).get("used_percentage"),
    })
    samples = samples[-HISTORY_MAX_SAMPLES:]

    tmp = HISTORY_PATH.with_suffix(".jsonl.tmp")
    try:
        tmp.write_text("\n".join(json.dumps(s) for s in samples) + "\n", encoding="utf-8")
        os.replace(tmp, HISTORY_PATH)
    except OSError:
        pass


def window_state(rate_limits: dict, key: str) -> dict | None:
    window = rate_limits.get(key)
    if not isinstance(window, dict):
        return None
    pct = window.get("used_percentage")
    if pct is None:
        return None
    resets_at = window.get("resets_at")
    iso = ""
    if isinstance(resets_at, (int, float)):
        iso = datetime.fromtimestamp(resets_at, timezone.utc).isoformat()
    return {"used_percentage": float(pct), "resets_at": resets_at, "resets_at_iso": iso}


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return

    config = read_json(CONFIG_PATH)
    threshold = float(config.get("budget_alert_threshold", DEFAULT_THRESHOLD))

    model = (data.get("model") or {}).get("display_name", "")
    context = data.get("context_window") or {}
    context_pct = context.get("used_percentage")

    # rate_limits is present only for claude.ai Pro/Max (or a gateway with spend limits),
    # only after the first API response, and each window disappears once it resets.
    rate_limits = data.get("rate_limits") or {}
    windows = {
        name: state
        for name in ("five_hour", "seven_day", "spend_limit")
        if (state := window_state(rate_limits, name)) is not None
    }

    tripped = [
        (name, state) for name, state in windows.items()
        if state["used_percentage"] >= threshold
    ]
    tripped.sort(key=lambda item: item[1]["used_percentage"], reverse=True)

    previous = read_json(BUDGET_PATH)
    alert: dict = {"tripped": False}
    if tripped:
        name, state = tripped[0]
        was_tripped = (previous.get("alert") or {}).get("tripped") is True
        alert = {
            "tripped": True,
            "window": name,
            "used_percentage": state["used_percentage"],
            "threshold": threshold,
            "resets_at": state["resets_at"],
            "resets_at_iso": state["resets_at_iso"],
            # acknowledged is cleared on a fresh trip so the Stop hook speaks once per breach
            "acknowledged": (previous.get("alert") or {}).get("acknowledged", False) if was_tripped else False,
        }

    now = datetime.now(timezone.utc)
    append_history(now, context_pct if isinstance(context_pct, (int, float)) else None, windows)

    write_atomic(BUDGET_PATH, {
        "updated_at": now.isoformat(),
        "updated_at_epoch": int(time.time()),
        "context_window": {
            "used_percentage": context_pct,
            "size": context.get("context_window_size"),
            "exceeds_200k": data.get("exceeds_200k_tokens"),
        },
        "windows": windows,
        "alert": alert,
    })

    segments = []
    if model:
        segments.append(model)
    if branch := git_branch():
        segments.append(branch)
    if isinstance(context_pct, (int, float)):
        segments.append(f"ctx {bar(context_pct)} {context_pct:.0f}%")
    for label, key in (("5h", "five_hour"), ("7d", "seven_day"), ("spend", "spend_limit")):
        if key in windows:
            pct = windows[key]["used_percentage"]
            flag = " !" if pct >= threshold else ""
            segments.append(f"{label} {pct:.0f}%{flag}")

    checkpoint = read_json(CHECKPOINT_PATH)
    if skill := checkpoint.get("active_skill"):
        phase = checkpoint.get("phase", "?")
        task = checkpoint.get("active_task_id") or ""
        segments.append(f"/{skill} p{phase}{f' t{task}' if task else ''}")

    if alert["tripped"]:
        segments.append(f"CHECKPOINT NOW — {alert['window']} at {alert['used_percentage']:.0f}%")

    print(GLYPHS["sep"].join(segments))


if __name__ == "__main__":
    main()
