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

Menagerist is a flexible collection manager built on a graph model. Records can represent anything — items, people, events, places — and can be connected to each other in whatever way makes sense for your collection.

The graph model is deliberately hidden from the user. You interact with familiar concepts like items and relationships; Menagerist handles the structure underneath.

---

## Current state

The core is working end-to-end:

- **Nodes** — create, view, edit, soft-delete records of any type
- **Node types** — define types with labels, descriptions, and custom attribute schemas
- **Relationships** — connect records with typed, directional or symmetric edges
- **Relationship types** — named edge types with forward/reverse labels and attribute schemas
- **Attributes** — freeform and schema-driven key/value metadata on any record
- **Media & attachments** — attach photos, scans, and documents to any record
- **Search** — filter nodes by name or description
- **Type filtering** — browse records by type
- **Infinite scroll** — lists load more as you scroll
- **Quick capture** — global `Cmd/Ctrl+K` sheet to add records without leaving the current page
- **Dark mode** — system-aware theme with manual toggle
- **Self-hosted** — single `docker compose up` to run the full stack

---

## Stack

| Layer | Technology |
|---|---|
| Backend | Python / FastAPI / SQLAlchemy / Alembic / PostgreSQL |
| Frontend | SvelteKit / TypeScript / Tailwind CSS |
| Container | Docker / distroless image |

---

## Running locally

All of these run the full stack (Postgres + Menagerist) via Docker. There's no pre-built image yet — `menagerist` (or its `ghcr.io/samcorky/menagerist` equivalent) doesn't exist on a registry until the first tagged release, so every option below builds the image locally rather than pulling it. The build produces the backend's OpenAPI schema and the frontend's typed client itself, so a fresh clone needs nothing pre-generated.

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

`uv run` syncs and resolves the backend package on its own — no separate install step. If you've activated the project's venv instead (see [CONTRIBUTING.md](CONTRIBUTING.md)), drop the `uv run` prefix and call `menagerist` directly.

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

Inspired by the idea of a *menagerie* — a curated collection of things. Rather than forcing everything into predefined categories, Menagerist is designed to be general-purpose and adaptable.

> **Your collection, your structure.**

A subtle nod to *Star Trek: The Original Series — The Menagerie*.
