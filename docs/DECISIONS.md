# Technical Decisions

Significant architectural choices and their rationale. Entries are added when a decision is made and updated when circumstances change. For the overall system structure, see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Hexagonal architecture with a strict dependency rule

**Decision:** The backend uses hexagonal (ports and adapters) architecture. The enforced dependency direction is `entrypoints → adapters → application → domain`. Domain has zero framework imports; application depends only on port Protocols it defines itself.

**Rationale:** Keeps business logic testable without running a web server or database. Domain entities and use cases can be instantiated with no infrastructure. The dependency rule is not convention — it is checked at CI time by `archunitpython` tests in `backend/tests/architecture/`.

**Tradeoff:** More boilerplate per bounded context than a flat structure. The test-speed and design-clarity benefits are judged to compound as the codebase grows.

---

## Vertical slices by bounded context, not horizontal layers

**Decision:** Code is organised as `modules/<context>/` (domain, application, ports, adapters), not as repo-wide `models/`, `services/`, `routers/` directories.

**Rationale:** Horizontal organisation couples every feature to every other feature at the import level. Vertical slices keep a module's internals self-contained — adding a bounded context does not require touching every layer. The organising question is "what domain concept is this about?", not "what kind of code is this?".

---

## UUID7 primary keys

**Decision:** Every entity primary key is a `uuid7` generated in the domain layer at construction time.

**Rationale:** UUID7 is time-ordered, so it supports keyset pagination (`after: UUID | None, limit: int`) without a separate sort column. Generated in the domain layer so IDs are consistent across persistence implementations and testable without a database.

---

## In-memory adapters as first-class citizens

**Decision:** Every port ships an in-memory implementation alongside its SQLAlchemy implementation as a sibling file in `adapters/persistence/`. Application-layer and router tests wire the in-memory adapter directly.

**Rationale:** Mock-based tests can pass while the real adapter is broken — this has happened once where mock/prod divergence masked a broken migration. In-memory adapters satisfy the same port Protocol as the real adapter, so tests exercise the actual contract. They also keep the unit test loop near-instant.

**Tradeoff:** Two implementations per port. In-memory implementations are typically trivial (an in-memory dict or list) and the test-correctness and speed benefits are worth it.

---

## Timestamps set in the domain layer

**Decision:** Entity `created_at` and `updated_at` are set in domain methods via `datetime.now(UTC)`, not via SQLAlchemy `server_default` or `onupdate`.

**Rationale:** Timestamping is domain behaviour, not a database side effect. Setting it in domain methods makes it testable with `freezegun`/`time-machine` without a live database, and ensures it behaves consistently across persistence backends.

---

## Shared `UnitOfWork` Protocol, not per-module subclasses

**Decision:** `shared_kernel/unit_of_work.py` defines `UnitOfWork[TRepos]` once. Two concrete implementations exist (`SqlAlchemySessionUnitOfWork` in `platform/`, `InMemoryUnitOfWork` in `shared_kernel/`), written once and reused by every module. A module contributes only a `Repos` dataclass and two one-line factory functions.

**Rationale:** A per-module UoW subclass repeats session lifecycle code (begin/rollback/close/commit) N times. A single central UoW listing all modules' repos was rejected — it couples modules to each other and implies transactions spanning bounded contexts, which DDD treats as the wrong boundary.

---

## CQRS as a typing convention, not a bus

**Decision:** `shared_kernel/cqrs.py` defines `CommandHandler[TCommand, TResult]` and `QueryHandler[TQuery, TResult]` Protocols. Every use case implements one. Routers call use cases directly — there is no mediator, dispatcher, or pipeline.

**Rationale:** The pattern enforces a consistent shape for every use case and makes `mypy --strict` verify it. A bus with pipeline behaviors would give a single seam for cross-cutting concerns, but nothing currently requires that uniformity enforced. Adding a bus later is possible — the typed-handler convention is a prerequisite and is already in place.

