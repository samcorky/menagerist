# Contributing

[![GHCR pulls][pulls-badge]][pulls-link]
[![Download size][size-badge]][pulls-link]
[![CalVer][calver-badge]][calver-link]
[![Python][python-badge]][python-link]
[![mypy: strict][mypy-badge]][mypy-link]
[![Ruff][ruff-badge]][ruff-link]
[![uv][uv-badge]][uv-link]
[![Renovate][renovate-badge]][renovate-link]

## Setup

Requires [uv](https://docs.astral.sh/uv/) and the Node version in `.node-version`. uv installs the right Python for you; [fnm](https://github.com/Schniz/fnm) does the same for Node (see [Node version](#node-version)). If you don't have uv installed:

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

### Node version

`.node-version` is the one place the Node version is set. CI, the Docker image and the `engines` field in `frontend/package.json` all follow it, and `npm` in `frontend/` refuses to run on a different major version (`engine-strict`). [fnm](https://github.com/Schniz/fnm) installs and switches to that version for you:

```sh
winget install Schniz.fnm      # Windows (or: scoop install fnm); macOS/Linux: brew install fnm
curl -fsSL https://fnm.vercel.app/install | bash   # macOS/Linux, no package manager required
fnm install                    # installs the version in .node-version
```

Add its shell hook once so the version switches when you enter the repository. `--version-file-strategy recursive` makes it find the root `.node-version` from `frontend/` too:

```powershell
# $PROFILE (PowerShell)
fnm env --use-on-cd --version-file-strategy recursive --shell powershell | Out-String | Invoke-Expression
```

```sh
# ~/.bashrc or ~/.zshrc
eval "$(fnm env --use-on-cd --version-file-strategy recursive)"
```

Other managers that read `.node-version` (mise, asdf, nodenv) work too. nvm only reads `.nvmrc`, so it does not.

If `npm` in `frontend/` fails with `EBADENGINE` ("Not compatible with your version of node/npm"), the shell is still on another Node. That is `engine-strict` doing its job. Open a new terminal after adding the hook, then check `node --version` against `.node-version`. If it is still wrong, run `Get-Command node -All` (PowerShell) or `which -a node` to see which one comes first on `PATH`. The fnm line should come last in the profile, and an activated virtual environment must not put another Node ahead of it.

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

uv run menagerist migrate upgrade --no-backup
uv run menagerist serve --host 0.0.0.0 --reload   # backend at :8000
```

Migrations take a verified backup first once a schema has pending upgrades, which needs a writable `/data/backups`. `--no-backup` (or `MENAGERIST_BACKUP_BEFORE_MIGRATE=false`) skips it on a development machine; `poe migrate` does this by default.

```sh
cd frontend && npm run dev -- --host 0.0.0.0       # frontend at :5173, in a second shell
```

### Building the Docker image

To run your own changes instead of the published image, build it locally. The build produces the backend's OpenAPI schema and the frontend's typed client itself, so a fresh clone needs nothing pre-generated.

```sh
uv run poe init            # sync deps + install git hooks
uv run poe docker-build    # build the Menagerist image
uv run poe docker-up       # start Postgres + Menagerist, detached, at :8080
```

Without `poe`:

```sh
docker buildx bake -f docker-bake.hcl local
MENAGERIST_IMAGE=menagerist:local docker compose up -d --force-recreate
```

`compose.yaml` pulls the published image unless `MENAGERIST_IMAGE` says otherwise, so `poe docker-up` and the line above point it at the image you just built. On PowerShell, set the variable first: `$env:MENAGERIST_IMAGE = "menagerist:local"`.

`uv run` syncs and resolves the backend package on its own - no separate install step. If you've activated the project's venv instead (see [Setup](#setup)), drop the `uv run` prefix and call `menagerist` directly.

### First run and accounts

The first visit to the app (or any `/api/v1` call) answers "set up required" and the browser lands on `/setup`: choose a username and password and that account becomes the administrator. Any items, collections, files and example installations that already exist (from before accounts) are adopted by that first administrator in the same step; the page shows what was claimed. Accounts are local to the instance. Administrators add other people under Settings > Users, giving each an initial password that the person must change at first sign-in.

After pulling changes that touch the database, run `poe migrate` (the container does it on start with `--migrate`) before opening the app.

The `menagerist identity` commands manage accounts without the UI:

```sh
uv run menagerist identity create-admin --username sam   # first admin (claims existing data) or an extra admin
uv run menagerist identity reset-password --username sam # new initial password, ends the account's sessions
uv run menagerist identity list                          # table: username, display name, role, status, last sign-in
uv run menagerist --json identity list                   # the same as JSON, for scripts
uv run menagerist identity set-display-name --username sam --display-name "Sam C"
uv run menagerist identity unlock --username sam         # lift a sign-in lockout (does not enable a disabled account)
```

Every command except `serve` and `worker` shows a result on stdout: Rich tables on a terminal, plain lines when piped or redirected, and JSON only when asked with `--json` (or `--format rich|text|json`), given before the command. Logs and errors go to stderr, and `-q` shows only errors. On a terminal, long steps show a spinner, `backup download` and `backup upload` show a progress bar, and destructive commands (`backup delete`, `backup restore --replace`, `data purge-deleted`, `migrate downgrade`) ask first; `--yes` skips the question. None of that appears when output is piped, so scripts and cron are never prompted.

`create-admin` reads the password from the settings (below) or, if none is set, asks for it (hidden, confirmed twice). `reset-password` always asks, so a bootstrap password left in the environment or a secret file is never applied to someone's account by accident; pass `--from-settings` to read the configured password instead (for scripts). The password is never printed or logged. It must be 10 to 128 characters and not the username. The account must change it at next sign-in.

**Preferred: a secret file.** Put the password in a file named `menagerist_identity_initial_password` in `/run/secrets` (Docker and Compose secrets mount there) and the CLI reads it. `MENAGERIST_IDENTITY_INITIAL_PASSWORD` also works, but an environment variable shows up in `docker inspect` and in process listings, so use the file where you can. Only the `identity` CLI reads this setting (`create-admin`, and `reset-password --from-settings`); the server never does.

**Sign-in lockouts.** Password checks are counted before they are made, per username (5 in 15 minutes) and per client address (20 in 15 minutes), whether or not the account exists, so parallel guesses cannot exceed the limit; a correct password clears the username count and gives back the address's. The password-change check is counted the same way (per user and per address); `MENAGERIST_IDENTITY_SIGN_IN_USERNAME_ATTEMPTS`, `MENAGERIST_IDENTITY_SIGN_IN_IP_ATTEMPTS` and `MENAGERIST_IDENTITY_SIGN_IN_WINDOW_MINUTES` change them. An administrator lifts a username lock with the Unlock button in Settings > Users, or `identity unlock`. The client address is the socket peer, unless that peer is listed in `MENAGERIST_API_TRUSTED_PROXIES` (comma-separated addresses, CIDR networks or `*`; default `127.0.0.1`), in which case its `X-Forwarded-For` is used. Behind a reverse proxy in another container, list the proxy's address or network; `*` trusts every peer and is only safe when the proxy is the sole way in and overwrites the header.

**API-token failures.** A bearer value that is malformed, unknown or has the wrong secret is counted against the client address (20 in the same window, `MENAGERIST_IDENTITY_API_TOKEN_IP_ATTEMPTS`; the window is `MENAGERIST_IDENTITY_SIGN_IN_WINDOW_MINUTES`). Past the limit every bearer request from that address, even with a valid token, is refused with a 429 and `Retry-After` until the window ends. The counter is separate from the sign-in one, so a script with a stale token cannot lock people out of signing in. Expired tokens and disabled owners are not counted, and a request with no client address is not limited.

**Request limits on expensive routes.** Uploads (media and backup archives), thumbnails, item searches and imports (presets and user data) are limited per signed-in user per minute: `MENAGERIST_RATE_LIMIT_UPLOADS_PER_MINUTE` (30), `MENAGERIST_RATE_LIMIT_THUMBNAILS_PER_MINUTE` (600), `MENAGERIST_RATE_LIMIT_SEARCH_PER_MINUTE` (120) and `MENAGERIST_RATE_LIMIT_IMPORTS_PER_MINUTE` (10); `0` turns a limit off. Past a limit the route answers 429 with `Retry-After` (seconds until the minute's window ends), in the usual problem+json form; refused requests are not counted, so waiting that long always works. These protect the server's resources, not accounts, so the counts are approximate: they are kept in memory in each server process, and with several workers the effective limit is the setting times the number of workers. Counts are checked after sign-in, so an unauthenticated request is a 401 and never uses anyone's allowance. A route joins a group with `dependencies=[Depends(rate_limited(RateLimitBucket.UPLOADS))]` (`entrypoints/api/shared/http/rate_limit.py`) and documents the 429 with `RATE_LIMITED_RESPONSE`; a new group is a member of `RateLimitBucket` plus a setting and a case in `limit_for`. Coarse per-address limits belong at the reverse proxy ([REVERSE-PROXY.md](docs/REVERSE-PROXY.md#rate-limit-at-the-proxy)).

**Shared addresses.** Every client behind one proxy or NAT shares one address counter, so 20 failed checks from anyone behind it lock sign-in for everyone behind it until the window ends (an administrator's Unlock clears only the username counters). Set `MENAGERIST_API_TRUSTED_PROXIES` so each person's real address is used.

**Hashing limit.** Passwords are hashed with scrypt (about 32 MiB each). `MENAGERIST_IDENTITY_PASSWORD_HASH_CONCURRENCY` (default `2`, minimum `1`) caps how many run at once in one server process; extra sign-ins wait, so a flood cannot exhaust memory. Raise it only if the container has the memory.

**Behind a TLS-terminating proxy.** Set `MENAGERIST_API_PUBLIC_ORIGIN` to the public address and `MENAGERIST_IDENTITY_COOKIE_SECURE=origin` (or `always`) so the session cookie always carries `Secure`, whatever scheme the app sees (a `Secure` cookie is named `__Host-Http-menagerist-session`; over plain HTTP it stays `menagerist-session`, so switching between the two means signing in again), and list the proxy in `MENAGERIST_API_TRUSTED_PROXIES`. Sign-in and first-run setup also refuse a browser request from another site. The browser's `Sec-Fetch-Site` decides first (page script cannot set it): `cross-site` is refused and `same-origin` passes, so a proxy that hides the scheme cannot lock people out. When the header is missing or says `same-site`, any `Origin` must be the request's own origin or one in `MENAGERIST_API_CORS_ORIGINS` (a `*` there does not count), so the proxy must pass `Host` and the original scheme through and be trusted. An unparseable `Origin` is refused. Refusals are logged with the claimed and seen origins (`cross-site request refused`). A same-origin request whose `Origin` differs from the one the app saw is let through but counted, as is a request with forwarding headers from an untrusted peer: the first of each in an hour is logged (`reverse proxy may be misconfigured`, with the setting to change) and the counts show as a warning for `proxy:configuration` at `GET /api/v1/system/health/ready/detail` for an hour. The counts are kept in memory per worker, hold only times, and never fail readiness.

**Sessions.** A session lasts at most `MENAGERIST_IDENTITY_SESSION_TTL_HOURS` (default `168`, seven days) however active it is. `MENAGERIST_IDENTITY_SESSION_IDLE_HOURS` (default `0`, off) also ends a session that has not been used for that many hours: it is checked against the time the session was last seen, which is recorded at most once a minute, so any whole number of hours is accurate. A value of `0` disables it; negative values are refused. An idle session is treated exactly like an expired one (401, the session is removed), and the hard cap above still applies on top.

**Cross-origin access (CORS).** By default no other origin is allowed: the API serves the web UI itself, and the Vite dev server proxies `/api`, so the browser only ever talks to one origin. If you host the frontend separately, list its origin, for example `MENAGERIST_API_CORS_ORIGINS=https://app.example.com` (comma separated for several). `*` is still accepted when set explicitly, but it is not recommended: it lets any website call the unauthenticated endpoints, so it logs a warning at start-up and shows as a warning for `cors:configuration` at `GET /api/v1/system/health/ready/detail` (it never fails readiness). A listed origin may use GET, POST, PUT, PATCH and DELETE with the `Content-Type`, `If-Match`, `If-None-Match`, `If-Modified-Since` and `Request-Id` request headers, and can read `ETag`, `Retry-After`, `Link`, `Total-Count`, `Request-Id` and `App-Version`; a preflight asking for anything else is refused (the lists are in `entrypoints/api/shared/http/cors.py`, and a test fails if a route or schema header falls outside them). Credentials are never allowed cross-origin, and sign-in and first-run setup refuse a request from another site whatever this setting says (see above).

**HSTS.** The app deliberately does not send `Strict-Transport-Security`: it cannot know whether it is reached over HTTPS, and a wrong header is hard to undo. Set it at the TLS-terminating proxy. Caddy: `header Strict-Transport-Security "max-age=15552000"`. nginx: `add_header Strict-Transport-Security "max-age=15552000" always;`.

**Health, version and diagnostics.** `GET /api/health` (liveness), `GET /api/health/ready` (readiness) and `GET /api/v1/system/version` are public and say as little as possible: liveness is `{"status": "pass"}`, readiness is `{"status": "pass"}` (200) or `{"status": "fail"}` (503), and the version is just the name and version number. Container and orchestrator health checks only look at the status code. The measurements and build details sit behind the `system:diagnostics:read` permission, which administrators hold: `GET /api/v1/system/health/ready/detail` (each check with its observed value; a failing check says only `check failed`, a warning may include an operator hint, and unexpected errors are in the server log) and `GET /api/v1/system/version/detail` (commit, branch, build time, migration head and, from the last stored update check, whether a newer release exists; `POST /api/v1/system/version/check` runs a check, needs `system:release:check`, and a daily job does the same). Storage issues are warnings and do not make the instance unready.

**Forgotten administrator password:** run `reset-password` for that username against the same database (`DATABASE_URL`/`MENAGERIST_*` settings as the app), then sign in with the new password and change it. For the Docker stack, run it inside the container: `docker compose exec menagerist menagerist identity reset-password --username sam`.

### Housekeeping commands

Run these from cron (or another scheduler) against the same database and media volume as the app; each is safe to repeat.

```sh
uv run menagerist media cleanup                              # delete staged and orphaned media past their TTL
uv run menagerist data purge-deleted                         # permanently delete content that was deleted over 30 days ago
uv run menagerist data purge-deleted --older-than-days 60    # use another retention for this run (at least 1)
uv run menagerist data purge-deleted --dry-run               # show what would be deleted and change nothing
```

`data purge-deleted` covers every person's items, connections and collections that have been in Recently deleted longer than `MENAGERIST_RETENTION_DELETED_DAYS` (default 30, minimum 1), with the memberships, attachments and stored files only they used. Live content is never touched. It also removes the item types, relationship types and presets that an uninstalled example pack left behind, once they are past the same cutoff, but never one that an item, connection or live type still uses. It prints the cutoff (UTC) and the counts per kind.

## Common tasks

```sh
poe sync                      # re-sync all deps, the e2e browser and the API client (run after pulling)
poe generate-frontend-client  # regenerate the typed API client after a backend schema change
poe migrate                   # apply Alembic migrations
poe db-up / poe db-down       # start/stop the local Postgres container
poe generate-settings-docs    # regenerate .env.example and docs/settings.md after changing a settings class
poe dump-schema               # regenerate openapi.json after changing the API
```

[`.env.example`](.env.example) and [`docs/settings.md`](docs/settings.md) are generated from the settings classes in `backend/src/app/platform/config`, so change a variable's default or description there, not in those files. `poe check-settings-docs` (run by CI as "Generated files (settings reference is current)" and by pre-commit when those paths change) fails when they are stale. Secret and credential defaults are never written out.

### The API schema

[`openapi.json`](openapi.json) is the committed OpenAPI schema: the contract that API clients, API-token scripts and the generated frontend client depend on. It is generated from the backend, so change the API there and run `poe dump-schema` (`poe generate-frontend-client` does this too), then commit the result with the change. `info.version` is pinned to `0.0.0` and `info.license.url` (a link that names the build's commit) is left out of the file, because both change with every commit; the running API still reports them, and `menagerist schema dump --with-version --output <path>` writes a copy that keeps it (the `Publish` workflow attaches one to each release; it cannot be used with `--check`). Do not edit the committed file by hand.

Two checks protect it:

- **Generated files (API schema is current)** runs `poe check-schema` in CI, and in pre-commit when backend source or the schema changes. It fails when the committed file differs from what the code produces.
- **Generated files (API schema is valid)** runs `poe validate-schema` in CI only (it takes about 20 seconds, too slow for pre-commit) and checks the file against the OpenAPI 3.1 specification with [openapi-spec-validator](https://github.com/python-openapi/openapi-spec-validator). Run it by hand after a large API change if you want the answer sooner.
- **Check for breaking API changes** (`.github/workflows/api-breaking-changes.yml`) compares the schema with the base branch using [oasdiff](https://github.com/oasdiff/oasdiff) and its default rules: for example a removed endpoint or field, a tightened type, or a new required request field. A breaking change fails the check unless the pull request carries the `breaking-change` label (see [Labels and release notes](#labels-and-release-notes)); adding or removing the label re-runs the check. Every schema change, breaking or not, is listed in the run summary. Changes that only add things, such as a new response field, never fail the check, but a strict client could still reject them, so read the summary.

## Quality checks

```sh
poe typecheck   # mypy --strict + svelte-check + tsc
poe lint        # ruff check + prettier + eslint
poe format      # ruff format + prettier (writes in place)
poe check       # every pre-commit hook, including the fast backend tests (re-syncs deps first)
poe check-changed # run pre-commit checks on changed files only
```

`poe check` runs the pre-commit hooks, which include the fast backend tests (`poe test-backend-fast`), but no coverage. The coverage gate is `poe coverage`, which runs the full suite. A plain `pytest` run does not write coverage data, so targeted runs never affect that gate.

## Testing

### Running tests

```sh
poe test                      # all unit tests (backend + frontend)
poe test-backend              # backend unit + router tests - fast, no infrastructure needed
poe test-backend-integration  # backend integration tests - requires live Postgres
poe test-backend-all          # unit + integration with combined coverage data
poe test-backend-fast         # only the quick in-memory areas (about 20 s): what pre-commit runs
poe test-frontend             # Vitest unit tests
poe coverage-frontend         # Vitest unit tests with coverage, failing below the frontend target
poe test-e2e                  # Playwright end-to-end tests - requires Docker
poe proxy-test                # nginx, Caddy and Traefik relay early 413/401 replies - requires Docker
poe coverage                  # full test suite + enforce all coverage thresholds
```

`poe proxy-test` builds the image, then runs `compose.proxy.yaml`: the real upload guard on Granian (no database) behind each proxy in turn, with a body sent after the app has already replied. It fails if any reply is a 502 instead of the 413 or 401. It sends a few hundred megabytes through each proxy; run `uv run --script scripts/proxy_test.py caddy --attempts 5` to test one proxy more quickly. Use it when changing the upload guard, Granian or a proxy example.

### Running tests in parallel

`poe test-backend`, `poe test-backend-integration` (and so `poe test-backend-all` and `poe coverage`) run under pytest-xdist with `-n auto --dist loadscope`: one worker per CPU core, with no worker cap by default and every test module kept on one worker. Pass `--maxprocesses=N` to a Poe test task to cap the workers; the flags live only in the `poe` tasks, so `pytest path::test` and IDE runs stay serial. Coverage is combined across workers automatically.

```sh
poe test-backend --workers 4                       # or -w 4: choose the worker count (auto by default, 0 = serial)
poe coverage -w 4                                  # also test-backend-all, test-and-status and test
PYTEST_XDIST_AUTO_NUM_WORKERS=3 poe test-backend   # what auto resolves to when --workers is not given
poe test-backend --maxprocesses=6                  # cap auto workers at six
poe test-backend-integration -n 0                  # serial: a later -n wins
cd backend && pytest -m 'not integration'          # plain serial run, no coverage-erase
```

Backend tests carry markers: `fast` (domain, application, shared kernel, architecture and platform tests, added by folder in `backend/tests/conftest.py`, so a new test there is included automatically; `poe test-backend-fast` and the pre-commit hook run `pytest -m fast`), `integration` (a real adapter) and `docker` (starts a Postgres container through testcontainers; it follows `integration` and any test using the `postgres_container` fixture). On this repo the fast set is about 3,000 tests in 20 seconds on four workers; more workers than that slow it down because each pays its own start-up.

Each integration worker starts its own Postgres container (`postgres:18-alpine`, roughly 100 MB of memory each), and there is no cap, so a many-core machine starts many containers: pass `-w 4` (or lower) there and on a small machine. `poe test-frontend` takes the same `--workers N` (`-w`), passed to vitest as `--maxWorkers`; without it vitest chooses. Frontend test files that use `vi.mock`, `vi.stubGlobal`, fake timers and the like run in isolated workers; the rest share modules per worker (`isolate: false`, see `frontend/vitest.config.ts`), so a test that changes module-level state must put it back. Tests must not share state between modules: use `tmp_path` and the per-worker fixtures in `backend/tests/conftest.py`, never fixed paths, ports or database names.

### End-to-end tests

`poe test-e2e` runs the Playwright suite in `frontend/tests/e2e/` against an isolated, throwaway Postgres (via `compose.e2e.yaml`). It builds the production frontend (`poe e2e-build`, `npm run build`, roughly two minutes), runs the specs in parallel, and removes the database container afterwards whatever the outcome. It requires Docker. CI runs it as its own `e2e` job, retrying a failed test once and uploading the traces of failures. It covers the roadmap's core happy paths: creating an item, setting an item type, adding a connection, quick capture, and managing item types.

`poe sync` (and so `poe init`) downloads the Chromium build Playwright drives (`poe install-e2e-browser`). On Linux, Chromium also needs a few system libraries; if the suite fails with `error while loading shared libraries`, run `poe install-e2e-deps` for the one-off command that fixes it (it needs `sudo` and a real terminal, so it prints the command rather than running it).

```sh
poe test-e2e                      # one worker per two CPU cores (each runs a backend, a scheduler worker and a browser)
poe test-e2e --workers 2          # or -w 2; --workers 1 runs serially
poe test-e2e --skip-build         # reuse frontend/build - only when it is current
poe test-e2e status.spec.ts       # only these spec files (several allowed; `file.ts:78` runs one test)
poe test-e2e --shard 2/3          # one third of the suite, split by spec file (CI runs three of these as parallel jobs)
```

`test-e2e-headed` and `test-e2e-slow` take the same arguments.

**Session cookie in WebKit and Firefox.** `poe test-e2e-cookies` runs only `cookies.spec.ts` in Chromium, WebKit (the Safari engine) and Firefox, against its own backend (port 8191, database `menagerist_cookies`) fronted by a small TLS proxy (`frontend/tests/e2e/tls-proxy.mjs`, port 8192, a self-signed certificate made at start-up with `openssl`). Through the proxy the app sees HTTPS and the cookie is `__Host-Http-menagerist-session`; on port 8191 directly it stays `menagerist-session`. It checks the cookie's attributes, that look-alike names are not a session, the prefix rule, a cross-site link and a forged cross-site post. The default `poe test-e2e` skips it, so ordinary runs need no extra browsers. Install them once with `poe install-e2e-cookie-browsers`; on Linux WebKit and Firefox need more system libraries, so run `poe install-e2e-cookie-deps` for the one-off command that installs them (it needs `sudo` and a real terminal, so it prints the command rather than running it). CI runs it after the main suite. Playwright's WebKit is an engine build, not Safari: check once by hand in Safari on macOS and iOS before a release.

Each worker has its own database (`menagerist_w0`, `menagerist_w1`, ... in the one Postgres container on port 55433) and its own backend on port **8100 + worker index**. Each backend serves the built SPA from `frontend/build`, so there is no Vite dev server. Files run in parallel across workers; tests inside a file stay ordered. The ports are deliberately not the dev defaults (8000/5173), so the suite can run alongside `poe serve` or a deployed `docker compose up` and can never reuse a server that points at your real data. Override the base port with `E2E_BACKEND_PORT`. Locally, servers already running on those ports are reused, which makes the single-spec workflow below fast.

**Authentication.** Every route except the auth routes needs a session, so `frontend/tests/e2e/fixtures.ts` signs each worker in once: it calls `GET /auth/status`, runs `POST /auth/setup` on a fresh worker database (the migrate script leaves it without users) or `POST /auth/login` if the stable admin `e2e-admin` already exists, and keeps the session in memory. The test-scoped `storageState` comes from that session, and the `request` fixture also sends the app's own `Origin` (the server refuses cookie-authenticated unsafe requests without it), so `page`, `context` and `request` are all signed in and existing specs need no change. Use `apiSessionOptions` (not `sessionOptions`) for extra API contexts; never set `Origin` on a browser context. Worker databases keep the `e2e-admin` account between runs; if sign-in fails, run `poe e2e-db-down` (it drops the volume) and migrate again. `helpers.ts` has `createUserViaApi(admin, baseURL, ...)` and `asUser(browser, user)` for specs that need other accounts. `browser.newContext()` starts as the worker admin, so contexts for other people must pass an explicit `storageState` (`asUser` does).

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
| frontend (`src/**/*.ts`) | 90% of lines |

`ports/` holds `Protocol` interfaces - the stub method bodies (`...`) never execute, so a hard 100% floor wouldn't test anything real. Codecov tracks it for visibility (`target: auto` in `codecov.yml`) without gating on it.

Every floor, frontend included, is a component `target` in `codecov.yml`, which is the single source of truth. `poe coverage-frontend` enforces the frontend one from the lcov report. It measures plain TypeScript only, since the Vitest environment renders no components; Playwright covers the rest.

Codecov's free plan posts only a short patch comment and no project or component statuses, so it cannot enforce the targets. Instead the `coverage-comment` CI job posts one comment on each pull request with the backend and frontend component tables. Patch coverage in Codecov is informational, and `poe coverage` and `poe coverage-frontend` are the gates. `codecov.yml` is validated by a pre-commit hook (`poe check-codecov`).

CI also uploads JUnit reports to Codecov Test Analytics, so failing, slow and flaky tests show on pull requests. Setting `JUNIT_XML_DIR` (a path relative to the repository root) makes `poe` write `backend-unit.xml`, `backend-integration.xml` and `frontend.xml` there; it is unset locally, so local runs write no reports. Playwright is not uploaded yet.

### Adding a new bounded context

A complete feature at one bounded context requires: domain entity/value object, use case(s), port Protocol(s), in-memory adapter, SQLAlchemy adapter, and tests at each layer (domain, application, router, persistence).

## Using the interactive API docs

Swagger UI is at `/api/docs` on the backend (`http://localhost:8000/api/docs` in development). Sign in by running `POST /api/v1/auth/login` with "Try it out": the browser keeps the session cookies, and the banner at the top shows who is signed in. The browser sends `Sec-Fetch-Site` and `Origin` itself on same-origin requests from the page, so mutating operations work; the generated curl snippets carry an `Origin` header (add `-b` with your session cookie when pasting one). The Authorize dialog takes a personal access token (the bearer scheme) only; its cookie scheme is hidden because browsers cannot set a `Cookie` header from JavaScript. ReDoc (`/api/redoc`) is read-only. The setup script is `backend/src/app/entrypoints/api/docs/static/swagger-init.js`; the Swagger UI and ReDoc assets load from cdn.jsdelivr.net at an exact version with Subresource Integrity (`integrity="sha384-..."`, `crossorigin="anonymous"`) set in `backend/src/app/entrypoints/api/docs/router.py`. To bump a version, download each file from its URL, recompute the hash (`openssl dgst -sha384 -binary FILE | openssl base64 -A`) and update the version and hash constants together (Swagger has three, ReDoc has two); `test_docs_external_assets_are_pinned_and_have_integrity` fails on an unpinned or unhashed tag on either page.

## Pull requests

- Target the `feature/initial-implementation` branch (pre-`main` merge) or `main` once it's open.
- `poe check` must pass, and `poe coverage` for backend changes.
- Coverage floors must not drop.
- One focused change per PR.
- The `Build` workflow builds the image and runs the smoke test; `CI` calls it, so it runs on every pull request.
- The `image-size-comment` CI job comments the compressed and uncompressed image size against the published `edge` image (the latest `main` build) on a pull request, editing one comment on later pushes. If `edge` cannot be pulled the comment shows the new size alone. The raw measurements are in the job log and summary. Fork pull requests get the job summary instead.
- On a pull request, the autofix.ci app may push a `style: apply hook fixes` commit (formatting and lint fixes), so pull before pushing again. It never edits files under `.github/workflows`.
- Require two checks in branch protection: `CI passed`, which succeeds only when the type check, frontend test, backend, end-to-end and image build jobs all do, and `Hooks: prek (autofix)`, which runs every other pre-commit hook (formatting, lint, secrets, config validation). They are separate workflows, so `CI passed` cannot cover the hooks.

## Releases

Versions are CalVer, `0.YYYY.M.PATCH` while pre-stable (for example `0.2026.11.0`; the month has no leading zero), and come from the git tag through hatch-vcs and `calver-scm`. The patch number counts releases within the month and restarts at `0` in a new month. `0.` means the data model and API are not yet stable; `[tool.calver-scm] stable = false` in `backend/pyproject.toml` adds it, and removing that line drops it when they are.

Tags are the version with a `v` in front: `v0.2026.11.0`. `calver-scm` rejects a tag without the `v` or without the `0.`, so `v2026.11.0` is not valid while `stable = false`.

A release candidate is the same version with `rc` and a number: `v0.2026.11.0rc1`, then `rc2` and so on, and finally `v0.2026.11.0` on the commit that passed. Write it exactly like that; the `-rc.1` spelling passes `calver-scm validate`, but it builds as `0.2026.11.0rc1`, so `Publish` would fail its tag-and-version check. A release candidate does not use up the patch number, so `poe release-tag` keeps proposing the final tag (`v0.2026.11.0`) until that is tagged; the `Release` workflow plans the candidate for you, and by hand `calver-scm next-tag --pre rc` (run in `backend/`) prints it. Builds from commits between a release candidate and its final tag report `0.2026.11.1.dev<N>`, which compares higher than the final `0.2026.11.0`; ignore that, it is only the dev build label.

| Trigger | Image tags on GHCR |
|---|---|
| A published GitHub release | the version and `sha-<commit>`, plus `latest` unless the release is marked a pre-release |
| A push to `main` | `edge` and `sha-<commit>` |
| `Publish` run by hand with "push" ticked | `sha-<commit>`, plus `edge` from `main` |
| A pull request, or `Publish` run by hand with "push" unticked | nothing is pushed |

To release from GitHub, run the `Release` workflow (Actions, Release, Run workflow) on `main`. Choose the tag to plan: `final` is the next release; `a`, `b` and `rc` the next alpha, beta or release candidate (`v0.2026.11.1a1`, `b1`, `rc1`, each counted separately); `promote` the final tag for the latest pre-release (it fails if there is none, or it is not an ancestor of `main`); and `post` a post-release of the latest release in the month (`v0.2026.11.0.post1`, which fails if the month has no release). It runs `calver-scm doctor`, plans the tag, checks it with `calver-scm validate --against-repo` (not already used, not skipping a patch, not lower than an existing release) and refuses to continue if a release, even a draft, already exists for it. Then it creates the release with notes grouped by label (`.github/release.yml`), covering everything since the last final release, and marks a pre-release (`a`, `b` or `rc`) as such so it stays off `latest`; a post-release is an ordinary release. Leave "draft" ticked (the default) to review the release and publish it yourself from the Releases page; publishing is what starts `Publish`. A release the workflow publishes itself does not start `Publish`, because releases made with the default `GITHUB_TOKEN` do not trigger other workflows, so unticking "draft" needs a `RELEASE_TOKEN` secret (a fine-grained token or app token with `contents: write`) and the workflow fails early without one. To release a tag you have chosen, for example a second candidate `v0.2026.11.1rc2` or a backport, type it in "tag" and leave the channel on `final`; the workflow refuses a channel and a tag together. A typed tag gets the same checks as a planned one (it must pass `calver-scm validate --against-repo`) and is marked as a pre-release when `validate` says it is one. Give the release a name in "name" (for example `Safe Harbour`) and its title becomes `v0.2026.11.1 - Safe Harbour`; leave it empty and the title is the tag alone. Only the title changes: the tag, the version and the image tags are the same, and the name is trimmed and kept to one line. Tick "dry run" to see the plan, the release title and the generated notes in the run summary and log, and create nothing.

Or by hand: on `main`, run `git fetch --tags`, then `poe release-tag` to print the next tag (it creates nothing; `git tag "$(poe release-tag)"` does) and publish a GitHub release for that tag. Mark it a pre-release only for a release candidate; `0.` releases are ordinary releases and do move `latest`. Use the "Generate release notes" button, or from the terminal `gh release create "$(poe release-tag)" --generate-notes` once the tag is pushed (add `--prerelease` for a release candidate, with its tag typed in place of `poe release-tag`). `poe version` shows the version the current checkout would build, `poe version-explain` shows how it was derived, and `poe version-doctor` checks the CalVer setup; all four wrap the `calver-scm` CLI. Until the first tag exists, `version-doctor` warns that no compatible tag was found. The `Publish` workflow runs the same doctor check, validates the tag against the CalVer configuration, fails if the tag and the version built from it disagree, smoke tests the image, builds `linux/amd64` and `linux/arm64` on native runners, tags the combined image and signs its build provenance (an attestation stored beside the image in GHCR). A published release also gets the API schema attached as `openapi.json`, with the version that release was built as. Run `Publish` by hand with "push" unticked to try the builds without pushing anything; the run summary lists the tags it would have used.

## Labels and release notes

Generated release notes group pull requests by label (`.github/release.yml`), so give pull requests a conventional-commit title such as `feat: ...`, `fix(auth): ...` or `docs: ...`; add `!` after the type (`feat!:`) for a breaking change. The `PR labeller` workflow then adds labels from the title prefix and from the files changed (`.github/labeller.yml`), and Renovate adds `dependencies`. Labels are only ever added, so correct a wrong one by hand. The `Labels: at least one` check fails a pull request that has no label for the kind of change (`area: ...` labels do not count); add one by hand and it reruns.

| Label | Meaning | Release notes section |
|---|---|---|
| `breaking-change` | Changes behaviour or an interface people rely on | Breaking changes |
| `upgrade-note` | Needs a note for people upgrading; add by hand | Upgrade notes |
| `performance` | `perf:` | Performance |
| `enhancement` | `feat:` | Enhancements |
| `bug` | `fix:` | Bug fixes |
| `security` | `security:` or a `(security)` scope | Security |
| `dependencies` | Dependency updates | Dependencies |
| `maintenance`, `tests`, `CI/CD`, `documentation` | `chore:`, `refactor:`, `build:`, `test:`, `ci:`, `docs:` and matching files | Housekeeping |
| `area: backend`, `area: frontend` | Files under `backend/` or `frontend/` changed (area only; added automatically) | none |
| `skip-release-notes` | Leave the pull request out; add by hand | none |

A pull request appears under the first section it matches, in the order above; one with no label lands under "Other changes". Renovate follows the same titles: `chore(deps):` for dependencies, `ci(deps):` for GitHub Actions, `build(deps):` for Docker images and the build system, and `fix(security):` for vulnerability updates, so its pull requests are labelled like any other.

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [backend/README.md](backend/README.md), and [frontend/README.md](frontend/README.md).

[pulls-badge]: https://img.shields.io/badge/dynamic/json?url=https://ghcr-badge.elias.eu.org/api/samcorky/menagerist/menagerist&query=downloadCount&label=pulls&logo=docker&logoColor=white&color=2496ED
[size-badge]: https://ghcr-badge.egpl.dev/samcorky/menagerist/size?tag=latest&label=download%20size%20(amd64)
[calver-badge]: https://img.shields.io/badge/calver-0.YYYY.MM.PATCH-22bfda
[python-badge]: https://img.shields.io/badge/dynamic/regex?url=https://raw.githubusercontent.com/samcorky/menagerist/main/.python-version&search=(.%2B)&replace=%241&label=python&logo=python&logoColor=white&color=blue
[mypy-badge]: https://img.shields.io/badge/mypy-strict-blue?logo=python&logoColor=white
[ruff-badge]: https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json
[uv-badge]: https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json
[renovate-badge]: https://img.shields.io/badge/renovate-enabled-brightgreen?logo=renovatebot&logoColor=white

[pulls-link]: https://github.com/samcorky/menagerist/pkgs/container/menagerist
[calver-link]: https://calver.org
[python-link]: https://www.python.org/
[mypy-link]: https://mypy-lang.org/
[ruff-link]: https://github.com/astral-sh/ruff
[uv-link]: https://github.com/astral-sh/uv
[renovate-link]: https://renovatebot.com
