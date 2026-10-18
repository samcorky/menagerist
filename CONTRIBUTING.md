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

The `media-data` named volume is initialised with the application's uid `1000`
from the image. If you replace it with a bind mount, set ownership on the host
with `chown 1000:1000 <host directory>` so uploads can be written.

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

### First run and accounts

The first visit to the app (or any `/api/v1` call) answers "set up required" and the browser lands on `/setup`: choose a username and password and that account becomes the administrator. Any items, collections, files and example installations that already exist (from before accounts) are adopted by that first administrator in the same step; the page shows what was claimed. Accounts are local to the instance. Administrators add other people under Settings > Users, giving each an initial password that the person must change at first sign-in.

After pulling changes that touch the database, run `poe migrate` (the container does it on start with `--migrate`) before opening the app.

The `menagerist identity` commands manage accounts without the UI:

```sh
uv run menagerist identity create-admin --username sam   # first admin (claims existing data) or an extra admin
uv run menagerist identity reset-password --username sam # new initial password, ends the account's sessions
uv run menagerist identity list                          # table: username, display name, role, status, last sign-in
uv run menagerist identity list --json                   # the same as JSON, for scripts
uv run menagerist identity set-display-name --username sam --display-name "Sam C"
uv run menagerist identity unlock --username sam         # lift a sign-in lockout (does not enable a disabled account)
```

`create-admin` reads the password from the settings (below) or, if none is set, asks for it (hidden, confirmed twice). `reset-password` always asks, so a bootstrap password left in the environment or a secret file is never applied to someone's account by accident; pass `--from-settings` to read the configured password instead (for scripts). The password is never printed or logged. It must be 10 to 128 characters and not the username. The account must change it at next sign-in.

**Preferred: a secret file.** Put the password in a file named `menagerist_initial_password` in `/run/secrets` (Docker and Compose secrets mount there) and the CLI reads it. `MENAGERIST_INITIAL_PASSWORD` also works, but an environment variable shows up in `docker inspect` and in process listings, so use the file where you can. Only the `identity` CLI reads this setting (`create-admin`, and `reset-password --from-settings`); the server never does.

**Sign-in lockouts.** Password checks are counted before they are made, per username (5 in 15 minutes) and per client address (20 in 15 minutes), whether or not the account exists, so parallel guesses cannot exceed the limit; a correct password clears the username count and gives back the address's. The password-change check is counted the same way (per user and per address); `MENAGERIST_SIGN_IN_USERNAME_ATTEMPTS`, `MENAGERIST_SIGN_IN_IP_ATTEMPTS` and `MENAGERIST_SIGN_IN_WINDOW_MINUTES` change them. An administrator lifts a username lock with the Unlock button in Settings > Users, or `identity unlock`. The client address is the socket peer, unless that peer is listed in `MENAGERIST_TRUSTED_PROXIES` (comma-separated addresses, CIDR networks or `*`; default `127.0.0.1`), in which case its `X-Forwarded-For` is used. Behind a reverse proxy in another container, list the proxy's address or network; `*` trusts every peer and is only safe when the proxy is the sole way in and overwrites the header.

