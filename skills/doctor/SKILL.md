---
name: doctor
description: Diagnose a shipwright installation — Python version, framework.json, whether the configured test/lint/typecheck/build commands actually run, Jira config, statusline wiring, and legacy hook wiring. Use when something in the pipeline seems not to fire, or after setup.
---

# /shipwright:doctor — installation health check

```bash
bash "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" "${CLAUDE_PLUGIN_ROOT}/tools/bootstrap.py" doctor \
  --project "${CLAUDE_PROJECT_DIR:-$PWD}" --plugin-data "${CLAUDE_PLUGIN_DATA}"
```

Relay the `[FIX]` lines with the concrete fix for each (install the missing tool, correct the command in `.claude/framework.json`, or run `/shipwright:init` / `/shipwright:init --migrate`). Offer to apply the config fixes yourself. If everything passes, say so in one line.
