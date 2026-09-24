"""Shipwright project bootstrap -- used by /shipwright:init, /shipwright:doctor and install.sh/.ps1.

    run.sh tools/bootstrap.py init   --project DIR [--plugin-data DIR] [--team] [--marketplace-repo OWNER/REPO]
                                     [--no-statusline] [--force-statusline] [--migrate]
    run.sh tools/bootstrap.py team   --project DIR [--marketplace-repo OWNER/REPO]
    run.sh tools/bootstrap.py doctor --project DIR [--plugin-data DIR]

Everything is idempotent and non-destructive: existing config and state are never
overwritten; JSON settings are merged key by key; .gitignore patterns are only appended.
The one exception is --migrate, which removes the legacy copy-installed hook wiring and
the framework-owned legacy scripts (exact known file names only).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT / "hooks"))

from _common import DEFAULT_CONFIG, claude_slug, read_json, write_json  # noqa: E402

TEMPLATES = PLUGIN_ROOT / "templates"
DEFAULT_MARKETPLACE_REPO = "HarshDhussa1008/shipwright"
MARKETPLACE_NAME = "shipwright"
PLUGIN_ID = f"shipwright@{MARKETPLACE_NAME}"
STATUSLINE_FILES = ("budget_sentinel.py", "_common.py", "run.sh")
LEGACY_FILES = (
    ".claude/hooks/budget_sentinel.py",
    ".claude/hooks/quality_gate.py",
    ".claude/hooks/session_start.py",
    ".claude/hooks/stop_checklist.py",
    ".claude/tools/dashboard.py",
    ".claude/session_id",
)


def python_cmd() -> str:
    for name in ("python", "python3"):
        exe = shutil.which(name)
        if exe:
            try:
                ok = subprocess.run([exe, "-c", "import sys; sys.exit(sys.version_info < (3, 10))"],
                                    capture_output=True, timeout=10, check=False).returncode == 0
            except (OSError, subprocess.SubprocessError):
                ok = False
            if ok:
                return name
    return "python3"


def detect_stack(root: Path) -> dict[str, Any]:
    """Best-effort toolchain defaults so nobody hand-edits JSON on day one."""
    py = python_cmd()
    languages: list[str] = []
    overrides: dict[str, Any] = {}

    def has(*names: str) -> bool:
        return any((root / n).exists() for n in names)

    if has("pyproject.toml", "setup.py", "setup.cfg") or any(root.glob("requirements*.txt")):
        languages.append("python")
        overrides.update({
            "test_command": f"{py} -m pytest -q --tb=short",
            "lint_command": f"{py} -m ruff check --fix {{file}}",
            "typecheck_command": f"{py} -m mypy {{file}} --ignore-missing-imports --no-error-summary",
            "project_typecheck_command": f"{py} -m mypy . --ignore-missing-imports",
            "gate_extensions": [".py"],
        })
    if has("package.json"):
        languages.append("typescript" if has("tsconfig.json") else "javascript")
        if not overrides:
            pkg = read_json(root / "package.json")
            deps = {**(pkg.get("dependencies") or {}), **(pkg.get("devDependencies") or {})}
            overrides.update({
                "test_command": "npm test --silent",
                "lint_command": "npx --no-install eslint --fix {file}" if "eslint" in deps else None,
                "typecheck_command": None,
                "project_typecheck_command": "npx --no-install tsc --noEmit" if has("tsconfig.json") else None,
                "gate_extensions": [".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"],
            })
    if has("go.mod"):
        languages.append("go")
        if not overrides:
            overrides.update({
                "test_command": "go test ./...",
                "lint_command": "gofmt -l -w {file}",
                "typecheck_command": None,
                "project_typecheck_command": "go vet ./...",
                "gate_extensions": [".go"],
            })
    if has("Cargo.toml"):
        languages.append("rust")
        if not overrides:
            overrides.update({
                "test_command": "cargo test",
                "lint_command": "rustfmt {file}",
                "typecheck_command": None,
                "project_typecheck_command": "cargo check",
                "gate_extensions": [".rs"],
            })
    if not languages:
        languages = ["python"]
        overrides.update({k: v.replace("python ", f"{py} ", 1) if isinstance(v, str) else v
                          for k, v in DEFAULT_CONFIG.items() if k.endswith("_command")})
    overrides["languages"] = languages
    if has("build.sh"):
        overrides["build_command"] = "./build.sh"
    return overrides


def jira_key_from_branch(root: Path) -> str | None:
    try:
        branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True,
                                text=True, cwd=root, timeout=5, check=False).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r"\b([A-Z][A-Z0-9]+)-\d+\b", branch)
    return match.group(1) if match else None


def seed_config(root: Path, report: list[str]) -> None:
    path = root / ".claude" / "framework.json"
    if path.exists():
        current = read_json(path)
        missing = [k for k in DEFAULT_CONFIG if k not in current]
        if missing:
            current.update({k: DEFAULT_CONFIG[k] for k in missing})
            current["schema_version"] = DEFAULT_CONFIG["schema_version"]
            write_json(path, current)
            report.append(f"[MERGE] framework.json: added {', '.join(k for k in missing if k != 'schema_version')}")
        else:
            report.append("[SKIP]  framework.json exists (yours; never overwritten)")
        return
    config = dict(DEFAULT_CONFIG)
    config["project_name"] = root.resolve().name
    config.update(detect_stack(root))
    if key := jira_key_from_branch(root):
        config["jira_project_key"] = key
        report.append(f"[INFO]  Jira project key {key} inferred from branch name; set jira_integration: true to enable")
    write_json(path, config)
    report.append(f"[OK]    framework.json (languages: {', '.join(config['languages'])})")


def seed_state(root: Path, report: list[str]) -> None:
    for template in sorted((TEMPLATES / "state").glob("*.json")):
        dest = root / ".claude" / template.name
        if not dest.exists():
            shutil.copyfile(template, dest)
            report.append(f"[OK]    {template.name}")


def merge_gitignore(root: Path, report: list[str]) -> None:
    dest = root / ".claude" / ".gitignore"
    wanted = [ln.strip() for ln in (TEMPLATES / "claude.gitignore").read_text(encoding="utf-8").splitlines()
              if ln.strip() and not ln.startswith("#")]
    existing = dest.read_text(encoding="utf-8").splitlines() if dest.exists() else []
    missing = [ln for ln in wanted if ln not in {e.strip() for e in existing}]
    if missing:
        with dest.open("a", encoding="utf-8") as fh:
            if existing and existing[-1].strip():
                fh.write("\n")
            fh.write("\n".join(missing) + "\n")
        report.append(f"[MERGE] .claude/.gitignore: +{len(missing)} pattern(s)")


def seed_claude_md(root: Path, report: list[str]) -> None:
    dest = root / "CLAUDE.md"
    if dest.exists():
        report.append("[SKIP]  CLAUDE.md exists")
        return
    shutil.copyfile(TEMPLATES / "CLAUDE.md.template", dest)
    report.append("[OK]    CLAUDE.md from template (fill in the <PLACEHOLDERS>)")


def statusline_command(data_dir: Path) -> str:
    target = data_dir / "statusline"
    return f'bash "{(target / "run.sh").as_posix()}" "{(target / "budget_sentinel.py").as_posix()}"'


def install_statusline(root: Path, data_dir: Path | None, force: bool, report: list[str]) -> None:
    if data_dir is None:
        report.append("[WARN]  No plugin data dir; statusline not wired (budget alerts need it)")
        return
    target = data_dir / "statusline"
    target.mkdir(parents=True, exist_ok=True)
    for name in STATUSLINE_FILES:
        shutil.copyfile(PLUGIN_ROOT / "hooks" / name, target / name)
    path = root / ".claude" / "settings.local.json"
    settings = read_json(path)
    command = statusline_command(data_dir)
    existing = (settings.get("statusLine") or {}).get("command", "")
    if existing and "budget_sentinel.py" not in existing and not force:
        report.append("[SKIP]  statusLine: you already have one in settings.local.json (re-run with --force-statusline)")
        return
    settings["statusLine"] = {"type": "command", "command": command, "refreshInterval": 30}
    write_json(path, settings)
    report.append("[OK]    statusLine -> .claude/settings.local.json (budget sentinel; auto-refreshed on plugin update)")


def merge_team_settings(root: Path, repo: str, report: list[str]) -> None:
    path = root / ".claude" / "settings.json"
    settings = read_json(path)
    markets = settings.setdefault("extraKnownMarketplaces", {})
    # Third-party marketplaces default to auto-update OFF; without this, "sync on every
    # repo update" silently never happens.
    markets[MARKETPLACE_NAME] = {"source": {"source": "github", "repo": repo}, "autoUpdate": True}
    settings.setdefault("enabledPlugins", {})[PLUGIN_ID] = True
    write_json(path, settings)
    report.append(f"[OK]    .claude/settings.json: team marketplace {repo} + {PLUGIN_ID} enabled "
                  "(commit it; on folder trust Claude Code shows teammates the one-line install command)")


def migrate_legacy(root: Path, report: list[str]) -> None:
    path = root / ".claude" / "settings.json"
    settings = read_json(path)
    changed = False
    hooks = settings.get("hooks") or {}
    for event in list(hooks):
        groups = []
        for group in hooks[event] or []:
            kept = [h for h in group.get("hooks", []) if ".claude/hooks/" not in str(h.get("command", "")).replace("\\", "/")]
            if kept:
                group["hooks"] = kept
                groups.append(group)
            elif group.get("hooks"):
                changed = True
        if len(groups) != len(hooks[event] or []):
            changed = True
        if groups:
            hooks[event] = groups
        else:
            del hooks[event]
    if "hooks" in settings and not hooks:
        del settings["hooks"]
    if ".claude/hooks/" in str((settings.get("statusLine") or {}).get("command", "")).replace("\\", "/"):
        del settings["statusLine"]
        changed = True
    if changed:
        write_json(path, settings)
        report.append("[MIGRATE] removed legacy hook/statusLine wiring from .claude/settings.json")
    for rel in LEGACY_FILES:
        legacy = root / rel
        if legacy.is_file():
            try:
                legacy.unlink()
                report.append(f"[MIGRATE] deleted legacy {rel}")
            except OSError as exc:
                report.append(f"[WARN]  could not delete {rel}: {exc}")


def doctor(root: Path, data_dir: Path | None) -> int:
    problems = 0

    def check(ok: bool, good: str, bad: str) -> None:
        nonlocal problems
        print(("  [OK]   " + good) if ok else ("  [FIX]  " + bad))
        problems += 0 if ok else 1

    config_path = root / ".claude" / "framework.json"
    check(sys.version_info >= (3, 10), f"Python {sys.version.split()[0]}", "Python 3.10+ required")
    check(config_path.is_file(), "framework.json present", "no .claude/framework.json -- run /shipwright:init")
    config = {**DEFAULT_CONFIG, **read_json(config_path)}
    check((root / ".git").exists(), "git repository", "not a git repository (drift and branch features disabled)")
    for key in ("test_command", "lint_command", "typecheck_command", "project_typecheck_command", "build_command"):
        cmd = config.get(key)
        if not cmd:
            continue
        exe = str(cmd).split()[0]
        found = shutil.which(exe) is not None or exe.startswith(("./", "echo"))
        module = re.search(r"-m\s+(\w+)", str(cmd))
        if found and module and exe.startswith("python"):
            found = subprocess.run([exe, "-c", f"import {module.group(1)}"], capture_output=True, check=False).returncode == 0
        check(found, f"{key}: {cmd}", f"{key}: `{cmd}` is not runnable here")
    if "echo '[ship]" in str(config.get("build_command")):
        check(False, "", "build_command is still the placeholder -- /shipwright:ship cannot deploy")
    if config.get("jira_integration"):
        check(bool(config.get("jira_project_key")), f"Jira project {config.get('jira_project_key')}",
              "jira_integration is on but jira_project_key is empty")
    local = read_json(root / ".claude" / "settings.local.json")
    check("budget_sentinel.py" in str((local.get("statusLine") or {}).get("command", "")),
          "statusline wired (budget alerts on)", "statusline not wired -- budget alerts are off (/shipwright:init)")
    legacy = read_json(root / ".claude" / "settings.json")
    check(".claude/hooks/" not in json.dumps(legacy).replace("\\\\", "/"),
          "no legacy hook wiring", "legacy copy-installed hooks still wired -- /shipwright:init --migrate")
    if sys.platform == "win32":
        bash_on_path = shutil.which("bash")
        shadowed = bash_on_path and any(marker in bash_on_path for marker in ("System32", "WindowsApps"))
        git_bash = next((p for p in (r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files (x86)\Git\bin\bash.exe")
                         if Path(p).is_file()), None)
        override_set = bool(os.environ.get("CLAUDE_CODE_GIT_BASH_PATH"))
        check(not shadowed or override_set,
              "Git Bash reachable for hooks" + (" (CLAUDE_CODE_GIT_BASH_PATH set)" if override_set else ""),
              f"`bash` on PATH resolves to {bash_on_path} (WSL's launcher stub, not Git Bash) -- "
              + (f"set CLAUDE_CODE_GIT_BASH_PATH to {git_bash!r} in Claude Code's settings"
                 if git_bash else "install Git for Windows, then set CLAUDE_CODE_GIT_BASH_PATH"))
    mem = Path.home() / ".claude" / "projects" / claude_slug(root.resolve()) / "memory"
    print(f"  [INFO] memory dir: {mem} ({'exists' if mem.is_dir() else 'not created yet'})")
    if data_dir:
        print(f"  [INFO] plugin data: {data_dir}")
    print(f"\n{problems} issue(s) found." if problems else "\nAll checks passed.")
    return 1 if problems else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["init", "team", "doctor"])
    parser.add_argument("--project", default=os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    parser.add_argument("--plugin-data", default=os.environ.get("CLAUDE_PLUGIN_DATA"))
    parser.add_argument("--marketplace-repo", default=DEFAULT_MARKETPLACE_REPO)
    parser.add_argument("--team", action="store_true", help="also write team marketplace settings")
    parser.add_argument("--no-statusline", action="store_true")
    parser.add_argument("--force-statusline", action="store_true")
    parser.add_argument("--migrate", action="store_true", help="remove legacy copy-installed hooks")
    args = parser.parse_args()

    root = Path(args.project).expanduser().resolve()
    data_dir = Path(args.plugin_data).expanduser() if args.plugin_data else None
    if not root.is_dir():
        sys.exit(f"Project directory not found: {root}")

    if args.command == "doctor":
        sys.exit(doctor(root, data_dir))

    report: list[str] = []
    (root / ".claude").mkdir(exist_ok=True)
    if args.command == "team":
        merge_team_settings(root, args.marketplace_repo, report)
    else:
        seed_config(root, report)
        seed_state(root, report)
        merge_gitignore(root, report)
        seed_claude_md(root, report)
        if not args.no_statusline:
            install_statusline(root, data_dir, args.force_statusline, report)
        if args.team:
            merge_team_settings(root, args.marketplace_repo, report)
        if args.migrate:
            migrate_legacy(root, report)
        elif ".claude/hooks/" in json.dumps(read_json(root / ".claude" / "settings.json")).replace("\\\\", "/"):
            report.append("[WARN]  legacy copy-installed hooks detected -- re-run with --migrate")
    print("\n".join(report))


if __name__ == "__main__":
    main()