---

## Static SPA, not server-side rendering

**Decision:** The SvelteKit frontend uses the static adapter. No `+page.server.ts`. Data is fetched client-side inside components.

**Rationale:** Menagerist is a self-hosted personal app, not a public-facing site requiring SEO or SSR performance. A static build simplifies deployment (nginx serves a directory), eliminates a Node.js runtime from the production image, and makes the Docker setup self-contained. First-load skeleton states are an acceptable tradeoff.

---

## Single Alembic environment for all modules

**Decision:** One `alembic/versions/` directory for the entire backend, not one per bounded context.

**Rationale:** All bounded contexts share a single PostgreSQL schema in v1. A multi-environment Alembic setup would add complexity (ordering, inter-module dependency chains) with no benefit at this scale. If contexts are ever split into separate services, the migration history can be partitioned at that point.

---

## AllowAll authorization adapter in v1

**Decision:** The v1 `AuthorizationPort` implementation always permits every action. Routes depend on `get_current_actor` and use cases take `actor` in `handle()`, but no checks are enforced.

**Rationale:** The wiring exists so that when the `identity` module lands, only the composition root changes — no route or use case signatures need updating. The app is single-user and self-hosted in v1; multi-user support is a later roadmap item. Building real authorization before identity exists would require faking it in ways that add coupling.

---

## Pluggable field-type registry (frontend)

**Decision:** The schema editor and attributes editor dispatch to field types via a registry (`field-types/registry.ts`) rather than switch/case blocks. Each type registers a `FieldTypeDescriptor` with `toSchema`, `fromSchema`, optional `EditorExtras`, `InputWidget`, and optional `ViewWidget`. New types are added by creating a descriptor file and one import line in `index.ts`.

**Rationale:** A switch/case or `if`/`else if` chain in the editor components couples every field type to every component that renders them. The registry inverts that: each type owns its own rendering and serialisation logic, and the components are unaware of what types exist. `descriptorForProp` uses registration order as precedence — most-specific matchers (date, longtext, choice) register before the `text` fallback, so no descriptor needs to guard against other descriptors winning first.

**Tradeoff:** Registration order is load-order dependent. The `index.ts` file is the canonical ordering point — it must be read before adding a new type. A misplaced import (e.g. `text` before `date`) silently causes `date` fields to render as plain text inputs.

**Backend alignment:** All built-in field types use standard JSON Schema keywords (`type`, `format`, `enum`, `properties`, `items`). The backend validates with `jsonschema[format-nongpl]` which covers all standard `format` strings. A new type only needs backend code if it introduces a non-standard `format` string — see [field-types.md](field-types.md).

---

## CalVer with a `0.` pre-stable prefix

**Decision:** Version scheme is `0.YYYY.MM.PATCH` until the data model and API stabilise, then `YYYY.MM.PATCH`.

**Rationale:** CalVer communicates the release date naturally for a personal app without semantic versioning overhead. The `0.` prefix signals pre-stable — breaking migrations and API changes are expected — without requiring a formal major-version bump. Dropping the `0.` is the public signal that the schema and API are stable.

---

## Unrecognised schema properties round-trip as an `opaque` field kind (frontend)

**Decision:** A property no field-type descriptor matches (for example `format: 'email'`, or an enum sub-property of a group) becomes an `opaque` field carrying the original property in `raw`. Its `toSchema` returns the raw property with only the title updated. `opaque` is not user-selectable, and the editors show a "custom" badge instead of a kind dropdown.

**Rationale:** Falling back to `text` silently dropped keywords such as `format` on the next save. Keeping the raw property makes open-edit-save lossless for schemas written through the API.

**Related:** an untouched boolean cell in a group row saves as `false`, because a checkbox has no unset state; blank number, date and choice cells are omitted, while blank text stays `''`.

---

## One `x-menagerist` namespace for non-validation schema metadata

