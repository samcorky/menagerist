<p align="center">
  <img src="frontend/static/favicon.svg" width="64" height="64" alt="Menagerist logo">
</p>

# Menagerist

*(meh-NAH-juh-rist)*

A lightweight, self-hostable platform for organising the things you care about.

> [!IMPORTANT]
> **Early alpha:** The API, data model, and features are still evolving. Expect breaking changes.

---

## What is it?

Menagerist is a flexible collection manager built on a graph model. Records can represent anything - items, people, events, places - and can be connected to each other in whatever way makes sense for your collection.

The graph model is deliberately hidden from the user. You interact with familiar concepts like items and relationships; Menagerist handles the structure underneath.

---

## Current state

The core is working end-to-end:

- **Nodes** - create, view, edit, soft-delete records of any type
- **Node types** - define types with labels, descriptions, and custom attribute schemas
- **Relationships** - connect records with typed, directional or symmetric edges
- **Relationship types** - named edge types with forward/reverse labels and attribute schemas
- **Attributes** - freeform and schema-driven key/value metadata on any record
- **Media & attachments** - attach photos, scans, and documents to any record
- **Search** - filter nodes by name or description
- **Type filtering** - browse records by type
- **Infinite scroll** - lists load more as you scroll
- **Quick capture** - global `Cmd/Ctrl+K` sheet to add records without leaving the current page
- **Dark mode** - system-aware theme with manual toggle
- **Accounts** - local sign-in; each person's items, collections and files are private to them
- **API tokens** - scoped, expiring tokens for scripts
- **Self-hosted** - single `docker compose up` to run the full stack

---

## API tokens

Scripts and other tools can use Menagerist without your password through a personal access token.

1. Sign in, open Settings, then Account, and choose **New token** under Personal access tokens.
2. Name it, enter your password and pick what it may do: **Read only**, **Read and write**, or per-area access under Advanced. Choose an expiry (default 90 days, maximum 365).
3. Copy the token when it is shown. It appears only once.

Send it in a header:

```sh
curl -H "Authorization: Bearer mnst_..." https://your-server/api/v1/auth/me/permissions
```

A token carries only the permissions you give it, never more than you hold, and stops working when it expires or you revoke it. Use **Regenerate** for a new token with the same name and access. Changing or resetting your password removes all your tokens. A token cannot manage tokens or your account, and it cannot export or import your data. The interactive docs at `/api/docs` accept a token through Authorize. Operators can tune the limits with `MENAGERIST_IDENTITY_API_TOKEN_DEFAULT_DAYS`, `MENAGERIST_IDENTITY_API_TOKEN_MAX_DAYS` and `MENAGERIST_IDENTITY_API_TOKENS_PER_USER`.

---

## Stack

| Layer | Technology |
|---|---|
| Backend | Python / FastAPI / SQLAlchemy / Alembic / PostgreSQL |
| Frontend | SvelteKit / TypeScript / Tailwind CSS |
| Container | Docker / distroless image |

---

## Running locally

All of these run the full stack (Postgres + Menagerist) via Docker. There's no pre-built image yet - `menagerist` (or its `ghcr.io/samcorky/menagerist` equivalent) doesn't exist on a registry until the first tagged release, so every option below builds the image locally rather than pulling it. The build produces the backend's OpenAPI schema and the frontend's typed client itself, so a fresh clone needs nothing pre-generated.

### Easiest

