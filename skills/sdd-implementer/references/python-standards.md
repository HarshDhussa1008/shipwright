# Python Implementation Standards

## Type Hints
- Required on all function signatures — parameters and return types
- Use `X | None` not `Optional[X]` (PEP 604 / ruff UP007)
- Use `list[str]` not `List[str]`, `dict[str, int]` not `Dict[str, int]`
- No bare `Any` — use specific types or `TypeVar`

## Code Style
- No docblocks or multi-line comment blocks — name things clearly instead
- One short inline comment max, only when the WHY is non-obvious
- No `# noqa` or `# type: ignore` without a written memory explaining why
- Prefer `pathlib.Path` over `os.path`
- Prefer f-strings over `.format()` or `%`

## Structure
- Functions do one thing. If you need to describe it with "and", split it.
- No global mutable state
- Dataclasses or TypedDict for structured data — no bare dicts for domain objects
- `__slots__` on hot-path dataclasses

## Error Handling
- Validate at system boundaries (user input, external APIs) — not internally
- Raise specific exceptions, not bare `Exception`
- Never silently swallow exceptions (`except Exception: pass`)
- Log before re-raising in infrastructure code

## Testing
- Tests live alongside code (e.g., `foo.py` → `test_foo.py` in the same directory)
- Use `pytest` — no `unittest.TestCase` unless integrating with legacy code
- Mock external I/O (network, disk, time) — never mock your own internal code
- Each test asserts one thing; use parametrize for multiple inputs
- Test the public interface, not private implementation details

## Dependencies
- Prefer standard library over third-party for simple tasks
- Pin versions in `requirements.txt` / `pyproject.toml`
- No circular imports — enforce with module boundary discipline

## Performance
- Use generators for large sequences — avoid materializing full lists
- Profile before optimizing — no premature optimization
- `asyncio` for I/O-bound concurrency; `multiprocessing` for CPU-bound
