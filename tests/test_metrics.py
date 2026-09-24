"""tools/metrics.py -- the pipeline-metrics CLI skills shell out to, and the summarize()
rollup the dashboard renders. Uses the same subprocess-driven Proj fixture as the hooks."""

from __future__ import annotations

import json
import sys

from conftest import ROOT, Proj

METRICS = ROOT / "tools" / "metrics.py"


def run_metrics(project: Proj, *args: str) -> str:
    import subprocess

    result = subprocess.run(
        [sys.executable, str(METRICS), *args], capture_output=True, text=True,
        env=project.env, timeout=30, check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def record(project: Proj, event: str, data: dict) -> None:
    run_metrics(project, "record", "--project", str(project.root), "--event", event, "--data", json.dumps(data))


def test_record_appends_jsonl_line(project: Proj) -> None:
    record(project, "ship", {"env": "staging", "result": "pass"})
    rows = [json.loads(ln) for ln in (project.claude / "metrics.jsonl").read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["event"] == "ship" and rows[0]["env"] == "staging" and "t" in rows[0]


def test_summary_json_groups_adversary_by_sdd_path(project: Proj) -> None:
    # two passes recorded for the SAME feature (a re-run after amendments) must count once,
    # by its latest outcome -- not once per recording
    record(project, "adversary_pass", {"passes": 1, "risks_critical": 1, "risks_high": 2, "risks_medium": 0,
                                       "converged": False, "sdd_path": "docs/sdd/x.md"})
    record(project, "adversary_pass", {"passes": 2, "risks_critical": 0, "risks_high": 0, "risks_medium": 1,
                                       "converged": True, "sdd_path": "docs/sdd/x.md"})
    record(project, "adversary_pass", {"passes": 1, "risks_critical": 0, "risks_high": 1, "risks_medium": 0,
                                       "converged": True, "sdd_path": "docs/sdd/y.md"})
    out = run_metrics(project, "summary", "--project", str(project.root), "--json")
    result = json.loads(out)
    assert result["adversary"]["features"] == 2  # x.md and y.md, not 3 recordings
    assert result["adversary"]["converged"] == 2  # x.md's LATEST row converged; y.md converged
    assert result["adversary"]["convergence_rate_pct"] == 100.0


def test_quality_gate_hit_rate_and_ship_pass_rate(project: Proj) -> None:
    record(project, "quality_gate", {"file": "a.py", "lint": 0, "types": 0, "clean": True})
    record(project, "quality_gate", {"file": "b.py", "lint": 2, "types": 1, "clean": False})
    record(project, "ship", {"env": "staging", "result": "pass"})
    record(project, "ship", {"env": "prod", "result": "fail", "gate_failed": "Gate 1 - Tests"})
    out = run_metrics(project, "summary", "--project", str(project.root), "--json")
    result = json.loads(out)
    assert result["quality_gate"]["hit_rate_pct"] == 50.0
    assert result["ship"]["pass_rate_pct"] == 50.0
    assert result["ship"]["failed_gates"] == {"Gate 1 - Tests": 1}


def test_summary_empty_is_all_none_not_a_crash(project: Proj) -> None:
    out = run_metrics(project, "summary", "--project", str(project.root), "--json")
    result = json.loads(out)
    assert result["total_events"] == 0
    assert result["quality_gate"]["hit_rate_pct"] is None
    assert result["ship"]["pass_rate_pct"] is None


def test_record_rejects_non_object_data(project: Proj) -> None:
    import subprocess

    result = subprocess.run(
        [sys.executable, str(METRICS), "record", "--project", str(project.root), "--event", "x", "--data", "[1, 2]"],
        capture_output=True, text=True, env=project.env, timeout=30, check=False,
    )
    assert result.returncode == 1
    assert not (project.claude / "metrics.jsonl").exists()


def test_metrics_file_caps_at_max_lines(project: Proj) -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location("_common", ROOT / "hooks" / "_common.py")
    assert spec and spec.loader
    common = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(common)
    proj = common.Project(project.root)
    for i in range(5010):
        common.record_metric(proj, "ship", n=i)
    lines = proj.metrics.read_text(encoding="utf-8").splitlines()
    assert len(lines) == common.METRICS_MAX_LINES
    assert json.loads(lines[-1])["n"] == 5009  # most recent survives the trim
