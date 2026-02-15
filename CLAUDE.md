# CLAUDE.md

This file provides context for AI coding agents working with this repository.

## Project Overview

**Aegra** is an open-source, self-hosted alternative to LangGraph Platform. It's a production-ready Agent Protocol server that allows you to run AI agents on your own infrastructure without vendor lock-in.

**Key characteristics:**
- Drop-in replacement for LangGraph Platform using the same LangGraph SDK
- Self-hosted on your own PostgreSQL database
- Agent Protocol compliant (works with Agent Chat UI, LangGraph Studio, CopilotKit)
- Python 3.11+ with FastAPI and PostgreSQL

## Quick Start Commands

```bash
# Install dependencies (from repo root)
uv sync --all-packages

# Start dev server (postgres + auto-migrations + hot reload)
uv run aegra dev

# Run tests
uv run --package aegra-api pytest libs/aegra-api/tests/
uv run --package aegra-cli pytest libs/aegra-cli/tests/

# Lint and format
uv run ruff check .
uv run ruff format .

# Type checking
uv run mypy libs/aegra-api/src/ libs/aegra-cli/src/

# All CI checks at once
make ci-check

# Database migrations (run automatically on server startup)
# To create a new migration:
uv run --package aegra-api alembic revision --autogenerate -m "description"
```

## Project Structure

```
aegra/
├── libs/
│   ├── aegra-api/                    # Core API package
│   │   ├── src/aegra_api/            # Main application code
│   │   │   ├── api/                  # Agent Protocol endpoints
│   │   │   ├── services/             # Business logic layer
│   │   │   ├── core/                 # Infrastructure (database, auth, orm, health, migrations)
│   │   │   ├── models/               # Pydantic request/response schemas
│   │   │   ├── middleware/           # ASGI middleware
│   │   │   ├── observability/        # OpenTelemetry tracing (Langfuse, Phoenix, OTLP)
│   │   │   ├── utils/               # Helper functions
│   │   │   ├── main.py               # FastAPI app entry point
│   │   │   ├── config.py             # aegra.json config loading
│   │   │   └── settings.py           # Environment settings
│   │   ├── tests/                    # Test suite
│   │   └── alembic/                  # Database migrations
│   │
│   └── aegra-cli/                    # CLI package
│       └── src/aegra_cli/
│           ├── cli.py                # Main CLI entry point
│           ├── env.py                # .env file loading
│           ├── commands/             # Command implementations (init)
│           ├── utils/                # Docker utilities
│           └── templates/            # Project templates for `aegra init`
│
├── examples/                         # Example agents and configs
├── docs/                             # Documentation
├── aegra.json                        # Project configuration (graphs, auth, http, store)
└── docker-compose.yml                # Local development setup
```

**Key principle:** LangGraph handles ALL state persistence and graph execution. FastAPI provides only HTTP/Agent Protocol compliance.

## Development Rules

### Type Annotations (STRICT)
- **EVERY function MUST have explicit type annotations** for ALL parameters AND the return type. No exceptions.
- If a function returns nothing, annotate it `-> None`. Never leave the return type blank.
- Use `X | None` union syntax (Python 3.10+), not `Optional[X]`.
- Use `collections.abc` types (`Sequence`, `Mapping`, `Iterator`) over `typing` equivalents where possible.
- Annotate class attributes and module-level variables when the type is not obvious from the assignment.
- This applies to **all** code you write or modify: production code, tests, helpers, fixtures, scripts — everything.

```python
# CORRECT
def create_user(name: str, age: int) -> User: ...
def process(items: list[str]) -> None: ...
async def fetch(url: str) -> dict[str, Any]: ...

# WRONG — missing return type, missing param types
def create_user(name, age): ...
def process(items): ...
```

### Import Conventions
- Use absolute imports with `aegra_api.*` prefix.
- **ALWAYS place imports at the top of the file.** Never use inline/lazy imports inside functions unless there is a **proven circular dependency** (confirmed by actual `ImportError`) or the import is from an **optional dependency** that may not be installed (wrapped in `try/except ImportError`). "Might be slow" or "only used here" are NOT valid reasons for inline imports. If unsure, put it at the top — only move inline after confirming the import cycle with an actual error.