Install [uv](https://docs.astral.sh/uv/):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # macOS/Linux
```

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"   # Windows
```

Then, from the repo root:

```sh
uv run poe init
uv run poe docker-up
```

The app is available at [http://localhost:8080](http://localhost:8080).

**First visit:** Menagerist asks you to create the administrator account (a username and a password of at least 10 characters). Anything already in the database is adopted by that account. The administrator can then add other people under Settings > Users, and each person sees only their own items. Accounts are local to your instance; there is no email or external sign-in yet. If you forget the administrator password, reset it from the command line: `docker compose exec menagerist menagerist identity reset-password --username <name>` (see [CONTRIBUTING.md](CONTRIBUTING.md#first-run-and-accounts)).

**Behind a reverse proxy.** Set `MENAGERIST_API_TRUSTED_PROXIES` to the proxy's address or network, and tell Menagerist its public address with `MENAGERIST_API_PUBLIC_ORIGIN=https://menagerist.example.com` plus `MENAGERIST_IDENTITY_COOKIE_SECURE=origin` if the proxy terminates TLS. Without the first, every visitor shares the proxy's address and 20 failed sign-ins from anyone lock sign-in for everyone for 15 minutes; without the second, the session cookie may be sent without `Secure`. `MENAGERIST_IDENTITY_COOKIE_SECURE` is `auto` by default (Secure when the app sees HTTPS), `origin` (follow the scheme of the public address, and refuse to start if none is set), or `always` / `never`. Signing in over plain `http://` sends the password and session cookie unencrypted, which is fine on `localhost` and a home network you trust, and not over the internet. Details are in [CONTRIBUTING.md](CONTRIBUTING.md#first-run-and-accounts).

**Sign-in and first-run setup refuse requests from other sites.** The browser's own `Sec-Fetch-Site` header decides: `cross-site` is refused and `same-origin` is accepted, whatever the proxy does to the scheme or host. Without that header (very old browsers, or plain HTTP on a LAN address) or when it says `same-site`, the request's `Origin` must match the origin the app sees, so there the proxy must pass `Host` and `X-Forwarded-Proto` through and be listed in `MENAGERIST_API_TRUSTED_PROXIES`. `MENAGERIST_API_CORS_ORIGINS` is not the fix for a proxy problem.

**If the proxy setup looks wrong, Menagerist says so.** The first time in an hour it sees forwarding headers from a peer it does not trust, or a browser whose origin differs from the one it saw, it logs a warning (`reverse proxy may be misconfigured`) with the setting to change. With `MENAGERIST_API_PUBLIC_ORIGIN` set it also notices requests that arrive at a different address (`publicOriginMismatch`) or over plain `http` when the public address is `https` (`insecureOrigin`); the container's own health check is ignored. Administrators also see a warning for `proxy:configuration` at `/api/v1/system/health/ready/detail` for the next hour. It is a warning only: `/api/health/ready` still answers pass. Find your proxy's network with `docker network inspect <network>` and list it, for example `MENAGERIST_API_TRUSTED_PROXIES=172.21.0.0/16`, in `.env`, then recreate the container.

**Send HSTS from the proxy.** Menagerist trusts the browser's headers, and the browser only keeps using HTTPS if the proxy tells it to. Set `Strict-Transport-Security` at the TLS-terminating proxy so a browser never falls back to plain HTTP for your address (Caddy `header Strict-Transport-Security "max-age=15552000"`, nginx `add_header Strict-Transport-Security "max-age=15552000" always;`, Traefik's `stsSeconds` headers middleware). The app does not send it itself because it cannot know it is reached over HTTPS.

**Deployment notes.** No other website may call the API unless you list its origin in `MENAGERIST_API_CORS_ORIGINS` (only needed if the frontend is hosted separately). Menagerist does not send `Strict-Transport-Security`; set it at the TLS-terminating proxy (see above). The public `/api/health/ready` answers only pass or fail; measurements are for administrators at `/api/v1/system/health/ready/detail`.

**Database memory tuning.** The Postgres container is capped at 512 MB and its memory settings are sized to match. Set any of these in a `.env` file next to `compose.yaml` (Compose reads it automatically) and recreate the stack. The defaults suit a small install; raise them together on a larger machine.

| `.env` variable | Default | Postgres' own default | When to change it |
| --- | --- | --- | --- |
| `POSTGRES_MEM_LIMIT` | `512m` | no limit | The container's hard memory cap. Raise it with the values below if the database is large. |
| `POSTGRES_SHARED_BUFFERS` | `128MB` | `128MB` | About a quarter of the memory cap. The most useful one to raise on a bigger machine. |
| `POSTGRES_EFFECTIVE_CACHE_SIZE` | `256MB` | `4GB` | A planner hint for how much data the OS can cache; keep it near half the memory cap so the planner is not over-optimistic. |
| `POSTGRES_WORK_MEM` | `4MB` | `4MB` | Memory per sort or hash in a query. Raise it only if large sorts spill to disk, as it applies to each step of each connection. |
| `POSTGRES_MAX_CONNECTIONS` | `100` | `100` | Each worker process keeps a pool of connections; lower it on a very small machine, and keep it above the total of all pools. |

For example, a machine with 2 GB to spare for the database: `POSTGRES_MEM_LIMIT=2g`, `POSTGRES_SHARED_BUFFERS=512MB`, `POSTGRES_EFFECTIVE_CACHE_SIZE=1GB`. To see the values in effect: `docker compose exec postgres psql -U menagerist -c "SHOW shared_buffers"`.

**Web server workers.** `MENAGERIST_SERVER_WORKERS` is `auto` by default (or a number from `1` to `16`). `auto` follows the advice in [Granian's documentation](https://github.com/emmett-framework/granian), which Menagerist runs on: one worker per CPU core on a plain host, and one worker per container on Docker and Kubernetes, scaling by running more containers. So the Docker image runs one worker, and so does `serve --reload` for development. One worker already serves many requests at once, because it is asynchronous. Set a number to override it, for example on a many-core machine where you would rather not run several containers. Each worker can hold up to 15 database connections, and the background worker another 15, so at startup the server reads Postgres' `max_connections` and logs a warning if the pools could exceed it; raise `POSTGRES_MAX_CONNECTIONS` with the workers. A changed setting can take up to 5 seconds to reach every worker.

**Your own changes: `compose.override.yaml`.** Compose merges a file named `compose.override.yaml` onto `compose.yaml` automatically, so local choices stay out of the shipped file and survive an update. The repository ignores it (`.gitignore`), so create it yourself next to `compose.yaml`. Anything you set replaces the matching entry in `compose.yaml`; the rest is kept. For example, keep media and backups in plain folders you can see and back up, and reach the database from the host for a one-off query:

```yaml
services:
  menagerist:
    volumes:
      - ./data/media:/data/media
      - ./backups:/data/backups
  worker:
    volumes:
      - ./data/media:/data/media
      - ./backups:/data/backups
  postgres:
    ports: !override
      - "127.0.0.1:5432:5432"
```

Give the app and the worker the same volumes, as above, because both read and write media. `!override` replaces a list instead of adding to it. `docker compose config` prints the merged result to check it. Running `docker compose -f compose.yaml up` skips the override.

### The same thing, one `poe` task at a time

```sh
uv run poe init            # sync deps + install git hooks
uv run poe docker-build    # build the Menagerist image
uv run poe docker-up       # start Postgres + Menagerist, detached
```

### What `poe` is actually running (no `poe`)

```sh
docker buildx bake -f docker-bake.hcl local
docker compose up -d --force-recreate
```

`uv run` syncs and resolves the backend package on its own - no separate install step. If you've activated the project's venv instead (see [CONTRIBUTING.md](CONTRIBUTING.md)), drop the `uv run` prefix and call `menagerist` directly.

---

## Roadmap

See [ROADMAP.md](ROADMAP.md) for the product direction and release strategy.

---

## Documentation

| Document | Contents |
|---|---|
| [ROADMAP.md](ROADMAP.md) | Product direction and UX philosophy |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Dev setup, commands, and testing |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System topology and data model |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Significant technical decisions and rationale |
| [backend/README.md](backend/README.md) | Backend architecture and conventions |
| [frontend/README.md](frontend/README.md) | Frontend stack and dev workflow |
| [frontend/DESIGN_GUIDELINES.md](frontend/DESIGN_GUIDELINES.md) | Frontend UX/UI rules |

---

## Why Menagerist?

Inspired by the idea of a *menagerie* - a curated collection of things. Rather than forcing everything into predefined categories, Menagerist is designed to be general-purpose and adaptable.

> **Your collection, your structure.**

A subtle nod to *Star Trek: The Original Series - The Menagerie*.
