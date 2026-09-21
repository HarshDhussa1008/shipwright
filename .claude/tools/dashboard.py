"""
Read-only pipeline dashboard.

Renders the state files, the active SDD's risk register and amendments, budget headroom
(with a trend sparkline), pattern trends, git status, and the drop-inbox into a single
self-contained HTML page.

    python .claude/tools/dashboard.py            # write dashboard.html once and print its path
    python .claude/tools/dashboard.py --serve    # serve on localhost, genuinely live:
                                                   each poll re-reads state from disk,
                                                   not a cached file re-sent on a timer.

Read-only by design: it never edits code and never talks to the agent. Nothing here
replaces the CLI loop; it exists for the visual passes a terminal is bad at.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = REPO_ROOT / ".claude"
INBOX_DIR = STATE_DIR / "inbox"
HISTORY_PATH = STATE_DIR / "budget_history.jsonl"
OUTPUT_PATH = STATE_DIR / "dashboard.html"
DEFAULT_PORT = 7399
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2}
SEVERITY_ICON = {"critical": "✖", "high": "▲", "medium": "•"}  # x, up-triangle, dot
STATUS_ICON = {"completed": "✓", "in_progress": "▶", "pending": "○"}  # check, play, circle


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return {}


def read_history() -> list[dict]:
    try:
        lines = HISTORY_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    samples = []
    for line in lines:
        try:
            samples.append(json.loads(line))
        except (json.JSONDecodeError, ValueError):
            continue
    return samples


def git(*args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args], capture_output=True, text=True,
            cwd=REPO_ROOT, timeout=5, check=False,
            encoding="utf-8", errors="replace",  # git emits UTF-8; the locale codec mangles it
        )
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def find_sdd(config: dict, branch: str) -> Path | None:
    sdd_dir = REPO_ROOT / config.get("sdd_path", "docs/sdd")
    if not sdd_dir.is_dir():
        return None
    candidates = sorted(sdd_dir.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not candidates:
        return None
    slug = re.sub(r"[^a-z0-9]+", "-", branch.lower()).strip("-")
    for candidate in candidates:
        if slug and (slug in candidate.stem or candidate.stem in slug):
            return candidate
    return candidates[0]


def parse_section(text: str, heading: str) -> str:
    match = re.search(rf"^##\s+{re.escape(heading)}\s*$(.*?)(?=^##\s|\Z)", text, re.MULTILINE | re.DOTALL)
    return match.group(1).strip() if match else ""


def parse_risks(section: str) -> list[dict[str, str]]:
    risks = []
    for line in section.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4 or set("".join(cells)) <= set("-: "):
            continue
        if cells[0].lower() in {"risk", ""}:
            continue
        risks.append({
            "risk": cells[0], "cls": cells[1], "severity": cells[2],
            "mitigation": cells[3], "status": cells[4] if len(cells) > 4 else "",
        })
    risks.sort(key=lambda r: SEVERITY_ORDER.get(r["severity"].lower(), 3))
    return risks


def bar_html(pct: float, danger: bool) -> str:
    width = max(0.0, min(100.0, pct))
    tone = "danger" if danger else "ok"
    return (
        f'<div class="meter"><div class="bar"><span class="{tone}" style="width:{width:.1f}%"></span></div>'
        f'<span class="pct">{pct:.0f}%</span></div>'
    )


def sparkline_svg(samples: list[dict]) -> str:
    if len(samples) < 2:
        return ""
    width, height, pad = 260, 44, 3
    series = [
        ("ctx", "var(--accent)"),
        ("5h", "var(--warn)"),
        ("7d", "var(--ok)"),
    ]
    n = len(samples)
    step = (width - 2 * pad) / max(1, n - 1)

    def points_for(key: str) -> str | None:
        vals = [s.get(key) for s in samples]
        if all(v is None for v in vals):
            return None
        pts = []
        for i, v in enumerate(vals):
            if v is None:
                continue
            x = pad + i * step
            y = pad + (height - 2 * pad) * (1 - max(0.0, min(100.0, float(v))) / 100.0)
            pts.append(f"{x:.1f},{y:.1f}")
        return " ".join(pts) if len(pts) >= 2 else None

    lines = []
    legend = []
    for key, color in series:
        pts = points_for(key)
        if pts:
            lines.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.6" />')
            legend.append(f'<span style="color:{color}">&#9679;</span> {key}')
    if not lines:
        return ""
    svg = (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'role="img" aria-label="usage trend">{"".join(lines)}</svg>'
    )
    return f'<div class="spark">{svg}<div class="spark-legend dim">{"  ".join(legend)}</div></div>'


def render_budget(budget: dict, threshold: float, history: list[dict]) -> str:
    rows = []
    context = budget.get("context_window") or {}
    if isinstance(context.get("used_percentage"), (int, float)):
        pct = float(context["used_percentage"])
        rows.append(f"<tr><td>context</td><td>{bar_html(pct, pct >= 90)}</td><td></td></tr>")
    for key, label in (("five_hour", "5-hour"), ("seven_day", "7-day"), ("spend_limit", "spend")):
        window = (budget.get("windows") or {}).get(key)
        if not window:
            continue
        pct = float(window.get("used_percentage", 0))
        resets = esc(window.get("resets_at_iso", "")[:16].replace("T", " "))
        rows.append(
            f"<tr><td>{label}</td><td>{bar_html(pct, pct >= threshold)}</td>"
            f"<td class=dim>resets {resets}</td></tr>"
        )
    if not rows:
        return "<p class=dim>No rate-limit data yet. Requires a Pro/Max subscription and one API response.</p>"
    alert = budget.get("alert") or {}
    banner = ""
    if alert.get("tripped"):
        banner = (
            f'<p class="alert">Budget breach: {esc(alert.get("window"))} at '
            f'{float(alert.get("used_percentage", 0)):.0f}% (threshold {esc(alert.get("threshold"))}%)</p>'
        )
    return banner + "<table>" + "".join(rows) + "</table>" + sparkline_svg(history)


def render_tasks(state: dict) -> str:
    tasks = state.get("tasks") or []
    if not tasks:
        return "<p class=dim>No tasks. Run /breakdown.</p>"
    approved = state.get("approved") is True
    badge = "approved" if approved else "awaiting approval"
    counts: dict[str, int] = {}
    rows = []
    for task in tasks:
        status = str(task.get("status", "")).lower()
        counts[status] = counts.get(status, 0) + 1
        flags = []
        if task.get("needs_recheck"):
            flags.append('<span class="flag warn">needs recheck</span>')
        if task.get("jira_sync_error"):
            flags.append('<span class="flag warn">jira sync failed</span>')
        icon = STATUS_ICON.get(status, "")
        rows.append(
            f'<tr data-status="{esc(status)}"><td class=mono>{esc(task.get("id", ""))}</td>'
            f'<td>{esc(task.get("title", ""))} {"".join(flags)}</td>'
            f'<td>{esc(task.get("complexity", ""))}</td>'
            f'<td class="status {esc(status)}">{icon} {esc(task.get("status", ""))}</td>'
            f'<td class=mono>{esc(task.get("jira_key") or "")}</td></tr>'
        )
    filters = "".join(
        f'<button type=button class="chip" data-filter="{esc(s)}">{STATUS_ICON.get(s, "")} {esc(s)} ({c})</button>'
        for s, c in sorted(counts.items())
    )
    return (
        f'<p><span class="flag {"ok" if approved else "warn"}">{badge}</span></p>'
        f'<div class="chips"><button type=button class="chip active" data-filter="">all ({len(tasks)})</button>{filters}</div>'
        '<table class="filterable"><tr><th>id</th><th>task</th><th>size</th><th>status</th><th>jira</th></tr>'
        + "".join(rows) + "</table>"
    )


def render_risks(risks: list[dict[str, str]]) -> str:
    if not risks:
        return "<p class=dim>No risk register in the active SDD. /design Step 4 produces it.</p>"
    rows = [
        f'<tr><td>{esc(r["risk"])}</td><td class=dim>{esc(r["cls"])}</td>'
        f'<td class="sev {esc(r["severity"].lower())}">{SEVERITY_ICON.get(r["severity"].lower(), "")} {esc(r["severity"])}</td>'
        f'<td>{esc(r["mitigation"])}</td><td class=dim>{esc(r["status"])}</td></tr>'
        for r in risks
    ]
    return (
        "<table><tr><th>risk</th><th>class</th><th>severity</th><th>mitigation</th><th>status</th></tr>"
        + "".join(rows) + "</table>"
    )


def render_amendments(sdd_text: str, pending: dict) -> str:
    logged = [l.strip() for l in parse_section(sdd_text, "Amendments").splitlines() if l.strip().startswith("-")]
    candidates = pending.get("candidates") or []
    styles = pending.get("style_candidates") or []

    parts = []
    if len(logged) > 5:
        parts.append(
            f'<p class="alert">{len(logged)} amendments logged - past the 5-entry compaction '
            "threshold. Fold them into the body sections.</p>"
        )
    if logged:
        parts.append("<ul>" + "".join(f"<li>{esc(l.lstrip('- '))}</li>" for l in logged) + "</ul>")
    else:
        parts.append("<p class=dim>No amendments logged. The SDD has not needed correcting yet.</p>")
    if candidates:
        parts.append(f'<p class="flag warn">{len(candidates)} staged, not yet folded in</p>')
        parts.append("<ul>" + "".join(
            f'<li>{esc(c.get("gap", ""))} <span class=dim>({esc(c.get("sdd_section", ""))})</span></li>'
            for c in candidates) + "</ul>")
    if styles:
        parts.append(f'<p class="flag warn">{len(styles)} style correction(s) staged for memory</p>')
    return "".join(parts)


def render_patterns(registry: dict) -> str:
    entries = sorted(registry.items(), key=lambda kv: kv[1].get("count", 0), reverse=True)
    entries = [(k, v) for k, v in entries if v.get("count", 0) > 0]
    if not entries:
        return "<p class=dim>Registry clean.</p>"
    peak = max(v.get("count", 0) for _, v in entries)
    rows = []
    for code, value in entries:
        count = value.get("count", 0)
        written = value.get("memory_written", False)
        rows.append(
            f"<tr><td class=mono>{esc(code)}</td>"
            f"<td>{bar_html(count / peak * 100, count >= 2 and not written)}</td>"
            f'<td class=dim>x{count}{"" if written else " - unwritten" if count >= 2 else ""}</td></tr>'
        )
    return "<table>" + "".join(rows) + "</table>"


def render_inbox() -> str:
    if not INBOX_DIR.is_dir():
        return (
            f"<p class=dim>Drop files into <code>{esc(INBOX_DIR.relative_to(REPO_ROOT))}</code> "
            "and they will be listed here with paths ready to reference.</p>"
        )
    files = sorted((f for f in INBOX_DIR.iterdir() if f.is_file()), key=lambda f: f.stat().st_mtime, reverse=True)
    if not files:
        return f"<p class=dim>Inbox empty: <code>{esc(INBOX_DIR.relative_to(REPO_ROOT))}</code></p>"
    rows = [
        f"<tr><td>{esc(f.name)}</td><td class=dim>{f.stat().st_size:,} B</td>"
        f"<td class=mono>{esc(f.relative_to(REPO_ROOT).as_posix())}</td></tr>"
        for f in files
    ]
    return "<table><tr><th>file</th><th>size</th><th>path to reference</th></tr>" + "".join(rows) + "</table>"


def render_header(project: str) -> str:
    config = read_json(STATE_DIR / "framework.json")
    checkpoint = read_json(STATE_DIR / "checkpoint.json")
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    sdd_path = find_sdd(config, branch)

    phase = ""
    if checkpoint.get("active_skill"):
        phase = f'/{checkpoint["active_skill"]} - phase {checkpoint.get("phase", "?")}: {checkpoint.get("phase_label", "")}'

    return (
        f"<h1>{esc(project)}</h1>"
        f'<div class="sub">{esc(branch) or "no branch"}'
        f'{" &middot; " + esc(phase) if phase else ""}'
        f'{" &middot; SDD: " + esc(sdd_path.relative_to(REPO_ROOT).as_posix()) if sdd_path else " &middot; no SDD found"}'
        f' &middot; generated {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")}Z</div>'
    )


def render_main() -> str:
    config = read_json(STATE_DIR / "framework.json")
    state = read_json(STATE_DIR / "task_state.json")
    checkpoint = read_json(STATE_DIR / "checkpoint.json")
    budget = read_json(STATE_DIR / "budget.json")
    registry = read_json(STATE_DIR / "anti_pattern_registry.json")
    pending = read_json(STATE_DIR / "amendments_pending.json")
    history = read_history()
    threshold = float(config.get("budget_alert_threshold", 95))

    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    dirty = [l for l in git("status", "--porcelain").splitlines() if l.strip()]
    commits = [l for l in git("log", "-8", "--format=%h  %s").splitlines() if l.strip()]

    sdd_path = find_sdd(config, branch)
    sdd_text = ""
    if sdd_path:
        try:
            sdd_text = sdd_path.read_text(encoding="utf-8")
        except OSError:
            sdd_text = ""

    dirty_block = f"<pre>{esc(chr(10).join(dirty[:14]))}</pre>" if dirty else "<p class=dim>Clean.</p>"
    commits_block = f"<pre>{esc(chr(10).join(commits))}</pre>" if commits else "<p class=dim>No commits.</p>"

    return f"""
  <section id="sec-budget"><h2>Budget</h2>{render_budget(budget, threshold, history)}</section>
  <section id="sec-next"><h2>Next action</h2>{
    f'<pre>{esc(checkpoint.get("next_step", ""))}</pre>' if checkpoint.get("next_step")
    else '<p class=dim>No checkpoint. Nothing in flight.</p>'
  }</section>
  <section id="sec-patterns"><h2>Patterns</h2>{render_patterns(registry)}</section>
  <section class="wide" id="sec-tasks"><h2>Tasks</h2>{render_tasks(state)}</section>
  <details class="wide" id="sec-risks" open><summary><h2 class="inline">Risk register</h2></summary>
    {render_risks(parse_risks(parse_section(sdd_text, "Risk Register")))}
  </details>
  <details id="sec-amendments" open><summary><h2 class="inline">Amendments</h2></summary>
    {render_amendments(sdd_text, pending)}
  </details>
  <section id="sec-tree"><h2>Working tree</h2>{dirty_block}</section>
  <section id="sec-commits"><h2>Recent commits</h2>{commits_block}</section>
  <details class="wide" id="sec-inbox" open><summary><h2 class="inline">Inbox</h2></summary>
    {render_inbox()}
  </details>
