# Contributing

## Setup

Requires [uv](https://docs.astral.sh/uv/) and Node 20+. If you don't have uv installed:

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh   # macOS/Linux
```

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"   # Windows
```

```sh
git clone <repo>
cd menagerist
uv run poe init   # sync all deps and install git hooks
```

`poe` and the `menagerist` CLI live in the project's `.venv`, not your global PATH. Every `poe` command elsewhere in this doc is written bare (`poe test`, `poe lint`, ...) and assumes that venv is active:

```sh
source .venv/bin/activate       # Linux/macOS
```

```powershell
.venv\Scripts\Activate.ps1      # Windows PowerShell
```

Skipping activation is fine too — just prefix each command with `uv run` instead, e.g. `uv run poe test`.

Start the full stack (Docker required):

```sh
poe db-up && poe migrate && poe serve  # Postgres in Docker + backend at :8000 + frontend at :5173
# or
docker compose up  # full stack including Postgres, all containerized
```

### Manually, without `poe`

```sh
uv sync --all-packages --group dev
cd frontend && npm install && cd ..

docker compose up -d postgres

uv run menagerist migrate upgrade
uv run menagerist serve --host 0.0.0.0 --reload   # backend at :8000
```

```sh
cd frontend && npm run dev -- --host 0.0.0.0       # frontend at :5173, in a second shell
```

## Common tasks

```sh
poe sync                      # re-sync all deps and regenerate the API client (run after pulling)
poe generate-frontend-client  # regenerate the typed API client after a backend schema change
poe migrate                   # apply Alembic migrations
poe db-up / poe db-down       # start/stop the local Postgres container
```

## Quality checks

```sh
poe typecheck   # mypy --strict + svelte-check + tsc
poe lint        # ruff check + prettier + eslint
poe format      # ruff format + prettier (writes in place)
poe check       # full pre-commit hooks + coverage gate (re-syncs deps first — this is what CI runs)
poe check-changed # run pre-commit checks on changed files only
```

## Testing

### Running tests

```sh
poe test                      # all unit tests (backend + frontend)
poe test-backend              # backend unit + router tests — fast, no infrastructure needed
poe test-backend-integration  # backend integration tests — requires live Postgres
poe test-backend-all          # unit + integration with combined coverage data
poe test-frontend             # Vitest unit tests
poe coverage                  # full test suite + enforce all coverage thresholds
```

### Backend test structure

Tests mirror the source layout under `backend/tests/`:

```
tests/
├── modules/<context>/
│   ├── domain/         # pure unit tests — no infrastructure
│   ├── application/    # use-case tests — in-memory adapters only
│   └── adapters/
│       ├── api/        # router tests — FastAPI TestClient + in-memory adapters
│       └── persistence/# @pytest.mark.integration — require live Postgres
└── architecture/       # archunitpython dependency-rule tests — always run, no infrastructure
```

**Use in-memory adapters, not mocks.** Every port ships a first-class in-memory implementation in `adapters/persistence/` as a sibling to the real adapter. Use those in domain, application, and router tests. `unittest.mock` is not used for repository or service boundaries — in-memory adapters exercise the real port contract.

**Integration tests** are tagged `@pytest.mark.integration`. They are excluded from `poe test-backend` and connect to a real Postgres instance.

### Coverage floors

Enforced by Codecov on every PR and locally via `poe coverage`:

| Component | Threshold |
|---|---|
| domain | 100% |
| ports | tracked, no fixed floor |
| application | 100% |
| shared_kernel | 100% |
| adapters | 80% |
| platform | 70% |

`ports/` holds `Protocol` interfaces — the stub method bodies (`...`) never execute, so a hard 100% floor wouldn't test anything real. Codecov tracks it for visibility (`target: auto` in `codecov.yml`) without gating on it.

### Adding a new bounded context

A complete feature at one bounded context requires: domain entity/value object, use case(s), port Protocol(s), in-memory adapter, SQLAlchemy adapter, and tests at each layer (domain, application, router, persistence).

## Pull requests

- Target the `feature/initial-implementation` branch (pre-`main` merge) or `main` once it's open.
- `poe check` must pass.
- Coverage floors must not drop.
- One focused change per PR.

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [backend/README.md](backend/README.md), and [frontend/README.md](frontend/README.md).
