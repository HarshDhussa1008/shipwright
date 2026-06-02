"""
PostToolUse hook — runs after every Edit or Write tool call.
Runs ruff + mypy on the edited file, updates anti_pattern_registry.json.
Emits a single-line summary. Emits [PATTERN ALERT] when any error code hits count >= 2.
Always exits 0 (advisory, never blocking).
"""

import json
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = REPO_ROOT / ".claude" / "anti_pattern_registry.json"
ALERT_THRESHOLD = 2

ALWAYS_SKIP = {"__pycache__", "dist", "build", "node_modules", ".git"}


def load_framework_config() -> dict:
    config_path = REPO_ROOT / ".claude" / "framework.json"
    if config_path.exists():
        try:
            return json.loads(config_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def get_venv_skip_dirs(config: dict) -> set[str]:
    project_name = config.get("project_name", "")
    skip = set(ALWAYS_SKIP)
    if project_name:
        skip.add(f".{project_name}")
        skip.add(f".venv-{project_name}")
    skip.update({".venv", "venv", ".env"})
    return skip


def get_edited_file() -> Path | None:
    raw = os.environ.get("CLAUDE_TOOL_INPUT", "")
    if not raw:
        return None
    try:
        data = json.loads(raw)
        path = data.get("file_path") or data.get("path") or data.get("new_file_path")
        if path:
            return Path(path)
    except (json.JSONDecodeError, TypeError):
        pass
    return None


def should_skip(path: Path, skip_dirs: set[str]) -> bool:
    if path.suffix != ".py":
        return True
    for part in path.parts:
        if part in skip_dirs:
            return True
    return False


def run(cmd: list[str]) -> tuple[int, str]:
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)
    return result.returncode, (result.stdout + result.stderr).strip()


def extract_ruff_codes(output: str) -> list[str]:
    codes = []
    for line in output.splitlines():
        parts = line.split()
        for part in parts:
            if len(part) >= 4 and part[0].isupper() and part[1:3].isdigit():
                codes.append(part.rstrip(":,"))
    return codes


def load_registry() -> dict:
    if REGISTRY_PATH.exists():
        try:
            return json.loads(REGISTRY_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_registry(registry: dict) -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(json.dumps(registry, indent=2))


def main() -> None:
    config = load_framework_config()
    skip_dirs = get_venv_skip_dirs(config)
    languages = config.get("languages", ["python"])

    edited = get_edited_file()
    if edited is None or should_skip(edited, skip_dirs):
        return

    if "python" not in languages:
        return

    ruff_rc, ruff_out = run(["python", "-m", "ruff", "check", "--fix", str(edited)])
    ruff_codes = extract_ruff_codes(ruff_out)
    ruff_summary = f"{len(ruff_codes)} issues" if ruff_codes else "0 issues"

    mypy_rc, mypy_out = run(["python", "-m", "mypy", str(edited), "--ignore-missing-imports", "--no-error-summary"])
    mypy_lines = [l for l in mypy_out.splitlines() if ": error:" in l or ": warning:" in l]
    mypy_summary = f"{len(mypy_lines)} warn" if mypy_lines else "0 warn"

    registry = load_registry()
    alerts = []
    for code in ruff_codes:
        entry = registry.get(code, {"count": 0, "last_file": "", "memory_written": False})
        entry["count"] += 1
        entry["last_file"] = str(edited)
        registry[code] = entry
        if entry["count"] >= ALERT_THRESHOLD and not entry["memory_written"]:
            alerts.append(f"{code}×{entry['count']}")
    save_registry(registry)

    registry_summary = ", ".join(f"{k}×{v['count']}" for k, v in registry.items() if v["count"] > 0) or "clean"
    print(f"[GATE] ruff: {ruff_summary} | mypy: {mypy_summary} | registry: {registry_summary}")

    for alert in alerts:
        code = alert.split("×")[0]
        print(f"[PATTERN ALERT] {code} triggered {registry[code]['count']} times — consider writing a feedback memory.")


if __name__ == "__main__":
    main()