"""


STYLE = """
:root { --bg:#fbfbfa; --fg:#1d1d1b; --dim:#6b6b66; --line:#e3e3df; --card:#fff;
  --ok:#2f7d5b; --warn:#a8631a; --danger:#b4342b; --accent:#3b5bdb; }
@media (prefers-color-scheme: dark) { :root:not([data-theme=light]) {
  --bg:#16171a; --fg:#e8e8e6; --dim:#8d8d88; --line:#2b2d31; --card:#1d1f23;
  --ok:#4ca97b; --warn:#d18a3c; --danger:#e0645a; --accent:#7f9cf5; } }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--fg); font:14px/1.5 ui-sans-serif,system-ui,-apple-system,Segoe UI,sans-serif; }
header { padding:20px 16px 8px; border-bottom:1px solid var(--line); display:flex; justify-content:space-between; align-items:flex-start; gap:12px; }
h1 { margin:0; font-size:17px; font-weight:650; letter-spacing:-.01em; }
.sub { color:var(--dim); font-size:12.5px; margin-top:4px; }
.hdr-actions { display:flex; align-items:center; gap:8px; flex:0 0 auto; }
#refresh-btn { font:inherit; font-size:12px; padding:5px 10px; border-radius:6px; border:1px solid var(--line); background:var(--card); color:var(--fg); cursor:pointer; }
#refresh-btn:hover { border-color:var(--accent); }
#live-dot { width:7px; height:7px; border-radius:50%; background:var(--ok); display:inline-block; }
#live-dot.stale { background:var(--dim); }
main { padding:16px; display:grid; gap:14px; grid-template-columns:repeat(auto-fit,minmax(330px,1fr)); max-width:1500px; }
section, details { background:var(--card); border:1px solid var(--line); border-radius:9px; padding:13px 15px; min-width:0; }
.wide { grid-column:1/-1; }
h2 { margin:0 0 9px; font-size:11px; font-weight:650; text-transform:uppercase; letter-spacing:.07em; color:var(--dim); }
h2.inline { display:inline; margin:0; }
summary { cursor:pointer; margin:-13px -15px 9px; padding:13px 15px 9px; list-style:none; }
summary::-webkit-details-marker { display:none; }
summary::before { content:"\\25be"; display:inline-block; margin-right:6px; color:var(--dim); transition:transform .15s; }
details:not([open]) summary::before { transform:rotate(-90deg); }
table { width:100%; border-collapse:collapse; }
th { text-align:left; font-size:10.5px; text-transform:uppercase; letter-spacing:.05em; color:var(--dim); font-weight:600; padding:0 8px 5px 0; }
td { padding:4px 8px 4px 0; border-top:1px solid var(--line); vertical-align:top; }
tr:first-child td { border-top:none; }
.dim { color:var(--dim); font-size:12.5px; }
.mono { font-family:ui-monospace,SFMono-Regular,Consolas,monospace; font-size:12px; }
.meter { display:flex; align-items:center; gap:9px; white-space:nowrap; }
.bar { flex:1 1 auto; min-width:60px; max-width:170px; height:7px; background:var(--line); border-radius:4px; overflow:hidden; }
.bar span { display:block; height:100%; }
.bar .ok { background:var(--accent); } .bar .danger { background:var(--danger); }
.pct { flex:0 0 auto; font-variant-numeric:tabular-nums; font-size:12.5px; }
.flag { display:inline-block; font-size:10.5px; padding:1px 7px; border-radius:20px; border:1px solid currentColor; margin-left:5px; }
.flag.ok { color:var(--ok); } .flag.warn { color:var(--warn); }
.alert { color:var(--danger); font-weight:600; margin:0 0 8px; font-size:13px; }
.sev.critical { color:var(--danger); font-weight:650; }
.sev.high { color:var(--warn); font-weight:600; }
.status.completed { color:var(--ok); } .status.in_progress { color:var(--accent); } .status.pending { color:var(--dim); }
ul { margin:0; padding-left:17px; } li { margin:2px 0; }
pre { margin:0; font-family:ui-monospace,Consolas,monospace; font-size:12px; white-space:pre-wrap; word-break:break-word; }
code { font-family:ui-monospace,Consolas,monospace; font-size:12px; }
.chips { display:flex; flex-wrap:wrap; gap:6px; margin-bottom:9px; }
.chip { font:inherit; font-size:11px; padding:3px 9px; border-radius:20px; border:1px solid var(--line); background:transparent; color:var(--dim); cursor:pointer; }
.chip.active { border-color:var(--accent); color:var(--accent); }
.spark { margin-top:8px; }
.spark-legend { margin-top:2px; font-size:10.5px; display:flex; gap:10px; }
"""

LIVE_SCRIPT = """
(function () {
  var main = document.getElementById("app-main");
  var header = document.getElementById("app-header");
  var dot = document.getElementById("live-dot");
  var btn = document.getElementById("refresh-btn");

  function captureOpenState() {
    var state = {};
    main.querySelectorAll("details[id]").forEach(function (d) { state[d.id] = d.open; });
    return state;
  }
  function applyOpenState(state) {
    Object.keys(state).forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.open = state[id];
    });
  }
  function applyFilter() {
    var table = main.querySelector("table.filterable");
    if (!table) return;
    var chips = main.querySelectorAll(".chip");
    var active = main.querySelector(".chip.active");
    var filter = active ? active.getAttribute("data-filter") : "";
    table.querySelectorAll("tr[data-status]").forEach(function (tr) {
      tr.style.display = (!filter || tr.getAttribute("data-status") === filter) ? "" : "none";
    });
  }
  function wireChips() {
    main.querySelectorAll(".chip").forEach(function (chip) {
      chip.addEventListener("click", function () {
        main.querySelectorAll(".chip").forEach(function (c) { c.classList.remove("active"); });
        chip.classList.add("active");
        applyFilter();
      });
    });
  }

  function refresh() {
    fetch("/fragment", { cache: "no-store" }).then(function (r) { return r.json(); }).then(function (data) {
      var scrollY = window.scrollY;
      var openState = captureOpenState();
      header.innerHTML = data.header;
      main.innerHTML = data.main;
      applyOpenState(openState);
      wireChips();
      applyFilter();
      window.scrollTo(0, scrollY);
      dot.classList.remove("stale");
    }).catch(function () {
      dot.classList.add("stale");
    });
  }

  wireChips();
  applyFilter();
  btn.addEventListener("click", refresh);
  setInterval(refresh, 10000);
})();
"""


def build_page(project: str, header_html: str, main_html: str, live: bool) -> str:
    script = f"<script>{LIVE_SCRIPT}</script>" if live else ""
    actions = (
        '<div class="hdr-actions"><span id="live-dot"></span>'
        '<button id="refresh-btn" type="button">Refresh now</button></div>'
        if live else ""
    )
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(project)} pipeline</title>
<style>{STYLE}</style></head><body>
<header id="app-header-wrap"><div id="app-header">{header_html}</div>{actions}</header>
<main id="app-main">{main_html}</main>
{script}
</body></html>
"""


def project_name() -> str:
    config = read_json(STATE_DIR / "framework.json")
    return config.get("project_name", REPO_ROOT.name)


class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:
        pass  # keep the terminal quiet; this is a local dev tool, not a service

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path in ("/", "/dashboard.html"):
            project = project_name()
            body = build_page(project, render_header(project), render_main(), live=True).encode("utf-8")
            self._send(200, "text/html; charset=utf-8", body)
        elif self.path == "/fragment":
            payload = json.dumps({"header": render_header(project_name()), "main": render_main()}).encode("utf-8")
            self._send(200, "application/json", payload)
        else:
            self._send(404, "text/plain; charset=utf-8", b"not found")


def serve_forever(port: int) -> None:
    with ThreadingHTTPServer(("127.0.0.1", port), DashboardHandler) as httpd:
        print(f"Dashboard: http://127.0.0.1:{port}/  (Ctrl+C to stop; each load/refresh re-reads live state)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Render the shipwright pipeline dashboard.")
    parser.add_argument("--serve", action="store_true", help="serve on localhost, live-refreshing")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    project = project_name()
    try:
        OUTPUT_PATH.write_text(
            build_page(project, render_header(project), render_main(), live=False), encoding="utf-8"
        )
    except OSError as exc:
        print(f"Could not write {OUTPUT_PATH}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if args.serve:
        serve_forever(args.port)
    else:
        print(OUTPUT_PATH)


if __name__ == "__main__":
    main()
