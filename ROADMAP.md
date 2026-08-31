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

Versioning follows CalVer. The project is currently on a `0.`-prefixed scheme (`0.YYYY.MM`) to signal pre-stable — but the bar for the first merge to `main` is lower than it might seem.

**Merge to `main` (`0.x`)** — target once the following are done:
- UI polish pass: tighten spacing, typography, empty states, loading states, and interaction feedback across all existing screens
- Playwright end-to-end test suite covering the core happy paths (create a node, set a type, add a relationship, use quick capture, manage types)

The `0.` prefix signals that the API, data model, and features are still evolving — no need to wait for P0 or P1 features. The merge bar is "solid enough to self-host without embarrassment."

**Public images on GHCR** — publish `ghcr.io/…/menagerist-backend` and `ghcr.io/…/menagerist-frontend` on every merge to `main` via CI. Tagged as `0.YYYY.MM.DD` and `latest`. Makes self-hosting a one-liner without needing to build from source.

**Stable release (`YYYY.MM`)** — drop the `0.` prefix once the P0 and P1 features are complete and the data model is unlikely to have breaking migrations. At that point CalVer without the leading zero becomes the normal scheme and `latest` tracks it.

---

## What's built

- [x] Nodes with optional, one-time-settable type
- [x] Node types with attribute schemas
- [x] Relationships (edges)
- [x] Relationship types with directional/symmetric labels and attribute schemas
- [x] CRUD and soft deletion for all entities
- [x] Cursor-based pagination with infinite scroll
- [x] Node search (name and description)
- [x] Type filtering on node list
- [x] Quick capture (`Cmd/Ctrl+K`)
- [x] Custom attributes (freeform key/value)
- [x] Schema-driven attribute fields (text, number, boolean, date, select, richtext)
- [x] Dark mode

---

## P0 — Foundation for a usable product

These unblock everything else. Without them the app doesn't feel like a collection manager.

- [ ] **Collection-first UX** — replace graph terminology (nodes, edges) with user-facing concepts: Items, People, Events, Places. Navigation and empty states should speak the user's language, not the data model's.
- [ ] **Improved detail pages** — unified view of a record's fields, media, relationships, and history on a single page; currently split and sparse
- [ ] **Media & attachments** — photos, scans, and documents attached to records; essential for physical collection items
- [ ] **Global full-text search** — search across names, descriptions, and indexed text fields across all record types

---

## P1 — Core value features

The features that make Menagerist worth using over a spreadsheet.

- [ ] **First-class relationship records** — model `Signature`, `Purchase`, `Loan`, `Visit`, etc. as records in their own right, linking a person, an item, and an event; reuses the same graph machinery but exposed as meaningful, named connections
- [ ] **Relationship metadata** — attach fields (date, location, inscription, authentication status) to a relationship record
- [ ] **Tags** — lightweight, freeform labels on any record: `Favourite`, `Rare`, `Authenticated`, `Wanted`
- [ ] **Dashboard** — recently added, recently viewed, pinned records, and useful statistics
- [ ] **Favourites / pinned records**
- [ ] **Recently viewed**
- [ ] **Mobile-optimised actions** — collection browsing and common actions fully usable on a phone; optimised for use at events, markets, and signings

---

## P2 — Depth and organisation

Makes the app usable for larger or more structured collections.

- [ ] **Filtering & sorting** — filter any list by type, tags, fields, and relationships; sort by name, date, or custom fields
- [ ] **Import / export** — CSV and JSON round-trip, including relationships and metadata; critical for onboarding existing collections
- [ ] **Contextual actions** — e.g. from a poster's detail page → `Add signature`; from a person → `Add to signing event`
- [ ] **Saved views / smart collections** — e.g. `My BTTF autographs`, `Items signed but not authenticated`
- [ ] **Timeline view** — chronological view derived from date fields on records and relationships; configurable date field (e.g. `Purchase date`, `Signing date`, `Event date`)
- [ ] **Human-friendly relationship labels** — natural singular/plural labels surfaced in the UI: `Signed by` / `Signed items`
- [ ] **Related items panel** — surface connected records on detail pages: `Michael J. Fox → Signed items (2)`
- [ ] **Reverse relationship browsing** — viewing a person shows the items they've signed, events they attended, etc.

---

## P3 — Infrastructure prerequisites

Required before multi-user or sharing features can land.

- [ ] **Authentication** — user accounts and sessions
- [ ] **Multiple users** — per-user data separation
- [ ] **Permissions** — control who can view or edit which records

---

## P4 — Power features

High value once the core experience is solid.

- [ ] **Metadata enrichment** — pull fields and media from external sources (TMDB, MusicBrainz, IGDB, etc.)
- [ ] **Relationship-based filtering** — e.g. `Items signed by Michael J. Fox`
- [ ] **Graph visualisation** — explore connected records visually
- [ ] **Activity log** — record-level history: `Rating changed 8 → 9`, `Signature added`
- [ ] **Undo / restore** — reverse recent changes
- [ ] **Bulk editing** — edit, tag, move, or delete multiple records at once
- [ ] **PWA with offline support** — installable on iOS and Android; service worker caches the shell and recent records for offline browsing; a local write queue captures new records, edits, and image attachments made without a connection and syncs them when connectivity returns; conflict resolution for edits made on multiple devices
- [ ] **Public / shared collections** — read-only sharing of a collection or individual record

---

## P5 — Integrations

- [ ] **Webhooks** — notify external services when records change
- [ ] **API tokens** — personal access tokens for scripts and integrations
- [ ] **Automation** — e.g. `New movie added → fetch metadata automatically`
