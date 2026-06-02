# Implementation Flow

## Phase 1 — Deep Analysis
1. Read the full SDD
2. Identify: all new files, all modified files, all deleted files
3. Identify: external dependencies (libraries, APIs, datastores)
4. Flag any SDD ambiguities — resolve before writing code

## Phase 2 — File Structure Proposal
Present a tree like:
```
src/
  feature/
    __init__.py
    models.py        # data models
    repository.py    # data access
    service.py       # business logic
    api.py           # HTTP handlers
  tests/
    test_models.py
    test_service.py
```
Wait for explicit user confirmation before proceeding.

## Phase 3 — Implement (dependency order)
Implement in this order:
1. Data models (no dependencies)
2. Repository / data access layer (depends on models)
3. Service / business logic (depends on repository)
4. API / interface layer (depends on service)
5. Tests (can be written alongside each layer)

After each file: run the quality gate mentally — does it satisfy the standards in `python-standards.md`?

## Phase 4 — Pre-Commit Audit
Before declaring implementation complete, verify:

- [ ] All function signatures have type hints
- [ ] No `Optional[X]` — using `X | None`
- [ ] No bare `pass` or `# TODO` in non-test code
- [ ] Tests exist for every public function
- [ ] No circular imports
- [ ] Error handling at all external boundaries
- [ ] Observability: key operations have log statements
- [ ] No secrets or credentials in code

## Phase 5 — Handoff
Output:
```
Implementation complete.
Files created: <list>
Files modified: <list>
Tests: <count> test functions across <count> files
Next: run /ship staging
```
