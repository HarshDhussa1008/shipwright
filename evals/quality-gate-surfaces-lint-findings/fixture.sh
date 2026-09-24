#!/bin/sh
# Harness-run scaffold: configures a fake lint_command (no real toolchain needed -- it
# always reports one deterministic finding) so this case can prove quality_gate.py's
# PostToolUse plumbing end to end: it runs the configured command against the edited
# file and returns the findings to Claude via additionalContext, without needing ruff,
# eslint or any other real linter installed in the eval sandbox.
set -eu
mkdir -p .claude src
cat > lint_stub.sh <<'EOF'
#!/bin/sh
echo "FAKE001 unused-import: 'os' imported but unused (line 1)"
exit 1
EOF
chmod +x lint_stub.sh
cat > .claude/framework.json <<'EOF'
{"schema_version": 2, "project_name": "evalproj", "approval_gate": false, "sdd_path": "docs/sdd", "gate_extensions": [".py"], "test_command": "echo ok", "lint_command": "sh lint_stub.sh {file}", "typecheck_command": null, "project_typecheck_command": null, "build_command": "echo ok", "jira_integration": false, "slack_integration": false, "budget_alert_threshold": 95, "jira_transitions": {}}
EOF
cat > .claude/task_state.json <<'EOF'
{"feature_branch": "", "parent_jira_key": null, "sdd_path": null, "approved": true, "approved_at": null, "approved_by": null, "tasks_created_at": null, "retro_offered": false, "last_memory_write": null, "last_test_run": null, "tasks": []}
EOF
echo '{}' > .claude/checkpoint.json
echo '{"candidates": [], "style_candidates": []}' > .claude/amendments_pending.json
echo '{}' > .claude/anti_pattern_registry.json