**Shared addresses.** Every client behind one proxy or NAT shares one address counter, so 20 failed checks from anyone behind it lock sign-in for everyone behind it until the window ends (an administrator's Unlock clears only the username counters). Set `MENAGERIST_TRUSTED_PROXIES` so each person's real address is used.

**Hashing limit.** Passwords are hashed with scrypt (about 32 MiB each). `MENAGERIST_PASSWORD_HASH_CONCURRENCY` (default `2`, minimum `1`) caps how many run at once in one server process; extra sign-ins wait, so a flood cannot exhaust memory. Raise it only if the container has the memory.

**Behind a TLS-terminating proxy.** Set `MENAGERIST_COOKIE_SECURE=true` so the session cookie always carries `Secure`, whatever scheme the app sees, and list the proxy in `MENAGERIST_TRUSTED_PROXIES`. Sign-in and first-run setup also refuse a browser request from another site. The browser's `Sec-Fetch-Site` decides first (page script cannot set it): `cross-site` is refused and `same-origin` passes, so a proxy that hides the scheme cannot lock people out. When the header is missing or says `same-site`, any `Origin` must be the request's own origin or one in `MENAGERIST_CORS_ORIGINS` (a `*` there does not count), so the proxy must pass `Host` and the original scheme through and be trusted. An unparseable `Origin` is refused. Refusals are logged with the claimed and seen origins (`cross-site request refused`). A same-origin request whose `Origin` differs from the one the app saw is let through but counted, as is a request with forwarding headers from an untrusted peer: the first of each in an hour is logged (`reverse proxy may be misconfigured`, with the setting to change) and the counts show as a warning for `proxy:configuration` at `GET /api/health/ready/detail` for an hour. The counts are kept in memory per worker, hold only times, and never fail readiness.

**Sessions.** A session lasts at most `MENAGERIST_SESSION_TTL_HOURS` (default `168`, seven days) however active it is. `MENAGERIST_SESSION_IDLE_HOURS` (default `0`, off) also ends a session that has not been used for that many hours: it is checked against the time the session was last seen, which is recorded at most once a minute, so any whole number of hours is accurate. A value of `0` disables it; negative values are refused. An idle session is treated exactly like an expired one (401, the session is removed), and the hard cap above still applies on top.

**Cross-origin access (CORS).** By default no other origin is allowed: the API serves the web UI itself, and the Vite dev server proxies `/api`, so the browser only ever talks to one origin. If you host the frontend separately, list its origin, for example `MENAGERIST_CORS_ORIGINS=https://app.example.com` (comma separated for several). `*` is still accepted when set explicitly, but it is not recommended: it lets any website call the unauthenticated endpoints. Credentials are never allowed cross-origin, and sign-in and first-run setup refuse a request from another site whatever this setting says (see above).

**HSTS.** The app deliberately does not send `Strict-Transport-Security`: it cannot know whether it is reached over HTTPS, and a wrong header is hard to undo. Set it at the TLS-terminating proxy. Caddy: `header Strict-Transport-Security "max-age=15552000"`. nginx: `add_header Strict-Transport-Security "max-age=15552000" always;`.

**Health, version and diagnostics.** `GET /api/health` (liveness), `GET /api/health/ready` (readiness) and `GET /api/version` are public and say as little as possible: liveness is `{"status": "pass"}`, readiness is `{"status": "pass"}` (200) or `{"status": "fail"}` (503), and the version is just the name and version number. Container and orchestrator health checks only look at the status code. The measurements and build details sit behind the `system:diagnostics:read` permission, which administrators hold: `GET /api/health/ready/detail` (each check with its observed value; a failing check says only `check failed`, a warning may include an operator hint, and unexpected errors are in the server log) and `GET /api/version/detail` (commit, branch, build time and migration head). Storage issues are warnings and do not make the instance unready.

**Forgotten administrator password:** run `reset-password` for that username against the same database (`DATABASE_URL`/`MENAGERIST_*` settings as the app), then sign in with the new password and change it. For the Docker stack, run it inside the container: `docker compose exec menagerist menagerist identity reset-password --username sam`.

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

### Running tests in parallel

`poe test-backend`, `poe test-backend-integration` (and so `poe test-backend-all` and `poe coverage`) run under pytest-xdist with `-n auto --maxprocesses=6 --dist loadscope`: one worker per CPU core, capped at six, with every test module kept on one worker. The flags live only in the `poe` tasks, so `pytest path::test` and IDE runs stay serial. Coverage is combined across workers automatically.

```sh
PYTEST_XDIST_AUTO_NUM_WORKERS=3 poe test-backend   # choose the worker count (still capped at 6)
poe test-backend-integration -n 0                  # serial: a later -n wins
cd backend && pytest -m 'not integration'          # plain serial run, no coverage-erase
```

Each integration worker starts its own Postgres container (`postgres:18-alpine`, roughly 100 MB of memory each), so the cap also caps containers. Lower the worker count on a small machine. Tests must not share state between modules: use `tmp_path` and the per-worker fixtures in `backend/tests/conftest.py`, never fixed paths, ports or database names.

### End-to-end tests

`poe test-e2e` runs the Playwright suite in `frontend/tests/e2e/` against an isolated, throwaway Postgres (via `compose.e2e.yaml`). It builds the production frontend (`poe e2e-build`, `npm run build`, roughly two minutes), runs the specs in parallel, and removes the database container afterwards whatever the outcome. It requires Docker. CI runs it as its own `e2e` job, retrying a failed test once and uploading the traces of failures. It covers the roadmap's core happy paths: creating an item, setting an item type, adding a connection, quick capture, and managing item types.

`poe sync` (and so `poe init`) downloads the Chromium build Playwright drives (`poe install-e2e-browser`). On Linux, Chromium also needs a few system libraries; if the suite fails with `error while loading shared libraries`, run `poe install-e2e-deps` for the one-off command that fixes it (it needs `sudo` and a real terminal, so it prints the command rather than running it).

```sh
poe test-e2e                      # one worker per CPU core
poe test-e2e --workers 2          # or -w 2; --workers 1 runs serially
poe test-e2e --skip-build         # reuse frontend/build - only when it is current
```

`test-e2e-headed` and `test-e2e-slow` take the same arguments.

Each worker has its own database (`menagerist_w0`, `menagerist_w1`, ... in the one Postgres container on port 55433) and its own backend on port **8100 + worker index**. Each backend serves the built SPA from `frontend/build`, so there is no Vite dev server. Files run in parallel across workers; tests inside a file stay ordered. The ports are deliberately not the dev defaults (8000/5173), so the suite can run alongside `poe serve` or a deployed `docker compose up` and can never reuse a server that points at your real data. Override the base port with `E2E_BACKEND_PORT`. Locally, servers already running on those ports are reused, which makes the single-spec workflow below fast.

**Authentication.** Every route except the auth routes needs a session, so `frontend/tests/e2e/fixtures.ts` signs each worker in once: it calls `GET /auth/status`, runs `POST /auth/setup` on a fresh worker database (the migrate script leaves it without users) or `POST /auth/login` if the stable admin `e2e-admin` already exists, and keeps the session in memory. The test-scoped `storageState` and `X-CSRF-Token` header come from that session, so `page`, `context` and `request` are all signed in and existing specs need no change. Worker databases keep the `e2e-admin` account between runs; if sign-in fails, run `poe e2e-db-down` (it drops the volume) and migrate again. `helpers.ts` has `createUserViaApi(admin, baseURL, ...)` and `asUser(browser, user)` for specs that need other accounts. `browser.newContext()` starts as the worker admin, so contexts for other people must pass an explicit `storageState` (`asUser` does).

A third Playwright project, `auth` (`auth.spec.ts`), tests first-run setup, sign-in and the password rules against its own backend on port **8190** (`E2E_AUTH_BACKEND_PORT`) and database `menagerist_auth`. `poe e2e-migrate` drops and recreates that database on every run so it is always empty; the file skips itself with a message if it finds users. Because Playwright starts this backend on every run, `menagerist_auth` must exist even when you run a single other spec: migrate after any `poe e2e-db-down`.

Every worker is a browser plus a backend, so memory and CPU use grow with `--workers`. If tests time out on a small machine, lower the count.

The backends start with `uv run --no-sync`, because several servers syncing at once fight over `.venv\Scripts\menagerist.exe` on Windows. `poe test-e2e` syncs once beforehand; when you run Playwright by hand, run `poe sync-backend` first (and again after backend dependency changes).

To iterate on a single spec without paying the full up/build/migrate/down cycle each time (the build must be current):

```sh
poe sync-backend && poe e2e-db-up && poe e2e-build
E2E_WORKERS=1 poe e2e-migrate      # once, leave running
cd frontend && E2E_WORKERS=1 npx playwright test tests/e2e/create-item.spec.ts
poe e2e-db-down                    # when done: removes the container and its volume
```

To rerun only the auth project: `E2E_WORKERS=1 poe e2e-migrate`, then `cd frontend && E2E_WORKERS=1 npx playwright test tests/e2e/auth.spec.ts --project=auth`.

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

## Using the interactive API docs

Swagger UI is at `/api/docs` on the backend (`http://localhost:8000/api/docs` in development). Sign in by running `POST /api/v1/auth/login` with "Try it out": the browser keeps the session cookies, and the banner at the top shows who is signed in. Swagger UI then adds the `X-CSRF-Token` header to POST, PUT, PATCH and DELETE calls itself, so mutating operations work. The Authorize button is hidden because browsers cannot set a `Cookie` header from JavaScript. ReDoc (`/api/redoc`) is read-only. The setup script is `backend/src/app/entrypoints/api/docs/static/swagger-init.js`; the Swagger UI and ReDoc assets load from cdn.jsdelivr.net at an exact version with Subresource Integrity (`integrity="sha384-..."`, `crossorigin="anonymous"`) set in `backend/src/app/entrypoints/api/docs/router.py`. To bump a version, download each file from its URL, recompute the hash (`openssl dgst -sha384 -binary FILE | openssl base64 -A`) and update the version and hash constants together (Swagger has three, ReDoc has two); `test_docs_external_assets_are_pinned_and_have_integrity` fails on an unpinned or unhashed tag on either page.

## Pull requests

- Target the `feature/initial-implementation` branch (pre-`main` merge) or `main` once it's open.
- `poe check` must pass.
- Coverage floors must not drop.
- One focused change per PR.

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [backend/README.md](backend/README.md), and [frontend/README.md](frontend/README.md).
