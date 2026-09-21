# Context and conventions

> Part of the field-types spec. Start with `00-INDEX.md`. This file is the shared context for every work item.


1. Read `AGENTS.md`, `CLAUDE.md`, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md` and `docs/field-types.md` first. Follow their conventions (hexagonal boundaries, mypy `--strict`, ArchUnitPython tests, tiered coverage floors, Poe tasks via `uv run`, conventional commits). Do not invent task names; use the repo's own.
2. Work items are numbered `WI-n` and are independent unless a dependency is listed. Keep each item a separate, reviewable change. Do not commit on the user's behalf (`CLAUDE.md`): leave committing to the user.
3. Where the spec says *proposal* or *open question*, decide after reading the code, and record the decision in `docs/DECISIONS.md`. Push back if a proposal violates an architecture rule. Prefer the smallest change that satisfies the acceptance criteria.
4. Output complete files, not patches, in any hand-off notes.
   Unit tests are listed under each work item; integration tests are collected in `testing-strategy.md`, with a table mapping each work item to the integration coverage it needs. A work item is not done until both exist.
5. The three frontend test files `etag-412`, `etag-interceptor` and `version-header-interceptor` fail locally only when `src/lib/api/generated/client.gen` has not been generated. That is environmental and unrelated to this spec.
6. **Vocabulary.** The code says *node type* and *edge type*. The UI currently calls a node type a "Category" (`settings/categories`); renaming that to **item type** is out of scope for this change (see `01-context-and-conventions.md`), but every new piece of UI text in this spec already says *item type*, so it will not need re-editing. Reusable parts are *presets* (WI-19).


---

## Cross-cutting requirements

- **Docs.** Update `docs/field-types.md` (the `x-menagerist` namespace and the keys it replaces, rating, opaque fields, registration-order and `kind` rules) and add `docs/DECISIONS.md` entries for: soft required, changed-keys-only validation, archive-then-purge, and the `x-menagerist` namespace.
- **Compatibility.** Schemas and attributes stay inside the existing JSONB columns, so most items need no table changes. The exceptions are WI-19 (a new `preset` table and migration) and WI-19d (overlay, decided; a nullable `extra_schema` column). There is no data migration and no compatibility layer for old-format schemas (WI-14 decision); node types and edge types using `x-layout`, `x-multiline` or root `required` are recreated or re-saved.
- **Architecture.** Backend work stays in the `graph` module: handlers in `application`, protocols in `ports`, SQLAlchemy in the platform adapters. No cross-module imports; ArchUnitPython tests must stay green.
- **Typing and lint.** `mypy --strict`, ruff, and the frontend lint and svelte-check must pass on everything touched.
- **Coverage.** Respect the per-component floors enforced from the repo's coverage configuration. Add unit tests with each work item and the integration tests from `testing-strategy.md`.
- **Out of scope: renaming "Category" in the UI.** The user-facing name for a node type should become **item type** (proposal; see open question 34). It touches UI labels, the `settings/categories` route, `category-select.svelte` and related component names, docs and screenshots, and is a separate change. Keep the code terms (`node_type`, `NodeType`, `/node-type`) as they are. This spec's new UI text already uses *item type*. Do not use "Kind" (clashes with a field's `kind`) or plain "Type" (clashes with JSON Schema `type` and `Node.type`).
- **Out of scope: connection follow-ups** found while checking real examples (a poster signed in three places; a photo with six people at an event). Verified in `collection/[id]/+page.svelte`: (1) and (2) are now specced as WI-22a and WI-22b (the item page listed only a connection's label and the other item's name, and connections were added one at a time); (5) search does not follow connections, so a poster is not found by the signer's name when that name lives in a connection detail or on a connected Person (guidelines §8 expects "keanu reeves" to find connected items); (3) later, a derived "where" on an item that follows "Taken at" then "Held at" to a Place; (4) the add-connection form labels the picker "Relationship" where guidelines §24 say "Connection". These belong to a connections spec, not this one;
- **Update the design guidelines in the same change (decided).** `frontend/DESIGN_GUIDELINES.md` is binding, so update it with the work: §7 (highlighted values on cards), §14 (Undo for connecting items and removing a field; confirmation for permanent deletion), §16a (Rating, display options, Table label), §16b (typed per-item fields, passive tips in Settings), §17 (connection rows show details). Keep the wording short and explain why.
- **Client generation.** If an API endpoint is added (WI-9), regenerate the hey-api client the repo's normal way. Do not hand-edit generated code.