**Decision:** Layout, advisory `required`, an explicit field `kind`, display hints and archived flags live under a single `x-menagerist` member (root and per property), read and written through one accessor module per side (`schema-meta.ts`, `schema_meta.py`). `x-multiline`, `x-layout` and the root `required` array are replaced with no migration and no legacy reader. The backend strips the root `required` array and archived properties before validating attributes.

**Rationale:** Flat vendor keywords scattered metadata across the schema, made a field's identity depend on guessing from its shape, and had no version marker. One namespace with an explicit `kind` gives a direct registry lookup, a place to version the format, and a clear test: removing `x-menagerist` must not change validity (apart from the two advisory exceptions above, which enforce that `required` never blocks a save).

**Tradeoff:** Item types saved in the old format lose their layout, long-text rendering and required markers until they are re-saved. Accepted: no stored attribute data is affected and the app has no external users yet.

---

## Field keys are the slug of the title at creation, then immutable

**Decision:** A new field's key is the ASCII slug of its title (underscores, at most 40 characters, `field` when nothing usable remains), made unique with `_2`, `_3` against every existing key including archived fields (case-insensitive) and names inherited from `Object.prototype`. The key follows the title only until the schema is saved; from then on renaming the label never changes it. Group sub-fields use the same rule within their group. Existing UUID keys keep working, and a schema may mix both.

**Rationale:** Readable attribute keys make the API, exports and search context understandable without the schema, while immutability keeps the guarantees UUIDs gave: renaming a label never touches stored data and references by key (layout, `required`) stay valid. Names such as `constructor` are avoided because `in` and index lookups on `properties` would otherwise find inherited members.

**Tradeoffs:** A key can drift from its label after a rename. Re-adding a same-titled field can reattach orphaned data, which is accepted. There is no "Change key" action in v1, and the key is never shown in the UI. Warning when a new key matches an existing custom detail name is deferred to the per-item custom fields work.

---

## Rating is a constrained number matched by an explicit kind

**Decision:** A rating is stored as a JSON number with `minimum: 1`, `maximum: 5` and `multipleOf: 1`, and `x-menagerist.kind: "rating"`. The descriptor only matches an explicit kind. An unset rating is omitted, and clicking the current star clears it. It can be a group sub-field.

**Rationale:** A constrained number needs no backend code, and both validators enforce the range. Matching on the explicit kind removes the registration-order dependency on `number` (they share `type: 'number'`), so a plain number with the same constraints is never captured.

**Tradeoff:** The star count is fixed at 5 until display options (WI-11) make it configurable.

---

## `required` is advisory and never reaches a validator

**Decision:** Required fields are stored in `x-menagerist.required` and shown with an asterisk only. The schema editor never writes a standard `required` array, and both validators (backend `validate_attributes`, client-side attributes editor) validate a copy of the schema with any root `required` removed, so a schema authored through the API cannot make required block a save.

**Rationale:** Design guideline §16a: required expresses what the collector considers a complete record, not a constraint the app enforces. Before this, adding a required field made every existing item of that type fail its next save, even when the user had not touched the field.

**Tradeoff:** A malformed value still fails validation; only a missing value is tolerated. The "missing information" summary (§18) is a separate feature.

---

## Updates validate only the attributes that changed

**Decision:** `UpdateNode` and `UpdateEdge` pass the stored attributes as `previous` to `validate_attributes`, which drops errors under any top-level key whose value is unchanged. Errors against the whole object are always kept, and create paths keep full validation. Values are compared as canonical JSON, so `1`, `1.0` and `true` count as different.

**Rationale:** The UI sends the whole attributes dict on every save, and editing a type's schema never touches existing items. Without this, tightening a schema (a removed choice option, a changed field kind, a new constraint) made an item unsaveable even when the user edited an unrelated field.

**Tradeoff:** A stale invalid value stays in the data until someone edits it. Editing it to another invalid value is still rejected. Comparison is per top-level key, so a change anywhere inside a group re-validates the whole group.
