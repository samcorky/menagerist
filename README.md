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
- **Self-hosted** - single `docker compose up` to run the full stack

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

**Behind a reverse proxy.** Set `MENAGERIST_TRUSTED_PROXIES` to the proxy's address or network, and `MENAGERIST_COOKIE_SECURE=true` if the proxy terminates TLS. Without the first, every visitor shares the proxy's address and 20 failed sign-ins from anyone lock sign-in for everyone for 15 minutes; without the second, the session cookie may be sent without `Secure`. Details are in [CONTRIBUTING.md](CONTRIBUTING.md#first-run-and-accounts).

**Sign-in and first-run setup refuse requests from other sites.** The browser's own `Sec-Fetch-Site` header decides: `cross-site` is refused and `same-origin` is accepted, whatever the proxy does to the scheme or host. Without that header (very old browsers, or plain HTTP on a LAN address) or when it says `same-site`, the request's `Origin` must match the origin the app sees, so there the proxy must pass `Host` and `X-Forwarded-Proto` through and be listed in `MENAGERIST_TRUSTED_PROXIES`. `MENAGERIST_CORS_ORIGINS` is not the fix for a proxy problem.

**If the proxy setup looks wrong, Menagerist says so.** The first time in an hour it sees forwarding headers from a peer it does not trust, or a browser whose origin differs from the one it saw, it logs a warning (`reverse proxy may be misconfigured`) with the setting to change. Administrators also see a warning for `proxy:configuration` at `/api/health/ready/detail` for the next hour. It is a warning only: `/api/health/ready` still answers pass. Find your proxy's network with `docker network inspect <network>` and list it, for example `MENAGERIST_TRUSTED_PROXIES=172.21.0.0/16`, in `.env`, then recreate the container.

**Send HSTS from the proxy.** Menagerist trusts the browser's headers, and the browser only keeps using HTTPS if the proxy tells it to. Set `Strict-Transport-Security` at the TLS-terminating proxy so a browser never falls back to plain HTTP for your address (Caddy `header Strict-Transport-Security "max-age=15552000"`, nginx `add_header Strict-Transport-Security "max-age=15552000" always;`, Traefik's `stsSeconds` headers middleware). The app does not send it itself because it cannot know it is reached over HTTPS.

**Deployment notes.** No other website may call the API unless you list its origin in `MENAGERIST_CORS_ORIGINS` (only needed if the frontend is hosted separately). Menagerist does not send `Strict-Transport-Security`; set it at the TLS-terminating proxy (see above). The public `/api/health/ready` answers only pass or fail; measurements are for administrators at `/api/health/ready/detail`.

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
