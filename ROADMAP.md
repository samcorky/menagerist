# Menagerist — Feature Roadmap

## Design principle

Menagerist should be **simple for a first-time user, while becoming increasingly powerful as they explore it**.

The underlying graph model is deliberately flexible, but users should not need to understand concepts like nodes, edges, schemas, or graph traversal to use the application. The UI should present familiar concepts — **items, people, events, signatures, collections, relationships** — while the graph model works underneath.

Prefer **progressive disclosure**: start with a straightforward collection-management experience and reveal more advanced capabilities when they become useful.

Features should be generic and reusable rather than hard-coded around a single collection type. A `Signature` can connect a person, an item, and an event — the same underlying mechanisms can support purchases, loans, appearances, memberships, and more.

The ideal journey looks like:

> **Start simple → add things → discover relationships → customise when needed → unlock the full graph.**

A user should be able to start with:
> `Add → Back to the Future Poster`

and eventually discover they can model:
> `Poster → Signature → Michael J. Fox → Signing Event → London Comic Con`

without ever being forced to think in terms of graph theory.

---

## Release milestones

Versioning follows CalVer. The project is currently on a `0.`-prefixed scheme (`0.YYYY.MM.PATCH`) to signal pre-stable — but the bar for the first merge to `main` is lower than it might seem.

**Merge to `main` (`0.x`)** — target once the following are done:
- UI polish pass: tighten spacing, typography, empty states, loading states, and interaction feedback across all existing screens
- Playwright end-to-end test suite covering the core happy paths (create a node, set a type, add a relationship, use quick capture, manage types)

The `0.` prefix signals that the API, data model, and features are still evolving — no need to wait for the full feature backlog. The merge bar is "solid enough to self-host without embarrassment."

**Public images on GHCR** — publish `ghcr.io/…/menagerist-backend` and `ghcr.io/…/menagerist-frontend` on every merge to `main` via CI. Tagged as `0.YYYY.MM.DD` and `latest`. Makes self-hosting a one-liner without needing to build from source.

**Stable release (`YYYY.MM.PATCH`)** — drop the `0.` prefix once the core feature set is complete and the data model is unlikely to have breaking migrations. At that point CalVer without the leading zero becomes the normal scheme and `latest` tracks it.

The feature backlog itself is tracked outside this repo (project board), not maintained here — this document covers direction and philosophy, not the live task list.