### Error Handling
- **NEVER use bare `except:` or `except Exception: pass`.** Always catch specific exceptions.
- Handle errors at function entry with **guard clauses and early returns** — place the happy path last.
- Keep exactly **ONE statement** in each `try` block when possible. Narrow the scope of exception handling.
- Use `HTTPException` for expected API errors. Use middleware for unexpected errors.
- **NEVER silently swallow exceptions.** If you catch an exception, log it or re-raise it. `except SomeError: pass` is almost always wrong.
- Use context managers (`with` statements) for resource cleanup.

```python
# CORRECT — guard clause, specific exception
def get_user(user_id: str) -> User:
    if not user_id:
        raise ValueError("user_id is required")
    try:
        return db.fetch_user(user_id)
    except UserNotFoundError:
        raise HTTPException(status_code=404, detail="User not found")

# WRONG — broad catch, swallowed exception, happy path buried
def get_user(user_id):
    try:
        if user_id:
            user = db.fetch_user(user_id)
            if user:
                return user
    except Exception:
        pass
    return None
```

### Function Design
- **NEVER use mutable default arguments** (`def f(items=[])` or `def f(data={})`). Use `None` and create inside the function.
- Functions with **5+ parameters MUST use keyword-only arguments** (add `*` separator).
- Return early to reduce nesting.
- Prefer pure functions — return values rather than modifying inputs.

```python
# CORRECT — keyword-only args, immutable default
def create_assistant(name: str, *, graph_id: str, config: dict | None = None, metadata: dict | None = None) -> Assistant:
    config = config or {}
    ...

# WRONG — mutable default, too many positional args
def create_assistant(name, graph_id, config={}, metadata={}, version=1, context={}):
    ...
```

### Testing (STRICT)
- **Bug fixes REQUIRE regression tests. New features REQUIRE tests.** No exceptions.
- Follow the **Arrange-Act-Assert** pattern.
- Test **edge cases AND invalid inputs** — not just the happy path.
- Test names must describe the expected behavior: `test_returns_404_when_assistant_not_found`, not `test_get_assistant_2`.
- Use `pytest` — never `unittest` classes.
- Tests must be async-aware using `pytest-asyncio`.
- Use fixtures from `tests/conftest.py`.
- Mock external dependencies (databases, APIs). Prefer `monkeypatch` over `unittest.mock` where possible.
- **NEVER mark a task as complete without running the tests and confirming they pass.**

### LLM Agent Anti-Patterns (IMPORTANT)
These rules exist because AI agents repeatedly make these mistakes. Follow them carefully:

- **Only modify code related to the task at hand.** Do not "helpfully" refactor, rename, or clean up adjacent code — this introduces breakage and scope creep.
- **When tests fail, fix the ROOT CAUSE, not the symptom.** Do not delete failing assertions, weaken test conditions, or add workarounds to make tests pass. Investigate why the test fails and fix the underlying bug.
- **NEVER add conditional logic that returns hardcoded values for specific test inputs.** This is cheating, not fixing.
- **Follow existing patterns EXACTLY.** Before writing new code, read the surrounding codebase and mimic its style, naming conventions, and patterns. Do not invent new patterns when established ones exist.
- **Do not assume a library is available.** Check `pyproject.toml` before importing a new dependency.
- **If you don't understand why code exists, ask or leave it alone** (Chesterton's Fence).
- **NEVER commit commented-out code.** Delete it or keep it — no middle ground.

### Security
- NEVER store secrets, API keys, or passwords in code — only in `.env` files or environment variables.
- NEVER log sensitive information (passwords, tokens, PII).
- Use parameterized queries / ORM — never raw string SQL.
- NEVER use `eval()`, `exec()`, or `pickle` on user input.
- Use `subprocess.run([...], shell=False)` — never `shell=True` with user input.

## Architecture

### Database Architecture
The system uses two connection pools:
1. **SQLAlchemy Pool** (asyncpg driver) - Metadata tables: assistants, threads, runs
2. **LangGraph Pool** (psycopg driver) - State checkpoints, vector embeddings

**URL format:** LangGraph requires `postgresql://` while SQLAlchemy uses `postgresql+asyncpg://`

### Configuration
**aegra.json** defines graphs, auth, HTTP config, and store settings. See `docs/configuration.md` for full reference.

### Graph Loading
Agents are Python modules exporting a compiled `graph` variable:
```python
builder = StateGraph(State)
# ... define nodes and edges
graph = builder.compile()  # Must export as 'graph'
```

## Common Tasks

