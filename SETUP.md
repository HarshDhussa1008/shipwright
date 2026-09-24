# Setup guide

## Prerequisites

| Requirement | Notes |
|---|---|
| Claude Code | CLI, desktop app or IDE extension, recent enough for plugins |
| Python 3.10+ | `python3`, `python` or `py -3` on PATH (or set `SHIPWRIGHT_PYTHON`) |
| Git Bash (Windows) | Claude Code runs hooks through it; hooks invoke `run.sh` via `bash`, which Git Bash always provides — the pitfall is forward slashes: any command string referencing `run.sh` must not use a literal backslash path, which Git Bash's MSYS runtime silently mangles |
| Your toolchain | Whatever `lint_command` / `typecheck_command` / `test_command` name — `/shipwright:doctor` checks them |
| Jira MCP (optional) | The Atlassian remote MCP or the community `mcp-atlassian` server |
| Slack MCP (optional) | For deploy notifications |

## 1. Install the plugin

In Claude Code:
```
/plugin marketplace add HarshDhussa1008/shipwright
/plugin install shipwright@shipwright
```
Then `/plugin` → **Marketplaces** → shipwright → **Enable auto-update** (third-party marketplaces default to off).

## 2. Initialise a project

Open Claude Code in the project and run `/shipwright:init`. It is safe to re-run.

## 3. Team rollout (optional)

`/shipwright:init --team`, then commit `.claude/settings.json`. Teammates who trust the folder are offered the install, with auto-update on. To host from your org, fork the repo and use `--marketplace-repo your-org/shipwright`.

## Migrating from the copy-installed version (v1)

v1 copied hooks into `.claude/hooks/` and wired them in `.claude/settings.json`. With the plugin installed those would fire twice, and several of them never worked (they read environment variables Claude Code does not set). Run:

```
/shipwright:init --migrate
```

It removes the legacy hook and statusline wiring (your own hooks are kept), deletes the framework-owned `.claude/hooks/*.py`, `.claude/tools/dashboard.py` and `.claude/session_id`, and adds any new `framework.json` settings. Your config, state, SDDs and memories are untouched. The skills v1 copied into `~/.claude/skills/{design,breakdown,ship,retro,dashboard,sdd-implementer}` can be deleted once you use the `/shipwright:*` versions.

## Jira

1. Connect a Jira MCP server.
2. In `.claude/framework.json`: `jira_integration: true`, `jira_project_key`.
3. Check `jira_transitions` matches your workflow's **status names** (`/shipwright:ship` finds the transition that leads to that status).
4. Name branches with the parent key (`feature/PAY-123-rate-limit`); `/shipwright:breakdown` asks if it can't find one.

The skills name the tools for both common servers (`getJiraIssue` / `jira_get_issue`, `createJiraIssue` / `jira_create_issue`, `transitionJiraIssue` / `jira_transition_issue`, `addCommentToJiraIssue` / `jira_add_comment`). Tasks under an Epic are created as Stories with the `parent` field.

## Memory

Claude Code keeps project memory in `~/.claude/projects/<project-folder>/memory/`, where `<project-folder>` is the absolute path with every non-alphanumeric character replaced by `-`. The hooks locate it from the session's transcript path, so no configuration is needed; set `memory_path` to override. `/shipwright:design`, `/shipwright:retro` and `/shipwright:remember` write memories; the SessionStart hook re-injects the three most relevant each session.

## The dashboard

`/shipwright:dashboard` writes `.claude/dashboard.html`; `/shipwright:dashboard serve` serves it on `127.0.0.1:7399` with live refresh. Files dropped in `.claude/inbox/` are listed with paths ready to reference.

## Troubleshooting

- Something doesn't fire → `/shipwright:doctor`.
- See hook activity → run `claude --debug` and look for `shipwright` lines, or set `SHIPWRIGHT_DEBUG=1` to surface hook exceptions.
- Approval gate in the way of unrelated work → `/shipwright:checkpoint clear-plan`, or `approval_gate: false`.
