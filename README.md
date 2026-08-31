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
| Container | Docker / Chainguard distroless images |

---

## Running locally

```bash
docker compose -f compose.dev.yaml up
```

The app is available at [http://localhost:8080](http://localhost:8080).

---

## Roadmap

See [ROADMAP.md](ROADMAP.md) for the full planned feature set.

---

## Why Menagerist?

Inspired by the idea of a *menagerie* — a curated collection of things. Rather than forcing everything into predefined categories, Menagerist is designed to be general-purpose and adaptable.

> **Your collection, your structure.**

A subtle nod to *Star Trek: The Original Series — The Menagerie*.