### Adding a New Graph
1. Create a new directory in `examples/`
2. Define your state schema and graph logic
3. Export compiled graph as `graph` variable
4. Add entry to `aegra.json` under `graphs`

### Adding a New API Endpoint
1. Create or modify router in `libs/aegra-api/src/aegra_api/api/`
2. Add Pydantic models in `libs/aegra-api/src/aegra_api/models/`
3. Implement business logic in `libs/aegra-api/src/aegra_api/services/`
4. Register router in `libs/aegra-api/src/aegra_api/main.py`

### Database Schema Changes
1. Modify SQLAlchemy models in `libs/aegra-api/src/aegra_api/core/orm.py`
2. Generate migration: `uv run --package aegra-api alembic revision --autogenerate -m "description"`
3. Review generated migration in `libs/aegra-api/alembic/versions/`
4. Apply: migrations run automatically on next server startup

## PR Guidelines

- Run `make test` (or `uv run --package aegra-api pytest libs/aegra-api/tests/`) before committing
- Run `make lint` (or `uv run ruff check .`) for linting
- Include tests for new functionality
- Update migrations if modifying database schema
- Title format: `[component] Brief description`

### Documentation Updates (STRICT)
- **EVERY code change that affects user-facing behavior MUST include corresponding documentation updates.** This is NOT optional — treat docs as part of the implementation, not a follow-up task.
- Check ALL of these locations for references that may need updating:
  - `README.md` (root), `libs/aegra-api/README.md`, `libs/aegra-cli/README.md`
  - `CLAUDE.md` (this file)
  - `docs/` directory (developer-guide, migration-cheatsheet, configuration, authentication, custom-routes, etc.)
- When adding/removing CLI flags, commands, or config options: search all docs for the old flag/command name and update every occurrence.
- When changing API behavior, default values, or startup behavior: update the relevant docs to reflect the new behavior.
- A PR that changes behavior without updating docs is **incomplete**. Do not consider the task done until docs are updated.

### Environment Variable Files (STRICT)
- There are **two `.env.example` files** that MUST be kept in sync:
  1. **`/.env.example`** — Root file used for development and documentation reference
  2. **`libs/aegra-cli/src/aegra_cli/templates/env.example.template`** — Template used by `aegra init` to generate `.env.example` for new projects (uses `$slug` placeholders for project-specific values)
- When adding, removing, or modifying any environment variable: **update BOTH files**.
- The template uses `$slug` in place of project-specific values (`PROJECT_NAME`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `DATABASE_URL` comment). All other values should be identical between the two files.

### Versioning (STRICT)
- **`aegra-api` and `aegra-cli` MUST always have the same version.** Both versions live in their respective `pyproject.toml` files (`libs/aegra-api/pyproject.toml` and `libs/aegra-cli/pyproject.toml`).
- **`aegra-cli` depends on `aegra-api~=X.Y.Z`** (compatible release). This allows patch updates (X.Y.Z+1) without changing the constraint, but a **minor bump requires updating the constraint** in `aegra-cli/pyproject.toml`.
- **Pre-1.0.0 versioning (current):** While in beta (`0.x.y`), the version scheme is `0.MAJOR.PATCH`:
  - **Patch** (0.5.1 → 0.5.2): Bug fixes, small improvements, new features, non-breaking additions. Update `version` in BOTH `pyproject.toml` files.
  - **Minor** (0.5.x → 0.6.0): Breaking changes (removed/renamed endpoints, changed behavior, schema migrations). Update `version` in BOTH `pyproject.toml` files AND update the `aegra-api~=` constraint in `aegra-cli/pyproject.toml`.
  - **1.0.0**: Reserved for when the public API is considered stable and we commit to full SemVer guarantees. This is a deliberate decision, not triggered by a single change.
- **Post-1.0.0 versioning (future):** Standard SemVer applies:
  - **Patch** (1.0.0 → 1.0.1): Bug fixes only.
  - **Minor** (1.0.x → 1.1.0): New features, non-breaking additions.
  - **Major** (1.x.y → 2.0.0): Breaking changes.
- **Always bump the version before creating a PR.** Determine the bump type from the changes:
  - Bug fix, small improvement, or new non-breaking feature → patch bump
  - Breaking change (removed/renamed API, changed defaults, schema migration) → minor bump
- **`aegra` meta-package** (on PyPI, not in this repo) is a name reservation that points to `aegra-cli`. It does not need to be updated on every release.
