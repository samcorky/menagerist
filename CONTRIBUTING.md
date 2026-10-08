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

Skipping activation is fine too - just prefix each command with `uv run` instead, e.g. `uv run poe test`.

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
poe sync                      # re-sync all deps, the e2e browser and the API client (run after pulling)
poe generate-frontend-client  # regenerate the typed API client after a backend schema change
poe migrate                   # apply Alembic migrations
poe db-up / poe db-down       # start/stop the local Postgres container
```

## Quality checks

```sh
poe typecheck   # mypy --strict + svelte-check + tsc
poe lint        # ruff check + prettier + eslint
poe format      # ruff format + prettier (writes in place)
poe check       # full pre-commit hooks + coverage gate (re-syncs deps first - this is what CI runs)
poe check-changed # run pre-commit checks on changed files only
```

## Testing

### Running tests

```sh
poe test                      # all unit tests (backend + frontend)
poe test-backend              # backend unit + router tests - fast, no infrastructure needed
poe test-backend-integration  # backend integration tests - requires live Postgres
poe test-backend-all          # unit + integration with combined coverage data
poe test-frontend             # Vitest unit tests
poe test-e2e                  # Playwright end-to-end tests - requires Docker
poe coverage                  # full test suite + enforce all coverage thresholds
```

### End-to-end tests

`poe test-e2e` runs the Playwright suite in `frontend/tests/e2e/` against an isolated, throwaway Postgres (via `compose.e2e.yaml`). It builds the production frontend (`poe e2e-build`, `npm run build`, roughly two minutes), runs the specs in parallel, and removes the database container afterwards whatever the outcome. It requires Docker. It covers the roadmap's core happy paths: creating an item, setting an item type, adding a connection, quick capture, and managing item types.

`poe sync` (and so `poe init`) downloads the Chromium build Playwright drives (`poe install-e2e-browser`). On Linux, Chromium also needs a few system libraries; if the suite fails with `error while loading shared libraries`, run `poe install-e2e-deps` for the one-off command that fixes it (it needs `sudo` and a real terminal, so it prints the command rather than running it).

```sh
poe test-e2e                      # one worker per CPU core
poe test-e2e --workers 2          # or -w 2; --workers 1 runs serially
poe test-e2e --skip-build         # reuse frontend/build - only when it is current
```

`test-e2e-headed` and `test-e2e-slow` take the same arguments.

Each worker has its own database (`menagerist_w0`, `menagerist_w1`, ... in the one Postgres container on port 55433) and its own backend on port **8100 + worker index**. Each backend serves the built SPA from `frontend/build`, so there is no Vite dev server. Files run in parallel across workers; tests inside a file stay ordered. The ports are deliberately not the dev defaults (8000/5173), so the suite can run alongside `poe serve` or a deployed `docker compose up` and can never reuse a server that points at your real data. Override the base port with `E2E_BACKEND_PORT`. Locally, servers already running on those ports are reused, which makes the single-spec workflow below fast.

Every worker is a browser plus a backend, so memory and CPU use grow with `--workers`. If tests time out on a small machine, lower the count.

To iterate on a single spec without paying the full up/build/migrate/down cycle each time (the build must be current):

```sh
poe e2e-db-up && poe e2e-build
E2E_WORKERS=1 poe e2e-migrate      # once, leave running
cd frontend && E2E_WORKERS=1 npx playwright test tests/e2e/create-item.spec.ts
poe e2e-db-down                    # when done
```

### Backend test structure

Tests mirror the source layout under `backend/tests/`:

```
tests/
├── modules/<context>/
│   ├── domain/         # pure unit tests - no infrastructure
│   ├── application/    # use-case tests - in-memory adapters only
│   └── adapters/
│       ├── api/        # router tests - FastAPI TestClient + in-memory adapters
│       └── persistence/# @pytest.mark.integration - require live Postgres
└── architecture/       # archunitpython dependency-rule tests - always run, no infrastructure
```

**Use in-memory adapters, not mocks.** Every port ships a first-class in-memory implementation in `adapters/persistence/` as a sibling to the real adapter. Use those in domain, application, and router tests. `unittest.mock` is not used for repository or service boundaries - in-memory adapters exercise the real port contract.

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

`ports/` holds `Protocol` interfaces - the stub method bodies (`...`) never execute, so a hard 100% floor wouldn't test anything real. Codecov tracks it for visibility (`target: auto` in `codecov.yml`) without gating on it.

### Adding a new bounded context

A complete feature at one bounded context requires: domain entity/value object, use case(s), port Protocol(s), in-memory adapter, SQLAlchemy adapter, and tests at each layer (domain, application, router, persistence).

## Pull requests

- Target the `feature/initial-implementation` branch (pre-`main` merge) or `main` once it's open.
- `poe check` must pass.
- Coverage floors must not drop.
- One focused change per PR.

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [backend/README.md](backend/README.md), and [frontend/README.md](frontend/README.md).
