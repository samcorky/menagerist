# Technical Decisions

Significant architectural choices and their rationale. Entries are added when a decision is made and updated when circumstances change. For the overall system structure, see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Hexagonal architecture with a strict dependency rule

**Decision:** The backend uses hexagonal (ports and adapters) architecture. The enforced dependency direction is `entrypoints → adapters → application → domain`. Domain has zero framework imports; application depends only on port Protocols it defines itself.

**Rationale:** Keeps business logic testable without running a web server or database. Domain entities and use cases can be instantiated with no infrastructure. The dependency rule is not convention - it is checked at CI time by `archunitpython` tests in `backend/tests/architecture/`.

**Tradeoff:** More boilerplate per bounded context than a flat structure. The test-speed and design-clarity benefits are judged to compound as the codebase grows.

---

## Vertical slices by bounded context, not horizontal layers

**Decision:** Code is organised as `modules/<context>/` (domain, application, ports, adapters), not as repo-wide `models/`, `services/`, `routers/` directories.

**Rationale:** Horizontal organisation couples every feature to every other feature at the import level. Vertical slices keep a module's internals self-contained - adding a bounded context does not require touching every layer. The organising question is "what domain concept is this about?", not "what kind of code is this?".

---

## UUID7 primary keys

**Decision:** Every entity primary key is a `uuid7` generated in the domain layer at construction time.

**Rationale:** UUID7 is time-ordered, so it supports keyset pagination (`after: UUID | None, limit: int`) without a separate sort column. Generated in the domain layer so IDs are consistent across persistence implementations and testable without a database.

---

## In-memory adapters as first-class citizens

**Decision:** Every port ships an in-memory implementation alongside its SQLAlchemy implementation as a sibling file in `adapters/persistence/`. Application-layer and router tests wire the in-memory adapter directly.

**Rationale:** Mock-based tests can pass while the real adapter is broken - this has happened once where mock/prod divergence masked a broken migration. In-memory adapters satisfy the same port Protocol as the real adapter, so tests exercise the actual contract. They also keep the unit test loop near-instant.

**Tradeoff:** Two implementations per port. In-memory implementations are typically trivial (an in-memory dict or list) and the test-correctness and speed benefits are worth it.

---

## Timestamps set in the domain layer

**Decision:** Entity `created_at` and `updated_at` are set in domain methods via `datetime.now(UTC)`, not via SQLAlchemy `server_default` or `onupdate`.

**Rationale:** Timestamping is domain behaviour, not a database side effect. Setting it in domain methods makes it testable with `freezegun`/`time-machine` without a live database, and ensures it behaves consistently across persistence backends.

---

## Shared `UnitOfWork` Protocol, not per-module subclasses

**Decision:** `shared_kernel/unit_of_work.py` defines `UnitOfWork[TRepos]` once. Two concrete implementations exist (`SqlAlchemySessionUnitOfWork` in `platform/`, `InMemoryUnitOfWork` in `shared_kernel/`), written once and reused by every module. A module contributes only a `Repos` dataclass and two one-line factory functions.

**Rationale:** A per-module UoW subclass repeats session lifecycle code (begin/rollback/close/commit) N times. A single central UoW listing all modules' repos was rejected - it couples modules to each other and implies transactions spanning bounded contexts, which DDD treats as the wrong boundary.

---

## CQRS as a typing convention, not a bus

*(The base classes changed on 2026-10-22: see "Declared access stances behind one guard" at the end.)*

**Decision:** `shared_kernel/cqrs.py` defines `CommandHandler[TCommand, TResult]` and `QueryHandler[TQuery, TResult]` Protocols. Every use case implements one. Routers call use cases directly - there is no mediator, dispatcher, or pipeline.

**Rationale:** The pattern enforces a consistent shape for every use case and makes `mypy --strict` verify it. A bus with pipeline behaviors would give a single seam for cross-cutting concerns, but nothing currently requires that uniformity enforced. Adding a bus later is possible - the typed-handler convention is a prerequisite and is already in place.

---

## Static SPA, not server-side rendering

**Decision:** The SvelteKit frontend uses the static adapter. No `+page.server.ts`. Data is fetched client-side inside components.

**Rationale:** Menagerist is a self-hosted personal app, not a public-facing site requiring SEO or SSR performance. A static build simplifies deployment (the backend serves the built files directly - see "Single-image deployment" below), eliminates a Node.js runtime from the production image, and makes the Docker setup self-contained. First-load skeleton states are an acceptable tradeoff.

---

## Single Alembic environment for all modules

**Decision:** One `alembic/versions/` directory for the entire backend, not one per bounded context.

**Rationale:** All bounded contexts share a single PostgreSQL schema in v1. A multi-environment Alembic setup would add complexity (ordering, inter-module dependency chains) with no benefit at this scale. If contexts are ever split into separate services, the migration history can be partitioned at that point.

---

## AllowAll authorization adapter in v1

**Superseded (2026-10-10)** by [Accounts and private ownership (multi-user Stage 1)](#accounts-and-private-ownership-multi-user-stage-1): `RoleAuthorizationAdapter` and a real `get_current_actor` replaced it. Kept for history.

**Decision:** The v1 `AuthorizationPort` implementation always permits every action. Routes depend on `get_current_actor` and use cases take `actor` in `handle()`, but no checks are enforced.

**Rationale:** The wiring exists so that when the `identity` module lands, only the composition root changes - no route or use case signatures need updating. The app is single-user and self-hosted in v1; multi-user support is a later roadmap item. Building real authorization before identity exists would require faking it in ways that add coupling.

---

## Pluggable field-type registry (frontend)

**Decision:** The schema editor and attributes editor dispatch to field types via a registry (`field-types/registry.ts`) rather than switch/case blocks. Each type registers a `FieldTypeDescriptor` with `toSchema`, `fromSchema`, optional `EditorExtras`, `InputWidget`, and optional `ViewWidget`. New types are added by creating a descriptor file and one import line in `index.ts`.

**Rationale:** A switch/case or `if`/`else if` chain in the editor components couples every field type to every component that renders them. The registry inverts that: each type owns its own rendering and serialisation logic, and the components are unaware of what types exist. `descriptorForProp` uses registration order as precedence - most-specific matchers (date, longtext, choice) register before the `text` fallback, so no descriptor needs to guard against other descriptors winning first.

**Tradeoff:** Registration order is load-order dependent. The `index.ts` file is the canonical ordering point - it must be read before adding a new type. A misplaced import (e.g. `text` before `date`) silently causes `date` fields to render as plain text inputs.

**Backend alignment:** All built-in field types use standard JSON Schema keywords (`type`, `format`, `enum`, `properties`, `items`). The backend validates with `jsonschema[format-nongpl]` which covers all standard `format` strings. A new type only needs backend code if it introduces a non-standard `format` string - see [field-types.md](field-types.md).

---

## CalVer with a `0.` pre-stable prefix

**Decision:** Version scheme is `0.YYYY.MM.PATCH` until the data model and API stabilise, then `YYYY.MM.PATCH`.

**Rationale:** CalVer communicates the release date naturally for a personal app without semantic versioning overhead. The `0.` prefix signals pre-stable - breaking migrations and API changes are expected - without requiring a formal major-version bump. Dropping the `0.` is the public signal that the schema and API are stable.

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

---

## Removing a saved field archives it

**Decision:** In the schema editor, removing a field that has been saved sets `x-menagerist.archived: true` instead of deleting the property. The property stays in `properties`, leaves the layout and `required`, and appears under "Removed fields" with a Restore action. Fields added in the current editing session are removed outright. Archived fields are skipped by `normalise()`, hidden from the attributes editor and from "Additional details", and ignored by both validators. Removing is reversible with a 5-second Undo toast, with no confirmation dialog. Permanently deleting a field's data is a separate, confirmed action (purge).

**Rationale:** Stored item data lives in JSONB and is not touched when a type changes, so deleting a property used to leave orphaned values that resurfaced under raw keys. Archiving keeps the data, makes removal safely undoable (guidelines §14) and lets a restored field show its old values again.

**Tradeoff:** A restored field returns at the end of the layout, not its old position (open question). Archived keys stay reserved, so a new field with the same title gets a `_2` suffix.

---

## Purging a field's data: usage counts and a paged, per-item purge

**Decision:** `GET /node-type/{id}/attribute/{key}/usage` and `DELETE /node-type/{id}/attribute/{key}` (and the same under `/edge-type`) count and permanently remove an attribute key across every item (or connection) of a type. New repository methods `count_with_attribute` and `list_with_attribute` use the JSONB `?` operator. The purge pages through the holders, removes the key from each and saves it through the unit of work, so `updated_at` and therefore the ETag change and a client holding a stale copy gets a 412. In the schema editor the action sits on archived fields as "Delete data permanently", behind a confirmation that repeats the count.

**Rationale:** Archiving keeps data (WI-8), so there has to be an explicit way to get rid of it. Saving each item rather than one bulk `UPDATE` keeps ETags honest, at the cost of speed on very large types (page size 100). Dedicated repository methods were chosen over extending `list` and `count`, which the attribute-search work also changes.

**Tradeoff:** No permission check for now, consistent with the other graph use cases: destructive commands such as the purge should check permissions once an authorisation model exists (`AuthorisedCommandHandler`, `AuthorizationPort` and `AllowAllAuthorizationAdapter` are ready). No events are emitted, because there is no publisher or outbox yet. The purge takes effect immediately on the server while the property is only removed from the schema when the form is saved. Keys containing `/` cannot be addressed by these routes.

---

## Saved fields may only change kind towards more permissive kinds

**Decision:** A field loaded from a saved schema can switch to a kind allowed by a central matrix (`field-types/kind-changes.ts`): text and longtext swap; number, boolean, date and choice become text or longtext; number and rating swap (with a warning that values outside 1 to 5 will error when edited). Everything else, including anything to or from a group, goes through "Replace" (archive the old field, add a new one). Fields added this session can be any kind. Switching kind drops `display` and `config`. Removing a choice option that stored values use shows a count but never blocks; those values are shown as "(no longer an option)" in the form. The usage endpoints take an optional `?value=` (exact string match, JSONB containment).

**Rationale:** Values are stored untyped in JSONB. Widening to text heals itself on the next save, while narrowing would reject or misread existing data. Because updates only validate changed values (WI-7), leftover values never block saving.

**Tradeoff:** The matrix is code, not per-descriptor, so a new kind needs an entry (unknown kinds may only keep themselves). Converting text to choice is only possible through a future suggestion that builds the options from existing values.

---

## Presentation variants are per-field "Show as" settings, not separate kinds

**Decision:** A field type declares `displayOptions` on its descriptor and the schema editor renders a dropdown for each. A style is stored as `x-menagerist.display` (unset means the type's default); the rating star count is editor state that maps to the standard `maximum` keyword. Widgets read the style from the property they receive, so stored values and validation never depend on it. First users: boolean (switch by default, checkbox, Yes/No buttons), choice (dropdown by default, radio buttons, chips) and rating (3, 5 or 10 stars). Yes/No buttons and chips can be cleared, so a top-level boolean saved as "not recorded" is now omitted rather than stored as `false`.

**Rationale:** One kind per stored data shape keeps the kind picker short and avoids competing shape matches; presentation is a setting on the field. Following the design guidelines, a boolean now defaults to a switch (it was a checkbox), which changes how existing boolean fields look until a type picks "Checkbox".

**Tradeoff:** Group sub-fields have no "Show as" control yet; they render with each type's default.

---

## Text constraints are generated anchored patterns, worded from the pattern

**Decision:** A text field's "Starts with" and "Ends with" rules are stored as standard JSON Schema: one anchored `pattern`, or an `allOf` of two for both, never a single combined regex. The pattern is the only stored copy: `text/constraints.ts` writes it and reads back exactly those forms; any other `pattern` or `allOf` is carried through unchanged as a "custom" rule. Users never type a regex. The API now returns `keyword` and `value` with every attribute validation error, and the client words a failed `pattern` (`Must start with "cover-"`) from the pattern itself, for its own and the server's errors. Client errors show once a field loses focus; the empty value of a constrained optional text field is omitted rather than sent as `''`.

**Rationale:** Constraints affect validity, so they are standard keywords (the `x-menagerist` principle). Patterns built from escaped literals, `^` and `$` behave the same in Python `re` and JavaScript's `u`-flag RegExp, which a shared fixture (`shared/contracts/regex-conformance.json`) checks in both suites. Two anchored halves keep `a` valid for `^a` plus `a$` and let each half say which part failed. Free-form regex was left out: the two dialects differ (lookbehind, named groups, `\d`), and a user pattern would run unbounded in Python `re` (ReDoS).

**Tradeoff:** Case-sensitive only. Python's `$` also matches before a trailing newline where JavaScript's does not; form values are single-line, so this is accepted. A pattern JavaScript rejects (only possible through the API) makes the browser validator skip all pattern rules and note it; the server still enforces them. A warning with the number of items a new constraint would fail is not built (it needs a pattern-evaluating query); stale values never block other edits (changed-keys validation).

---

## Card highlights are one display-only list per item type

**Decision:** An item type chooses up to three fields to show on its cards, stored as an ordered list at the schema root: `x-menagerist.highlights.card: [{ "key": "director" }]`. It changes presentation only: not search, validation, layout or storage. One shared renderer (`node-summary.svelte`, fed by `summaryItems` in `lib/highlights.ts`) serves every surface, and the number of values per surface is one constant table: grid card 2, list card 3, connection picker 1, connection row 2. Each field type declares `highlightable` (text, number, yes/no, date, choice and rating; not long text, table or custom) and may supply a compact `SummaryWidget` or a `formatSummary` (date). `normaliseHighlights` drops dangling, archived, non-highlightable and duplicate keys and anything past three, both when loading and when the editor saves. The backend only checks the list's shape on save (`check_meta_shape`): at most three unique entries, each naming an existing, non-archived property.

**Rationale:** Highlights belong to the type, so every user and item of a type sees the same cards. Deriving the picker and connection rows from the same list avoids per-surface configuration until someone needs it, and keeping the cover and title dominant (guidelines §3.2) explains the lower grid count. Empty values are skipped rather than shown as blanks. Ranks live on the editor field, so reordering survives edits to the field and fields whose key is still pending.

**Tradeoff:** A field that stops being highlightable (its kind changes, or it is archived) silently leaves the list. Other highlight lists, such as the connection details planned for relationship types, are preserved but not validated yet. There is no live card preview in the editor (deferred).

---

## Search reads every text and number value in an item's details

**Decision:** `q` on the item list matches the name, the description and any string or number anywhere inside `attributes` (including table cells and details the type does not define), case-insensitively, as a substring. It never matches field names, booleans or nulls. Per item type it skips archived fields, fields with `x-menagerist.search: false`, and ratings (`search_excluded_keys` in `schema_meta.py`; the frontend descriptors carry `searchable: false` for rating and yes/no). Untyped items are scanned in full. The repository `list` and `count` take an optional `attribute_search_exclusions` (type slug to keys); `ListNodes` builds it from all item types when `q` is set. The query walks the values with `jsonb_path_query` and one clause per type that has exclusions; keys and the pattern are bind parameters. `%`, `_` and the escape character in `q` are now escaped, for the name and description match too. The API is unchanged apart from the description of `q`. The cards show "Matched in Director: Ridley Scott" when the match is not in the name or description (`matchContext`).

**Rationale:** Highlights (WI-16) are display only, so what can be found must not depend on what is shown on a card. Excluding archived fields stops an item matching on a value the user can no longer see. Scanning at query time needs no index to keep in step with schema changes; a maintained search column can replace it later without changing the port.

**Tradeoff:** The scan is sequential, so very large collections may need an index (not measured yet). Results stay in id order, not by relevance. Tags are not searched. The set of non-searchable kinds is a constant on both sides (`NON_SEARCHABLE_KINDS`, `searchable: false`) and must be kept in step. There is no editor control for `search: false` yet.

---

## Per-item details keep their type, order and name rules; only name problems block saving

**Decision:** "Add detail" stays a loose key in `attributes` with the name as the key (a stopgap until the WI-19d overlay). It is made safe: names are trimmed; a blank name with a value, a duplicate name (ignoring case and spaces) and a name equal to any field of the type (removed fields included, ignoring case) are shown as inline errors and disable Save on the item forms. New details can be Text, Number or Yes/No; numbers and yes/no values keep their JSON type, and values the form cannot edit (null, nested values, lists) show read-only as compact JSON and are written back unchanged (rows keep the original in `raw`, `attributesToRows` no longer stringifies). Details are listed alphabetically, ignoring case, because the database does not keep key order. Limits: names up to 100 characters and 50 details per item, applied to details only. The server enforces them for new or changed details in `CreateNode` and `UpdateNode` (`check_custom_details`): a name already stored, or an item already over the limit, does not block other edits.

**Rationale:** Two rows with the same name silently overwrote each other (`Object.fromEntries`) and stringified values corrupted data set through the API, so these problems have to stop the save rather than warn. The guard lives in the application layer, not in `Node`: the domain cannot see which keys the schema defines, and its invariants also run when nodes are loaded from the database, so a limit there would make existing nodes unloadable.

**Tradeoff:** This is an exception to "client-side errors never block Save" (WI-6): only detail-name problems block, because otherwise data is lost silently. Limits are constants (proposals from the spec), not settings. Edge types have no custom details. Details still cannot be highlighted, and the type choice is limited to three types until the overlay lands.

---

## Connections show and edit their own details through a second highlight list

**Decision:** A relationship type's schema gets `x-menagerist.highlights.connection` (at most 2 fields, same rules as the card list: eligible kinds, unique, existing and not archived; the backend checks the shape in `check_meta_shape`). Connection rows on the item page show three single lines: the relationship label, the other item with its own card highlights, and the connection's highlighted details, using the same `node-summary` component with `surface="connection"`. Tapping "Edit connection" opens a sheet that reuses `attributes-editor` over the relationship type's schema and saves with `PATCH /edge/{id}` and its ETag. Removing a connection no longer asks to confirm: it removes at once with a 5-second Undo that re-creates the connection. The relationship type editor gets the same "Show on connection" pin as item types, capped at 2. No backend behaviour changed apart from the shape check.

**Rationale:** The backend already stored, validated and returned connection details; only the UI was missing. Reusing the highlight list, summary component, attribute editor and detail rules keeps one mental model for items and connections (guidelines §16a, §16b, §17), and Undo replaces confirmation for a reversible action (§14).

**Tradeoff:** Undo re-creates the connection, so its id and timestamps change. A row shows both the other item's highlights and the connection's own (open question 51). Adding several connections at once (WI-22b) and typed per-connection extras beyond the type's fields are not built.

---

## A nullable `extra_schema` overlay gives nodes per-item typed fields

**Decision:** Nodes gain a nullable `extra_schema` column (v1: nodes only, not edges), in the same JSON Schema shape as a node type's `attributes_schema` (properties with `x-menagerist`, a `version`, `required`, `layout`). `application/schema_meta.merge_attribute_schemas(type_schema, extra_schema)` combines both into one schema for validation: properties from each side, `required` and `layout` concatenated (type first), and `highlights` left type-only (never merged). `CreateNode`/`UpdateNode` check a given `extra_schema`'s own JSON Schema validity and `x-menagerist` shape (`check_schema_definition`, shared with the node-type and edge-type use cases), then validate `attributes` and check custom-detail limits against the merged schema instead of the type schema alone. A key defined by both schemas is rejected as `InvalidSchemaError`, including a key that is only archived on the type (its slot stays reserved). `extra_schema` follows the existing "`None` on update means unchanged" convention (there is no way to clear it yet, matching `attributes_schema` on a node type).

**Rationale:** Reuses the existing field-type registry, editor components, validation and search unchanged for per-item fields, instead of a parallel typed-field system. `backend-surface.md` scopes WI-19d to "a column and API fields, not a port" - this session is that plumbing. The frontend UI to add typed per-item fields (WI-18b/18c) is separate and builds on this.

**Tradeoff:** No item-page UI yet to create or edit `extra_schema` entries directly; only the API surface exists. WI-17 attribute search does not yet exclude non-searchable overlay fields (for example a per-item rating) the way it does for type fields, since exclusions are computed per type, not per node - left for later. No migration path to remove per-item fields beyond archiving them inside `extra_schema` itself, same as a type schema.

---

## Reusable field and list presets: copy-on-apply with provenance

**Decision:** A new `presets` backend module (own hexagonal layers, no dependency on `graph`) stores saved fields, field groups (`field_set`, "field group" in the UI) and lists (`choice_list`) as `{kind, label, description, definition, version, builtin}`, soft-deletable, with a definition-shape check per kind (`application/preset_definitions.py`). Applying a preset **copies** its definition into the target schema with a fresh key (WI-20) and records `x-menagerist.origin: {preset, version}` on the property; provenance is metadata only and never affects validation. Editing a preset's `definition` bumps `version`, so a copy showing an older version can offer "update available". `field` (a single field, "Save for reuse" from a schema-editor field) and `choice_list` (a set of options, "Save these options as a list" / "Use a saved list" on a choice field, with "Update options" reusing the WI-9/10 in-use warning) are wired up this session; `field_set` is stored and validated but has no save/apply UI yet.

**Rationale:** Copy-on-apply keeps every node type's schema a standalone JSON Schema both validators already understand, so deleting a preset never breaks a type that used it - the alternative, a live link, is parked as a v2 idea (`SyncChoiceList`). The `group` field kind's UI label changes to "Table" (code name unchanged) to free "Field group" for the new reusable-set concept.

**Tradeoff:** No UI yet for saved fields from a custom detail, for field groups (save/apply as a labelled section), for per-item application (needs the WI-19d overlay's own editor), or for packs/import-export/built-ins (WI-19c). These are separate, later items.

---

## Multi-add uses a single `CreateEdges` batch command

**Decision:** `POST /edge/batch` (`CreateEdgesCommand`/`CreateEdges`) connects one source to several targets of the same relationship type in one transaction, sharing the same attributes across every new connection. A target already connected by an edge of that type (in either direction) is skipped, not duplicated, using the same `list_for_node` paging the purge use cases already use. The item page's "Connect item" form becomes a multi-select; on success it shows a count (created, and skipped if any) with a 5-second Undo that deletes the created edges individually.

**Rationale:** The spec calls this out explicitly as structural over convention: N client calls to `POST /edge` would not be atomic and could leave a half-connected state on a partial failure, whereas the batch command commits once. Reusing `list_for_node` for the duplicate check avoids a new repository method.

**Tradeoff:** Undo removes the created edges one at a time (no batch delete exists), best-effort. Creating new items inline from the picker (typing a name that doesn't match anything) is not implemented; only existing items can be selected.

---

## Rank-based matching for kind-less properties (WI-12)

**Decision:** `FieldTypeDescriptor` gained an optional `rank?: (prop) => number`. `descriptorForProp` now picks the highest-ranked descriptor whose `fromSchema` matches an unkinded (API-authored) property, defaulting unranked matches to `1`; ties fall back to registration order. An explicit `x-menagerist.kind` is unaffected - it was, and remains, a direct lookup.

**Rationale:** Correctness no longer depends on import order in `field-types/index.ts`. No current built-in kind actually needs a non-default rank: every scalar's `fromSchema` already excludes the shapes the others claim (checked directly - `text` excludes `format`/`enum`, `date`/`choice` require them, `rating`/`longtext` only ever match an explicit `kind`), so this is infrastructure for the overlapping kinds the spec anticipates (multi-choice, partial date, identifier, URL/email), not a fix for a live bug.

**Tradeoff:** None beyond the small added surface on the descriptor type.

---

## Required-field marker is neutral, not red

**Decision:** In the attributes editor, a required field's asterisk is `text-muted-foreground`, not `text-destructive`. When the field is currently empty, the asterisk is replaced by a small "Recommended" text hint instead. Neither ever blocks saving.

**Rationale:** Required is advisory only (WI-6, guidelines §16a); a red asterisk reads as a validation error even though nothing is actually being validated. Implements open question 58 (owner decision, 2026-09-21), which had been recorded but not yet built.

---

## A table (group) field's column order is stored explicitly

**Decision:** A `group` property's own metadata gains a `columns` member: an ordered array of its sub-property keys, written by `toSchema` from the in-memory sub-field order and read by `fromSchema`, `GroupInput.svelte` and `GroupView.svelte` via a shared `orderedColumns(prop)` helper (`field-types/group/columns.ts`). A property with no `columns` (saved before this fix, or authored through the API) falls back to `Object.entries` order. The backend's `check_meta_shape` validates `columns` is an array of strings, alongside the other property metadata members.

**Rationale:** Verified directly against Postgres: nested JSONB object keys are not stored in insertion order (`{zeta_field, region, a_long_custom_name, aa, k1}` came back as `{aa, k1, region, zeta_field, a_long_custom_name}`), the same reordering WI-18a already found for loose attribute keys. A table field's columns were derived from `Object.entries(prop.items.properties)` with no explicit order recorded anywhere, unlike top-level fields (`x-menagerist.layout`), so a table's column order silently scrambled after any save and reload.

**Tradeoff:** Existing table fields saved before this fix keep their JSONB-scrambled order until re-saved from the schema editor - the same no-migration pattern as every other `x-menagerist` addition.

---

## Quantity field kind, and a general object-valued field fix

**Decision:** A new `quantity` kind stores `{value: number, unit: string}` (e.g. "180 g"), matched only by its explicit `x-menagerist.kind` (shape alone isn't distinctive). Not a group sub-field in v1 - a table cell is a plain string, not an object, so nesting needs a second follow-up. Getting there required widening `AttributeRow.value` to `string | GroupRow[] | GroupRow` and giving `attributesToRows` an optional `schema` argument: a key the schema defines as `type: 'object'` now hydrates as an editable flat row instead of falling into the generic read-only-JSON branch; `rowsToAttributes` gained the matching write-back branch. A composite sub-value follows the same blank-handling as a group cell (a blank number/date/enum sub-value is omitted, a blank text sub-value like `unit` is kept); the whole field is omitted only when every raw sub-value was blank to begin with.

**Rationale:** This is exactly the prerequisite the candidate `location` kind was already waiting on (`further-field-types.md`), so quantity unblocks it too. Matching only the explicit kind avoids a future kind colliding on the same `type: 'object'` shape.

**Tradeoff:** Group column reordering (WI-23) landed alongside this: `GroupExtras.svelte` gained up/down buttons per sub-field, using the `x-menagerist.columns` order the group column-order fix already writes - no further storage change needed.

---

## Per-item custom fields moved from a loose, untyped stopgap to the typed `extra_schema` overlay

**Decision:** "Add detail" (WI-18a's Text/Number/Yes-No loose-key stopgap) is retired, not deprecated - deleted (`lib/attribute-rows.ts`'s `extra`/`newDetailRow`, `lib/custom-details.ts`, `application/custom_details.py`, all gone). Per-item extras are now typed fields in the node's `extra_schema` overlay (WI-19d), created through the same Name + Kind flow the schema editor uses (`FieldKindRow.svelte`, extracted from `schema-editor.svelte`'s field-creation row), for both typed and untyped nodes. WI-18c (adopt-across-items, `ListNodeTypeCustomAttributes`/`AdoptNodeTypeCustomAttribute`) is dropped entirely - there is no loose-key data left to adopt. Edges also lose ad-hoc fields (the overlay is nodes-only in v1); a connection can only use fields its relationship type's schema defines.

**Promotion:** WI-18b becomes `PromoteExtraSchemaField` (`application/promote_extra_schema_field.py`) - a pure move of a property from a node's overlay onto its item type's schema, in one transaction via `JoinedUnitOfWork` (composing `UpdateNodeType` and `UpdateNode`, the same pattern `upload_and_attach_media.py` uses). No value coercion is needed, since the value already satisfied the property's schema as an overlay field.

**Rationale:** The stopgap could not support constrained or typed kinds (rating, date, choice, quantity, table, constrained text) without duplicating validation logic the registry and backend schema validation already own - exactly the gap `decisions.md` already flagged it as ("a stopgap"). Since this is a pre-release application with no real user data, there was nothing to migrate, so the simpler, architecturally-correct path (typed overlay everywhere) was taken directly instead of building a bridge from the old model.

**Found along the way:** `UpdateNodeCommand.extra_schema=None` means "leave unchanged" (the same convention as `attributes_schema` on a node type), so a node's overlay can never actually be cleared to empty by sending `null` - both `PromoteExtraSchemaField` and `attributes-editor.svelte`'s "remove the last overlay field" path always write a real `{"properties": {}}` object instead, never `null`, so the clearing write actually takes effect. This is a latent, pre-existing gap in the `None`-means-unchanged convention itself (not something this change introduced), worth a proper fix (e.g. a sentinel) if a future session needs to clear other optional fields on this command the same way.

**Tradeoff:** No label-length cap on overlay fields (only a schema field's ordinary `title`, unlike the old 100-character detail-name limit) - an intentional asymmetry removed, since the key is now slug-generated (WI-20), not the label itself. The 50-fields-per-item count limit carries over (`MAX_EXTRA_SCHEMA_FIELDS`).

---

## Rating colour is a per-field display option; kind changes that drop a highlight now say so

**Decision:** Rating gained a second display option, `display: 'amber' | 'accent'` (default `amber`), read by `RatingInput`/`RatingView`/`RatingSummary` via a shared `filledStarClass(prop)` helper (`field-types/rating/colour.ts`). Closes open question 6 (was undecided between a fixed colour and the theme accent - the owner wants amber to stay the default but be overridable per field).

Separately, `schema-editor.svelte`'s `handleFieldRowChange` now toasts ("No longer shown on cards" / "...on connections", matching whichever `highlightList` the editor is in) when a kind change makes a currently-highlighted field non-highlightable, instead of dropping the pin silently. Closes open question 65.

**Rationale:** Both were small, low-risk additions to existing mechanisms (the generic `displayOptions`/`meta.display` plumbing already used by boolean and choice; the existing toast pattern already used elsewhere in the same file for archive/remove/purge actions) rather than new UI surface.

---

## Field-row icon crowding, invalid-field styling, and overlay-field distinction (open questions 73, 74, 75)

**Decision (73, revised same session):** an earlier pass in this session closed 73 as "keep everything always-visible" (no precedent for an alternative existed yet). The owner overruled that as too cluttered and asked for a proper overflow control that works well on mobile. Landed: pin/highlight and remove stay standalone (most frequent actions); "Replace field" and "Save field for reuse" move into a `MoreVertical` kebab menu using a newly-scaffolded `dropdown-menu` component (`frontend/src/lib/components/ui/dropdown-menu/`, via `npx shadcn-svelte add dropdown-menu` - built on `bits-ui`, already a dependency, so no new package). A kebab was chosen over a settings-cog icon (the owner's other suggestion) because a cog conventionally signals "configuration," not "actions on this item"; bits-ui's menu handles touch/keyboard/positioning itself, meeting the mobile requirement without extra work. This is the first use of a dropdown menu anywhere in the app - a real precedent now exists for the next row-action question.

**Decision (74):** `attributes-editor.svelte`'s `fieldEntry` snippet now wraps the widget/input in a `ring-destructive/60` ring (150ms transition, §22's "state change" bucket) whenever the field has an error, and sets `aria-invalid` on the plain-text `Input` fallback. Deliberately no shake or other one-off animation - matches §16a's soft, non-alarming tone already established for required-field feedback. `aria-invalid` is not threaded into the per-kind `Widget` components (rating, choice, date, ...), since each has its own prop contract; left for later if wanted.

**Decision (75):** Per-item overlay fields (WI-19d's `extra_schema`) get a small "Per-item" badge next to the label in `attributes-editor.svelte`, reusing the opaque-field "custom" badge styling from `field-kind-row.svelte` for visual consistency. Node-type fields get no badge (the implicit, default case). Per-item custom details no longer exist to distinguish (retired by the WI-18 revision), so this only separates the two kinds that remain.

**Rationale:** All three were reviewed together since they're all about the same underlying pressure (the field row accumulating more distinct pieces of information and actions as the spec has grown); 74 and 75 got small, additive visual treatments reusing existing styles, while 73 stayed as-is rather than trading a real crowding problem for a bigger, unproven interaction pattern.

---

## Weak ETags to survive a compressing proxy (open question 76)

**Decision:** `shared_kernel/etag.py`'s `etag_from_entity` now emits weak ETags (`W/"<digest>"`), not strong ones. `ConditionalRequest.check_get`/`check_patch` (`entrypoints/api/shared/http/conditional_request.py`) compare `If-None-Match`/`If-Match` against the current ETag with a leading `W/` stripped from both sides first, so a weak and a strong form of the same underlying tag are treated as equal.

**Root cause (found from live Network-tab evidence, not guessed):** `frontend/nginx.conf` gzip-compresses `/api/` JSON responses. Something in the proxy chain in front of the backend rewrites a *strong* ETag to a *weak* one whenever the response it's attached to actually gets compressed (confirmed directly: a 412 response, which has no body and so is never gzipped, kept the backend's original strong ETag untouched; the very next 200, which did have `content-encoding: gzip`, carried a weak one). The frontend's ETag cache correctly stores whatever the response actually said - the weakened value - so the following PATCH's `If-Match` carried that weakened form, while the backend recomputed a fresh strong ETag and did a strict string comparison against it. Mismatch, every time a save followed a compressed GET, which is normal browser behaviour - hence "the first save always fails, the second always succeeds" (the 412 response clears the client's cache, so the retry sends no `If-Match` at all and the conditional check is skipped).

**Rationale:** Weak validators are specified to survive exactly this kind of representation change (RFC 7232 §2.1) - emitting one ourselves from the start makes a downstream rewrite a no-op instead of a footgun. The comparison-side tolerance is defence in depth in case some other layer someday does the reverse (adds a `W/` that wasn't there) or a client normalises it away.

**Not investigated:** which specific layer (nginx itself, or something between it and the public domain) performs the rewrite - the fix doesn't depend on knowing, and chasing it further across infrastructure outside this repo wasn't worth it once the fix was clear.

---

## Media gallery re-skinned on shadcn-svelte's Attachment component; NativeSelect over the custom Select

**Decision:** `media-gallery.svelte`'s hand-rolled square-tile grid (black-overlay hover actions on plain `<img>`/`<div>` tiles) is replaced with shadcn-svelte's `Attachment` component (`ui/attachment/`, scaffolded via `npx shadcn-svelte add attachment`), following the structure of its own docs examples (`attachment-image.svelte`, `attachment-states.svelte`) rather than inventing a bespoke usage: images render as `orientation="vertical"` media cards in the existing `grid-cols-3 sm:grid-cols-4` grid; everything else (PDFs, docs, ...) renders as smaller `size="sm"` `orientation="horizontal"` rows in a list below, per the owner's explicit split. Upload progress now uses `Attachment`'s real `state` prop (`uploading`/`error`/`done`) instead of a hand-rolled spinner div, with a scaffolded `Spinner` component (`ui/spinner/`, also from the docs' own `attachment-states`/`attachment-demo` examples) for the in-flight icon. All existing behaviour is preserved exactly: rename (inline, Enter/Escape), cover set/unset (images only), download, and the two-step delete confirm - now as an icon swap within `Attachment.Actions` rather than a floating black-overlay column.

Separately, `field-kind-row.svelte`/`GroupExtras.svelte`'s three dropdowns (field kind, display option, group sub-field kind) ended up on `NativeSelect` (`ui/native-select/`), not the custom `Select` scaffolded earlier the same session - `NativeSelect` is a themed wrapper around a real `<select>`/`<option>`, giving the requested "prettier" shadcn styling while keeping the OS-native picker on mobile (the concern that prompted reconsidering `Select`). The unused `ui/select/` scaffold was removed since nothing references it once the swap landed.

**Also resolved this session:** the owner asked about a `marker` component seen in the shadcn-svelte registry; it's an inline status/event-log line (icon + short text, built for chat/agent-timeline UIs - see `marker-demo.svelte` upstream), not a map marker, and doesn't fit anything in Menagerist's UI. Left uninstalled.

**Rationale:** Matching the docs' own example structure (namespace import `import * as Attachment from ...`, `Attachment.Root`/`.Media`/`.Content`/`.Title`/`.Description`/`.Actions`/`.Action`/`.Trigger`) rather than a custom composition keeps the component upgradable and consistent with how `Card`/`Dialog`/`DropdownMenu` are already imported elsewhere in this codebase. `NativeSelect` over `Select` for the three schema-editor dropdowns was a direct, explicit trade-off call by the owner after being shown both options' mobile implications.

---

## Single-image deployment: one `menagerist` container, not `menagerist-backend` + `menagerist-frontend` behind nginx

**Decision:** There is one published image, `menagerist`. The FastAPI process serves the built SvelteKit SPA itself (`entrypoints/api/spa.py`, a `StaticFiles` subclass mounted at `/` after every API router) instead of a separate nginx container proxying to the backend. `frontend_dist_path` (`MENAGERIST_API_FRONTEND_DIST_PATH`) controls it: set, the process serves the SPA alongside the API; unset (the default for local `poe serve-backend` dev), it's API-only. The root `Dockerfile` builds both in one multi-stage build - a Python stage that also dumps the OpenAPI schema (`menagerist schema dump`), a Node stage that generates the typed client from that schema and builds the SPA, and a distroless runtime stage with both outputs. `docker-bake.hcl` has one `menagerist` target (plus `local`, its single-platform `type=docker` variant for `poe docker-build`); `compose.yaml` runs Postgres plus one `menagerist` service (`serve --host 0.0.0.0 --migrate`, exposed on `8080:8000`).

**Rationale:** Nothing had been published yet, so there was no compatibility cost to dropping the split. A reverse proxy in front of a single backend process earns its keep when it terminates TLS, load-balances across replicas, or fronts more than one origin - Menagerist is single-process and self-hosted behind whatever the operator already puts in front of it (their own reverse proxy, a tunnel, or nothing). Running nginx purely to serve a handful of static files and forward `/api/*` added a second container, a second set of security headers to keep in sync with the backend's `SecurityHeadersMiddleware`, a duplicate 10 MB upload cap that silently disagreed with the backend's real 100 MB limit, and a second image to build, scan, and version. `SpaStaticFiles` reproduces nginx's behaviour exactly (hashed `_app/immutable/*` cached a year, other files an hour, missing asset-like paths 404 instead of falling back to the shell, dotfiles hidden except `.well-known`, `/favicon.ico` → `/favicon.svg`, the SPA shell never cached) and mirrors `frontend/nginx.conf` line for line - no serving behaviour changed, only where it runs (the same OS process as the API, not a separate container). `serve --migrate` folds the standalone `migrate` compose service into the app's own startup for single-instance deployments; multi-instance deployments still run `migrate upgrade` as a separate step.

**Tradeoff:** The image is CPU/framework-coupled to Python for something that's pure static file serving - nginx would out-perform it under heavy static-asset load. Not a concern at Menagerist's scale (self-hosted, single operator, no CDN-scale traffic). If that changes, the split can come back; `frontend_dist_path` being a plain setting (not baked into the app's structure) keeps that reversible.

---

## Quantity and choice as table sub-fields; usage/purge extended to group sub-keys

**Decision:** `quantity` and `choice` are now `canBeSubField: true` (a table column can be a quantity or a choice, not just text/number/boolean/date/rating). Backend `count_with_attribute`/`list_with_attribute` (both `NodeRepository` and `EdgeRepository`, SQLAlchemy and in-memory adapters) and the `Count/PurgeNodeTypeAttributeUsage`/`Count/PurgeEdgeTypeAttributeUsage` use cases and their routes take an optional `sub_key`: with it, `key` names a group array and matching/purging happens per row (via `jsonb_array_elements`, not a hand-built JSON path string) instead of against the top-level value. Frontend: removing a choice columns option is advisory (remove immediately, warn after if in use - WI-10 style); removing a column itself queries usage first and requires confirming if any items hold it (WI-9 style) - but a removed column has no archive/restore step, since none existed for columns before this either; confirming is the permanent action, there is no separate purge call.

**Rationale:** The owner asked for parity with the existing top-level field in-use checks when making more types nestable, rather than adding new types silently and leaving column removal unchecked. Building full archive/Undo/"Removed columns" infrastructure for table columns (mirroring WI-8 exactly) was explicitly scoped out as bigger than needed; a confirm-before-delete gate keeps the safety property (no silent data loss) without a second archive-restore surface.

---

## Ordered list (`list`) and checklist (`checklist`) field types

**Decision:** Two new field kinds. `list` stores a plain array of free-text strings with a purely cosmetic `display: numbered|bulleted` "Show as" option (storage unaffected either way). `checklist` stores an array of `{text, done}` objects, with a real, persisted boolean tick per item. Checklist is not a `list` display variant: `list`'s display option is designed to never change storage, and a tick is real data, not a rendering choice, so it needed its own kind and its own stored shape. Both are `canBeSubField: false`, not highlightable, matched only by an explicit `x-menagerist.kind` (never inferred from shape alone), and need no `x-menagerist.columns`-style ordering bookkeeping (JSONB array order survives a save/reload for free; only object-key order needs it).

**Rationale:** The owner asked directly for an ordered-list kind (already a documented but unscheduled candidate in `further-field-types.md`), then separately asked for a checklist while discussing list display styles. A first instinct to fold checklist in as a third `display` value on `list` was rejected: that option only ever controls presentation in this codebase (boolean's switch/checkbox/buttons behave identically), and overloading it with a storage-shape change would break that invariant for every future reader of the code. `attributesToRows` must check the schema's declared `checklist` kind before its existing generic array-of-objects fallback (shared with `group`'s untyped-key catch-all) - otherwise a checklist's boolean `done` silently degrades through the group cell coercion path built for arbitrary string-typed table columns, always producing `false`. A regression test locks this ordering in (`attributes-editor.test.ts`).

See `docs/field-types-spec/wi-25-ordered-list-and-checklist-field-types.md` for full implementation notes.

---

## Bugfix: a quantity's read-mode display showed only the unit

**Bug (user-reported):** A quantity field's read-mode rendering (the item detail page, and a quantity table column) showed only the unit (e.g. "g"), dropping the numeric value entirely.

**Root cause:** `quantityText` (`field-types/quantity/format.ts`) only accepted a JS `number` for `value`. Every read-mode caller reaches it through `attributesToRows`, which stringifies every sub-value of an object-typed field for editing (so a stored `180` arrives as the string `"180"`) - `typeof value === 'number'` was therefore always false for that path, silently dropping the numeric part while the unit (a string already) passed through untouched.

**Fix:** `quantityText` now also accepts a numeric string, converting it with `Number(...)` and validating with `isNaN`. Covered by new cases in `quantity.test.ts`.

---

## Hybrid Tooltip/Popover for touch devices; `date-fns` for relative time

**Decision (tooltip):** New `ui/popover-tooltip/` component (`Root`/`Trigger`/`Content`, same shape as `ui/tooltip` and `ui/popover`): at runtime, `MediaQuery('any-hover: none')` (from `svelte/reactivity`) picks `Popover` (tap-to-open) on a touch device or `Tooltip` (hover-to-open) otherwise, so call sites don't change. Both real usages (`node-summary.svelte`'s card-highlight tooltips, the item detail page's "Added/Updated X ago" timestamps) now import this instead of the plain `Tooltip`.

**Root cause:** confirmed directly in the installed `bits-ui` (2.19.0) source, not just from the upstream shadcn-svelte issue's age: `Tooltip`'s `pointerenter`/`pointermove` handlers explicitly bail on `e.pointerType === 'touch'`, and `pointerdown`/`click` only ever close it, never open it. Combined with this app's `tabindex="-1"` on both trigger spans, these two tooltips were completely unreachable on a touch device, not merely awkward.

**Rationale:** matches the community-vetted fix from the linked upstream issue (huntabyte/shadcn-svelte#1044) - a maintainer-suggested "conditional check of which device a user is on and swapping between `Tooltip` & `Popover`" - adapted to this repo's own themed wrapper components (self-closing pass-throughs, like every other `ui/` primitive here) rather than the community snippet's slightly more verbose re-render pattern, which is unnecessary once `child`/`children` already flow through via prop spreading the way every other wrapper in this codebase already relies on.

**Decision (relative time):** `formatRelativeTime` (`lib/format-date.ts`) now uses `date-fns`'s `formatDistance(date, now, { addSuffix: true })` instead of a hand-rolled `Intl.RelativeTimeFormat` walk over fixed unit thresholds. Its "Just now" special-case for sub-45-second differences was removed on request; the function now returns exactly what `date-fns` produces at every threshold (e.g. "less than a minute ago"), no override layer on top.

**Rationale:** requested directly, for `date-fns`'s more conversational wording ("about 2 hours ago", "over 1 year ago") than a bare numeric `Intl.RelativeTimeFormat` count. English-only was an explicit, deliberate trade-off (confirmed with the owner): the previous implementation auto-localised via `Intl.RelativeTimeFormat(undefined, ...)`, which `date-fns` does not do out of the box (would need per-locale imports wired to the browser's detected language) - not worth it for a self-hosted personal app.

---

## Kind-change matrix entry for `quantity`; field groups (WI-19b, scoped)

**Decision (kind-change matrix):** `kind-changes.ts`'s `ALLOWED` map now lists `quantity: ['quantity']` explicitly, matching `group`'s existing self-only entry. Behaviour is unchanged (`allowedKinds` already fell back to `[original]` for any kind missing from the map), but every other kind is listed explicitly there and `quantity`'s omission read as an oversight rather than a deliberate choice. `choice` already had an entry (`['choice', ...TO_TEXT]`) from WI-15/WI-10; only `quantity` was missing.

**Rationale:** `quantity`'s stored value is an object (`{value, unit}`), not a scalar, the same reason `group` is self-only - switching it to `text` would leave a stored object under a `type: 'string'` schema until the value itself was re-entered, unlike a genuine number-to-text widening.

**Decision (WI-19b, field groups):** Implemented the "field groups" half of WI-19b - saving a schema editor section as a `field_set` preset ("Save field group for reuse"), inserting one into a node type's schema as a new labelled section ("Add saved field group…" in `schema-editor.svelte`), the `settings/saved-fields` "Field groups" listing (was a placeholder), and applying a field group ad hoc to a single item's `extra_schema` overlay ("Add saved field group…" in `attributes-editor.svelte`, alongside "Add field"). `$lib/presets.ts` gained `fieldSetToDefinition`/`definitionToFieldSet`; `SavePresetDialog`'s `kind` prop widened to include `field_set`. No backend change was needed - the `presets` module (WI-19a) already stores and validates all three preset kinds generically.

**Scoped out of this session, left for later (see `wi-19-presets.md`'s WI-19b bullets):**
- **"Add these to `<item type>` instead"** when applying a field group ad hoc - not built as a bulk action. The existing per-field "Make this a field" action (promotes one overlay field to the node type at a time, already shipped) covers the same end state one field at a time; a type author can also use the schema editor's own "Add saved field group…" directly. A dedicated bulk-promote endpoint was judged more than this session's scope justified without a way to exercise it end to end in this sandbox (see the environment note below).
- **"Copy details from another item"** (copy another item's overlay field *names*, not values, into the current item) - needs a new item-picker UI (search across nodes, ideally of the same type) that doesn't exist yet in a reusable form; the closest precedent (the item page's multi-select connection picker) loads all nodes client-side and is specific to that flow. Not started.

**Environment note:** frontend client codegen (`poe generate-frontend-client`) could not be run in this sandbox - the backend CLI fails at import time under the container's Python 3.14.0rc2 with a pydantic/typing incompatibility inside `pydantic`'s own 3.14 forward-compat shim (unrelated to this repo's code; `app.shared_kernel.cqrs.UseCase`'s `TYPE_CHECKING`-only `Actor` import confirms the codebase is intentionally written for 3.14's lazy annotation evaluation, so downgrading the interpreter isn't a fix either). Verified instead with a local, un-committed stub of `src/lib/api/generated/` (that directory is gitignored) sufficient to run `eslint`, `prettier` and the full `vitest` suite (300/300 pre-existing tests still pass; the two ETag-interceptor test files were excluded, since they assert on the stub's necessarily-fake HTTP behaviour, not on anything this session changed). `svelte-check` was not clean, but every error traced to the stub's loose typing (`any`/`never` on response shapes it can't know), not to real code - none were inside a file this session touched. Regenerate the real client and re-run `poe check` before trusting this fully.

## Keyboard shortcuts: one registry, one listener, guarded by target

**Decision:** Shortcuts go through a single registry (`frontend/src/lib/shortcuts.svelte.ts`) that components register into and out of via `$effect`. The root layout attaches **one** long-lived `keydown` listener (`attachShortcuts`) built on [tinykeys](https://github.com/jamiebuilds/tinykeys) v4, which reads the registry at key-press time. The help overlay (`?`) renders whatever is registered. Shipped set: `g c` / `g s` / `g e` (navigate), `n` and `Cmd/Ctrl+K` (quick capture), `/` (search, from any page), `?` (help), and on an item `e` / `Esc` / `Cmd/Ctrl+S`; plus arrow-key movement between text cells in table (group) fields.

**Rationale (why not the design in the plan):** the plan's registry kept the list in `$state` and rebuilt the tinykeys binding map in a root `$effect`. Browser e2e runs showed that was unsound, in three ways the unit tests could not see:
- `$state` deep-proxies stored objects, so `filter((d) => d !== def)` compared a proxy with the raw object and never unregistered anything; and reading `active` inside each caller's `$effect` made every registering effect depend on the registry, so effects re-ran each other in an endless loop that froze the app.
- Using `$state.raw` and `untrack` fixed the loop, but a read-modify-write of state inside effect *cleanups* still returned a stale value within a flush, so a cleanup overwrote a registration made moments earlier (after `Esc` cancelled an edit, `e` stopped working).
- Rebinding tinykeys on every registry change also reset its pending-sequence state, so a half-typed `g` could be lost.

So a plain private array is the source of truth, `active` is a write-only `$state.raw` snapshot for the help dialog, and the single listener needs no reactive dependencies. Rule of thumb: do not read-modify-write Svelte state from effect cleanups.

**Guards** (all in the registry, so every shortcut gets them): skip when the target is an input, textarea, select or contenteditable; skip when the target is inside a dialog, alertdialog, listbox or menu; skip when `event.defaultPrevented` (bits-ui's escape layer prevents default on `document` before our `window` listener runs, so without this `Esc` closing an overlay also cancelled the edit underneath); `allowInInputs` opts a shortcut out of the first two. tinykeys' own default `ignore` drops every form-element event, which would have made `allowInInputs` dead, so a custom `ignore` keeps only repeat and IME-composition filtering.

**Layout-dependent keys:** tinykeys rejects an event with a held modifier the binding does not declare, so `?` and `/` are registered as `[Shift]+?` and `[Shift]+/` (optional Shift). `formatKeys` hides the optional part in the overlay.

**Cross-page search:** `/` off the items list navigates to `/items?search=1`, which the list page turns into a focus. That page now clears the parameter with `goto(..., { replaceState: true })`; the previous raw `history.replaceState` discarded SvelteKit's history state and broke the Back button.

**Update 2026-10-08:** `/` now opens the global search popup (`lib/components/search-palette.svelte`, opened through `searchPaletteController`) from every page, including the items list, so `?search=1` is gone. The popup's "See all results in Items" row goes to `/items?q=...`; the items page applies `q` (trimmed, capped at 200 characters) to its search box and then removes it from the URL, so the same link works again later. Separately, tinykeys stops at the first completed binding and leaves the other bindings half-matched, so a stale `g e` swallowed the next `g` once nothing rebuilt the handler between navigations (earlier, page-level registrations masked this). `attachShortcuts` now rebuilds the handler after any binding fires; `tests/shortcuts.test.ts` and an e2e test cover back-to-back sequences.

**e2e tooling changes made along the way:** the Playwright suite now starts its own servers on ports 8100/5273 (`E2E_BACKEND_PORT` / `E2E_FRONTEND_PORT`; the Vite proxy target is `MENAGERIST_API_PROXY_TARGET`) instead of 8000/5173. With the old ports Playwright reused, or collided with, any dev or deployed stack already on 8000 - the latter would have written test data into a real database. The default test timeout is 60s because cold Vite starts made the first multi-step spec time out. `poe sync` now downloads Chromium (`install-e2e-browser`); Linux system libraries are a one-off `sudo` step that `poe install-e2e-deps` prints rather than runs (`sudo` cannot prompt from inside `poe`, and resets `PATH` to root's older Node).

**Known gaps, deferred:** number-type table cells report no caret position, so `ArrowLeft` always leaves them and `ArrowRight` never does; an arrow key is swallowed when the destination cell has no `<input>` (choice, date, rating); the save e2e test hard-codes `Control+s`, so it fails on macOS (`ControlOrMeta+s` would fix it); the Vitest config cannot run `$effect`, so the registry's effect behaviour is covered only by the e2e suite.

## Mobile navigation: Search replaces Explore

**Update 2026-10-08:** Explore is only a "Coming soon" placeholder, so Search replaced it as the fifth entry of the mobile bottom bar (a button that opens the search popup, shown active while it is open) and Explore left the desktop top navigation too. The `/explore` route and the `g e` shortcut stay; Explore returns to the navigation when the connections map exists. The desktop header keeps its search icon button.

## Versioning preset definitions per kind, not the pack envelope

**Decision:** Each preset definition carries its own schema number (for example `"schema": 2` inside `definition`). Import and reads run an upgrade chain (v1 to v2, and so on) before validation. A data migration rewrites stored rows when a kind's shape changes. The pack envelope `version` (`PACK_VERSION`) changes only when the envelope itself changes, so a new list shape doesn't bump it.

**Rationale:** A pack holds presets of several kinds, and each kind's shape can change on its own. Bumping the envelope for a single kind would reject every pack that still uses the other kinds, and the import checks the whole pack first. Per-definition numbers also let old exports keep importing after a change.

**Not built yet:** no kind has changed shape, so the upgrade chain and the fixture of an old pack are deferred until the first change. When it lands, add the fixture to the pack tests, and keep the upgrade functions next to `preset_definitions.py`.


## One shared data file for ISO countries and currencies, generated by a script

**Decision:** `shared/data/iso-data.json` is the only copy of the ISO 3166-1 countries and ISO 4217 currencies. `scripts/generate_iso_data.py` (PEP 723 inline metadata, `pycountry` pinned) regenerates it through `poe generate-iso-data`. The backend reads it at migration time, and the frontend imports it through the `$shared` alias. The Dockerfile copies `shared/` into both builds.

**Rationale:** the Docker backend build copies only `backend/`, so data kept under `backend/` could not be read by the frontend (and the reverse), and a copy inside each tree would drift. `pycountry` as a runtime dependency added about 21 MB to the image for roughly 60 KB of data, so it runs only as a generator. X-prefixed currency codes are excluded, because ISO 4217 reserves them for metals, funds and "no currency". The app-local currencies GPL and ZRU are added to the generated file with `add_entry`, so the frontend has one list.

**Consequence:** currency names follow ISO (for example "Pound Sterling"). A seeded list does not update on databases that already ran its migration.

## Live-linked choice lists (backend first)

**Decision:** a choice field can reference a saved choice list by id (`x-menagerist.list`) rather than copying its options. Writes strip `enum` from referencing fields and refuse unknown references. Reads and validation resolve the options from the list. A referenced list cannot be deleted while in use; that guard is not built yet.

**Rationale:** copying a large list such as Countries into every field that uses it stores hundreds of strings per field, and a later edit to the list never reaches those copies. Resolution happens in the use case, outside the unit of work, through a graph-owned port, so `graph` never imports `presets` and the architecture rules still hold. A missing list at read time leaves the field unconstrained rather than blocking every save. Writes are strict, so the case should not arise.

**Not decided:** how an exported node-type pack carries referenced lists (inline the options, or ship the list with the pack).

## Built-in presets are hidden on request, not removed

**Decision:** built-in presets stay in the database and in every picker. A "Show built-in" toggle hides them on the settings page and in the picker. The choice is stored per browser in `localStorage`.

**Rationale:** the built-ins are the only example content a new user has, so they must stay available, but they crowd the screen once a user has their own. A server-side setting would be per instance, and this is a per-viewer preference.

## Example packs: an `examples` module, not the presets format or a `source_pack` column

**Decision:** optional example packs (item types, connection types, items, connections and presets) live in their own `examples` module. A pack is a JSON file shipped inside the module (`modules/examples/packs/`, listed by `index.json`). Installing records every entity it creates in an `example_installations` row, so removal knows exactly what the pack owns.

**Rationale:** the presets pack format describes reusable field definitions, not items and connections between them. A `source_pack` column on nodes and types would touch every table, and every query that lists them, to answer a question only one screen asks. The module owns its own ports (`PresetTarget`, `GraphTarget`) and never imports `graph` or `presets`; the adapters that call the real use cases sit in `entrypoints/api/shared/bridges/example_targets.py`, beside `preset_usage.py`.

**Consequence:** the packs are package data, not content in `shared/`, which is only for files both the backend and the frontend read.

## Example install is per-module commits with compensation, not one transaction

**Decision:** installing is an ordered list of steps (presets, connection types, item types, items, connections). Each step goes through the real use case of the module that owns the entity, commits on its own, and is recorded in the installation straight away. If a step fails, the installation is marked failed and everything already created is removed again.

**Rationale:** `graph` and `presets` each own their unit of work, and bounded contexts accept eventual consistency rather than a cross-module transaction (see ARCHITECTURE.md). Recording each entity as it is created means a crash part-way leaves a record of exactly what to clean up. Modelling install as a list of steps also lets media (example images) become another step later without reshaping the use case.

## Removing examples keeps anything the user has touched

**Decision:** an installed entity records a content hash. Removal runs in reverse order and, per entity, applies the first matching rule: already gone, edited since install (hash differs), carries the user's own data (connections or files), still in use by something the pack did not create, otherwise remove. Anything kept is reported with its reason. A preset that existed before the install is never owned by it.

**Rationale:** people explore by editing and connecting examples. Silently deleting something they changed would destroy their work, and keeping everything would defeat "remove them when you're ready". A hash compares what is stored with what the pack wrote without needing an `edited` flag on every entity.

**Consequence:** anything kept also keeps the item types it uses. This applies equally to an edited item or an edited collection (which keeps all its example items). Reinstalling used to be refused because of this; see the update below.

**Update (2026-10-09):** reinstalling re-adopts what the pack kept, instead of refusing (409) or duplicating. The installer walks the pack's installations newest first; for each kind and ref the newest record decides, and it is adoptable only if that record was kept (a later removed or owned record supersedes older ones). It is adopted only if the entity still exists and, for item and relationship types, still has the slug the pack specifies. Otherwise it is created fresh, and a slug taken by something that is not a kept example is still a 409. An adopted entity is recorded as owned by the new installation with the original content hash from the kept record, not its current content: adoption never reduces protection, so an edited item still reads as edited and is kept again on the next removal. The install result reports `adopted` beside `created`, and a failed install rolls back by the same hash rule, so adopted edits survive it. Known limit: an adopted collection is left as the user has it, so items created afresh on this install are not added to it.

**Update (2026-10-08):** an item on a live collection is kept for the same "user data" reason, so the reason now reads "has your connections, files or collections". Installs recorded before this keep the old wording, which the frontend still maps.

## The application owns every constraint; database indexes are backstops

**Decision:** type slugs are unique among live types through a partial unique index (`WHERE deleted_at IS NULL`), and the use cases check the same rule before writing. A soft-deleted type's slug can be reused.

**Rationale:** with soft delete everywhere, a plain unique index made removing and re-adding examples fail on the deleted row's slug. The domain and application layers must reject bad input with a useful message; the database index only catches what slips past, and must agree with the application's rule.

## First-run link to examples, no wizard

**Decision:** an empty Home shows one primary button (add your first item) and a small text link, "Or look around with some examples", to Settings > Examples. While examples are installed, Home shows a dismissible line saying so. There is no onboarding wizard.

**Rationale:** the product problem is that people cannot tell what Menagerist is for until they see connected items, so the way to examples must be visible at first run. A wizard would put a decision in front of someone who has not seen anything yet, and the link keeps a single primary action (DESIGN_GUIDELINES sections 3.5 and 3.6).

## A generic bundle layer for import and export is deliberately not built yet

**Decision:** example packs have their own format and installer. A shared bundle layer for importing and exporting items, collections and types (the same format for examples and for user data) is a planned later phase, not part of this work.

**Rationale:** there is one consumer today. The merge policy (what happens when an imported slug or item already exists) and how an export refers to its own entities would both be guesses. When import and export arrive, the pack format's local `ref`s and the installer's ordered steps are the intended starting point.

**Not decided:** whether add-on packs that need another pack (`requires`) become part of that bundle layer.

## Collections are named lists of items, in their own module

**Decision:** a collection is a first-class entity, not an item. It has a name, a slug, an optional description and an owner, and it refers to items by id: an item can be in any number of collections, and deleting a collection never deletes or changes items. It lives in its own `collections` module. Only manual collections are built; the `kind` field leaves room for dynamic ones (a saved search, #190), which wait until search can filter on more than type, text and favourite.

**Rationale:** modelling a collection as an item with "contains" connections would put one more concept into every list, search and type picker, and a person grouping their vinyl does not want a record. A folder that items live in was rejected: it would force each item into one place and tie type and fields to the folder. `graph` already holds four concepts, and the ownership and visibility rules apply to collections in ways they do not apply to items, so they belong in a module of their own.

**Consequence:** a collection's page reuses the item cards, the search box, the list and grid views and the Examples filter, but not the items page's type filter (yet). It deliberately does not share its list code with the items page. Collections are shown to people as "collection"; the words "shelf", node, edge and graph do not appear.

## Collection membership is by id, and liveness is checked when reading

**Decision:** a membership row stores a collection id, an item id and when it was added, with no foreign key to items. Deleting an item leaves its rows alone. Every read goes through an `ItemLookup` port that returns which of a set of ids are live items, so counts and lists ignore deleted ones.

**Rationale:** modules reference each other by id and accept eventual consistency, so `collections` cannot cascade into `graph`'s tables, and item deletion needs no cleanup step that could be forgotten. The cost is one extra lookup per collection when counting, which is chunked and cheap at the sizes expected.

## Two ports and one filter join collections and items

**Decision:** `collections` never imports `graph`, and `graph` never imports `collections` (architecture tests enforce both directions). `collections` owns `ItemLookup`; `graph` owns `CollectionMembers`, used by the `?collection=<id>` filter on the item list. Adapters for both live in `entrypoints/api/shared/bridges/`, which may import both modules. The filter passes the member ids to the item query as an `ids` restriction, so the search, type and favourite filters, paging and the total all work unchanged.

**Rationale:** the same pattern as `examples` and the choice-list source. A missing or deleted collection is a 404, so an empty collection (an empty list, total 0) is distinguishable from a wrong id.

**Consequence:** the ids go into an `IN (...)` list, which is fine for hundreds or a few thousand items (the database caps bind parameters at 32 767). If collections grow far beyond that, switch the adapter to a join; the port hides it.

## A collection's ETag covers its item count and its membership

**Decision:** the response includes `item_count`, so the ETag is built from the collection's `updated_at` and the live item count, and adding or removing items bumps `updated_at`. `If-Modified-Since` is ignored when `If-None-Match` is present, and `If-Unmodified-Since` when `If-Match` is present, as RFC 9110 requires.

**Rationale:** an ETag from `updated_at` alone gave a stale 304 when an item was deleted elsewhere. Browsers send both validators, and the old fall-through to the date check re-introduced the same bug, so it had to be fixed in the shared helper as well. Other routers' ETags are unchanged because the new input is optional.

**Consequence:** an `If-Match` taken before a membership change now fails with 412 on rename, which is correct because the collection changed.

## Collection slugs: immutable, derived from the name, unique among live collections

**Decision:** each collection has a slug for pretty links. It is derived from the name (`slugify`, falling back to `collection`, then `-2`, `-3` until free) or given explicitly, and it never changes on rename, so a saved link never breaks. It is unique among collections that have not been deleted (a partial unique index backs the check), so a deleted collection's slug can be reused. Slugs are global for now.

**Not decided:** per-owner uniqueness when multi-user arrives; that is an index and use-case change in one place. (Decided 2026-10-10: unique per owner; see the accounts entry.)

## Collection ownership is stored but not enforced: a precondition for multi-user

**Superseded (2026-10-10)** by [Accounts and private ownership (multi-user Stage 1)](#accounts-and-private-ownership-multi-user-stage-1): every collection path is now scoped to its owner. Kept for history.

**Decision:** every collection records an `owner_id` and a `visibility` (private), and use cases take the acting user, but nothing is checked yet because there is one fixed user. Enforcement through `AuthorizationPort` is a hard precondition for shipping multi-user, on every path that touches a collection: get, list, update, delete, adding and removing items, and the read path behind `GET /node?collection=`, where the `CollectionMembers` bridge and `ListNodes` will need to take the requesting user (a port-signature change, not a one-line check).

**Rationale:** the rest of the application is wired the same way (permissions are wired, not enforced). Adding owner checks now could wrongly reject legitimate callers, such as the system user, and would be tested against a user model that does not exist. An automated review flagged the missing owner checks as an authorisation gap; they are deliberately absent until multi-user, and this entry is where that is written down.

**Consequence:** if multi-user ships without this work, any user could read, change or delete another user's collections.

## Collection errors: 400 for domain validation, 422 for malformed requests

**Decision:** a blank name, an unknown item id and similar domain failures return 400, the application's existing mapping for domain `ValidationError`. Requests that fail Pydantic validation (a name over 120 characters, more than 500 ids in one request, a malformed id, unknown fields) return 422. The client treats both as "invalid input".

## Example packs can ship collections, installed last and removed first

**Decision:** a version 2 pack has an optional `collections` section: named lists of the pack's own items. `examples` owns a third target port, `CollectionTarget`, and `entrypoints/api/shared/bridges/example_targets.py` implements it over the real collections use cases, so `examples` still imports neither `graph` nor `collections`. Install creates collections as the last step, after connections. Removal runs collections before items. A collection's recorded content is its name, description and the sorted ids of its live members, so renaming it, changing the description or adding, removing or deleting any member makes it "edited", and an edited collection is kept.

**Rationale:** collections are the way to show that items can be grouped without being typed or connected differently, and a pack is the right place to demonstrate it. Removing them before their items means an unedited example collection stops counting as a reason to keep its members. An example item that is on any collection that survives (the user's own, or an edited example one) counts as user data and is kept, in the same way an item with your own connection is. The collections module derives the slug, so a pack collection can never clash with the user's own.

**Consequence:** anything kept also keeps the item types it uses, so reinstalling the pack re-adopts what was kept (see "Removing examples keeps anything the user has touched"). Example collections carry the same "Example" badge as example items and types, and `GET /example/entities` lists their ids.

## Add-on example packs require other packs and never change them

**Decision (2026-10-09):** a pack format 4 pack may list `requires` (a list, so a bridge add-on can need several packs) and refer to a required pack's types and items as `pack:ref`. An add-on only adds: it never changes a required pack's types or items, and everything it creates is recorded in its own installation. Removal is blocked, not cascaded: a pack cannot be removed while an add-on that requires it is installed (or half installed), and the message names every dependant. An edited add-on connection is kept when the add-on is removed, and then counts as the person's data on the base item, so a later removal of the base pack keeps that item.

An add-on item of a base item type inherits that type's cover style, read through the catalogue, so it gets a generated cover and is removed with the add-on. One add-on ships: `games-extras` (Extra board games, needs Board games). The Film soundtracks add-on was converted to links declared by Music (2026-10-14, see "Optional links between example packs").

**Note:** the blocking is derived from the current catalogue's `requires`, not recorded at install time. A later pack update that drops a `requires` would lift the block. Nothing the person made is lost by that, because touched base items are kept as user data.

## Grouped search fans out on the client; ranking is per group

**Decision (2026-10-09):** the search popup (`/`) shows Items, Collections, Item types and Pages. It fans out on the client behind `searchEverything` (`frontend/src/lib/palette-sources.ts`); a backend search endpoint is deferred. Item types (listed once and cached) and pages (a fixed list) are filtered locally. Collections gained an optional `q` on `GET /collection`. Ranking is per group (exact, then prefix, then word-prefix, then other); there is no ranking across groups, and group order is fixed. A source that fails shows a retry row for its group only, and "Nothing found" appears only when every source answered and all were empty.

**Accents:** matching is accent-insensitive on the server (`unaccent`) and in the local filters and match context (`foldText`), so "cafe" matches "Café" and the reverse.

**Consequence:** one keystroke burst costs up to two requests (items, collections); a single endpoint would cut that and allow cross-group ranking.

**Collections follow-up (2026-10-09):** the collections page gained a search box that uses the collection `q` (same debounce, `?q=` pick-up and "Nothing matched" state as the items page). When the popup's Collections group is full (`GROUP_CAPS.collections` rows, so more may exist) it adds a last "See all collections" row that opens `/collections?q=...`. It is a normal row of that group: it joins arrow-key navigation, is disabled while the group is stale and follows the same focus rules.

## Text search ignores accents via the unaccent extension

**Decision (2026-10-09):** "cafe" finds "Café" and "café" finds "Cafe". Postgres matches with `unaccent(column) ILIKE unaccent(pattern)` (LIKE escaping unchanged) for item name, description and attribute values, for attribute-value suggestions, and for `q` on collections. A migration runs `CREATE EXTENSION IF NOT EXISTS unaccent`; its downgrade is a deliberate no-op because the extension may be shared. The in-memory repositories fold the same way (Unicode NFD, drop combining marks, casefold), each module with its own small helper so `graph` and `collections` stay independent. This replaces the earlier "accents are not folded" note in the grouped-search entry.

**Rationale:** `unaccent` is a trusted extension on Postgres 13+, so the application role can create it without superuser rights.

**Consequence:** no index is affected because none exist on these columns; if one is added later it needs an immutable wrapper around `unaccent`. Characters such as "ß" or "ø" follow the extension's rules in Postgres but not the in-memory NFD fold.

## Example packs generate covers as removable PNGs

**Decision (2026-10-09):** pack format version 3 lets an item type declare `cover: {style}`; installing draws a cover per item of that type (records get a sleeve, films a poster, board games a box, recipes a card). Covers are PNG, not SVG, because the media module treats SVG as unsafe and refuses it. Rendering is deterministic from the item name (colour and initial), so a reinstall gives identical bytes. `examples` owns a `CoverTarget` port, bridged to media in `entrypoints/api/shared/bridges/`, so it imports neither media nor graph.

**Removal:** a cover is a removable entity settled before items, so a pack's own cover is never counted as the person's file. An untouched cover is deleted; a cover the person replaced is their file, so it is kept and keeps its item. Reinstall re-adopts a kept cover and never takes over a cover the person added to an item that had none.

**Also fixed:** media's `Content-Disposition` now uses RFC 6266 encoding, so non-ASCII file names download correctly.

**Known limit:** the built-in Pillow font draws only ASCII initials; a name starting with another character shows "?". Every shipped item name starts with an ASCII letter. A bundled font would lift this.

## A second cover is a 409, not a server error

**Decision (2026-10-09):** attaching with `attribute_key=cover` to an item that already has a cover (`POST /media/{id}/attachments`, `POST /media/attached`) returns 409 `CoverAlreadySetError` ("This item already has a cover. Set another image as the cover instead, or clear the cover first."). Before, the unique index `uq_media_attachment_cover` rejected the insert and the request failed with a 500. `AttachMedia` and `UploadAndAttachMedia` check first (the upload check runs before anything is staged); the SQL repository's `add()` also translates an `IntegrityError` on that one index into the same error inside a savepoint, so two racing requests get the 409 too. Other integrity errors are not translated. The in-memory repository enforces the same rule.

**Unchanged:** setting a cover with `attachments/cover` still replaces the previous one, and the example-pack cover bridge attaches without a key and then calls that endpoint, so it never hit this.

**Closed (2026-10-09):** two simultaneous set-cover calls on one item no longer reach the index. `SetMediaCover` first takes a transaction-scoped Postgres advisory lock keyed on the target (`MediaAttachmentRepository.lock_target`, `pg_advisory_xact_lock`), so the second call waits for the first to commit, then reads the new state and moves the cover; last write wins and neither call fails. An advisory lock was chosen over `SELECT ... FOR UPDATE` because the target may have no attachment rows to lock yet and the target lives in another module. The in-memory repository's `lock_target` is a no-op because its calls cannot interleave inside a use case. A set-cover racing an attach with `attribute_key=cover` is still settled by the unique index, giving the attach the 409.

## Built-in Countries stays a database row for now (2026-10-10)

**Decision:** "Countries" stays a built-in preset row (`builtin = true`, stable id from `uuid5("builtin:Countries")`), seeded by a migration from `shared/data/iso-data.json`, like "Condition grades" and the built-in fields and field groups. It does not become a separate shared-data source (`builtin:countries`) and there is no Country field type yet.

**Rationale:** every built-in preset is a row, so a virtual source would make Countries the odd one out and add code to the list, copy and in-use guards for one list. Fields reference the list by id and store country names, so nothing is copied around and nothing is broken. Currencies are different: they are not presets, only a list for the money field. Nothing needs more today: no pack or feature is waiting on it.

**Known gap, not fixed:** a seeded list is not refreshed on servers that already ran the migration, so a regenerated ISO file does not reach them. ISO country lists change rarely.

**If it ever matters:** sync the built-in rows from code and the shared file on startup, keyed by their stable ids (idempotent, leaving copies a person made alone), and let example packs reference a built-in preset by its stable id. A real Country field storing ISO 3166-1 alpha-2 codes, which can link, sort and later show flags, is a separate and larger change because existing fields hold names.

## Accounts and private ownership (multi-user Stage 1)

**Decision (2026-10-10):** Menagerist has local accounts, and everything a person creates (items, connections, collections, files, example installations) is visible to that person alone. This replaces "AllowAll authorization adapter in v1" and "Collection ownership is stored but not enforced". Sharing between people is Stage 2. The choices that matter long term:

**Passwords and sign-in**

- **Hashing is stdlib `hashlib.scrypt`, behind a hasher registry, not argon2.** No new dependency or image weight, and scrypt is an OWASP-recommended KDF. Every stored hash carries its scheme prefix (`scrypt$...`) and its parameters (N=2^15, r=8, p=1). `MENAGERIST_IDENTITY_PASSWORD_HASHER` names the scheme for new hashes, any known scheme still verifies, and an older hash is rewritten on the next successful sign-in. Parsing rejects out-of-bounds parameters so a tampered hash cannot force large memory use. Moving to argon2 later is one adapter.
- **The admin creates accounts with an initial password**, not invitation links. No email infrastructure exists, and links add expiry and token handling for no Stage 1 benefit. The user must change the password at first sign-in: `password_expired` is set on the account, and until it is cleared every content route answers 403 with problem type `password_expired` (the account routes still work). An admin password reset sets it again.
- **Sign-in goes through an `Authenticator` port.** Stage 1 has one adapter (local username and password) that returns a verified identity. OIDC and trusted-proxy-header sign-in (for people running Authentik or Authelia in front) become later adapters that reuse sessions, roles and the access policy unchanged.
- **Throttling is stored on the user row.** *(Superseded 2026-10-11 by "Sign-in throttle, disabled accounts and user-management permissions" below.)* Five failed attempts within a fixed 15-minute window lock the account for the rest of the window (429 with `Retry-After`). The state needs no extra service, and the user row is read `FOR UPDATE` so concurrent guesses are serialised. Known cost: the 429 reveals that the username exists. Otherwise a wrong password, an unknown user and a disabled user give the same 401, and the unknown and disabled paths verify a decoy hash, so the expensive scrypt step takes the same time as for a wrong password. A small difference remains: a wrong password for a real user also writes the failure count and commits. The scrypt step runs with no database transaction open (the user is read, the password checked, then the row is locked and re-checked to record the outcome), so a flood of attempts cannot hold every pooled connection.
- **Sessions** are random tokens stored as hashes and sent in an HttpOnly cookie (`menagerist-session`). CSRF uses the double-submit pattern: a readable `menagerist-csrf` cookie that the client copies into an `X-CSRF-Token` header on every unsafe `/api/v1` call (sign-in, setup and status are exempt). CORS allows no credentials. Logout answers with `Clear-Site-Data: "cache"` so a shared browser keeps nothing of the previous person (browsers ignore it on non-secure origins other than localhost; the frontend also clears its own cache on sign-in and sign-out).
- **Before setup (no users)** every `/api/v1` route except the auth routes answers 401 with problem type `setup_required`, and the frontend redirects to `/setup`. After setup a missing session answers 401 `unauthenticated`. Health, version, docs and the SPA shell stay public.

**Access model**

- **Authorisation lives in an access rule, not in repositories.** *(2026-10-22: the `AccessPolicy` port is now the `AccessGuard`; see the entry at the end.)* `AccessPolicy` was a `shared_kernel` port; the Stage 1 implementation is `OwnerAccessPolicy` (`entrypoints/api/shared/access_policy.py`). It is the only place that knows who may see or change what: `scope_for(actor)`, `assert_can_view/modify/delete(actor, owner_id)` (all raise `NotFoundError`, so existence never leaks) and `require_admin(actor)` (403). Administrators get no special view of other people's content.
- **Repositories take a required `AccessScope` criterion** (`AccessScope.of(user_id)` or `AccessScope.everyone()`) on every method that returns or counts content, so lists, searches, counts, keyset paging and ETags are filtered in SQL; filtering afterwards would break `Total-Count` and paging. Repositories contain no rules. A missing scope is a type error, and architecture tests plus a generated cross-user isolation test (every route, as a second user) enforce it. Stage 2 replaces `OwnerAccessPolicy` with a sharing policy and widens what a scope means in SQL; use cases do not change.
- **Connections and files have their own `owner_id`.** A connection is owned by its creator, and creating one needs both endpoints visible to that person. A media asset is owned by its uploader and attachments follow their asset; attaching needs an owned asset and a visible target (a media port, bridged to graph).
- **Owner columns stay nullable in the database in Stage 1** (items, connections, files, example installations; collections are NOT NULL already). A row with no owner is visible to nobody, and the domain requires an owner on construction. Making the columns NOT NULL is a follow-up migration once every deployment has claimed its data.
- **Collection slugs are unique per owner** (`(owner_id, slug)` among live collections), and `get_by_slug` is scoped.
- **Destructive structure operations are admin-only.** Deleting an item type or connection type (it clears the type on everyone's content) and purging an attribute run through `AuthorisedCommandHandler` with a permission. Usage counts and attribute-value suggestions are scoped to the viewer. Creating and editing structure stays open to every member.
- **Permission strings read `<module>:<resource>:<action>`** (for example `graph:node_type:delete`), declared as a `StrEnum` per module. `RoleAuthorizationAdapter` gives admins and the system actor every permission and members `MEMBER_PERMISSIONS` (empty today; *superseded 2026-10-22: it is now the 14 content permissions*). `GET /api/v1/auth/me/permissions` returns the signed-in account's effective permissions as a typed list, and the frontend hides controls with `auth.can(...)`; the server still enforces them.
- **Example packs install per user.** `example_installations.owner_id` is added, the active-pack uniqueness becomes `(pack_id, owner_id)`, and pack targets run as the installing person, not the system actor. Shared types a pack needs that exist because another person installed the same pack are reused (never recorded as owned by this person, never removed by them); removal of a shared type keeps it while any person's content still uses it, using an all-scope in-use check. A clash with a type from anywhere else is still a 409.

**First run**

- **The first administrator claims existing data in the same transaction as setup.** `POST /auth/setup` (or `menagerist identity create-admin` when no accounts exist) creates the admin and gives them every row with no owner or a legacy owner (`UUID(int=0)` from example installs, `UUID(int=1)` from the old fixed API user). Soft-deleted rows are included. If the claim fails, nothing is created.
- **Setup is serialised by a Postgres advisory lock** (`lock_for_setup`), so two simultaneous first visits cannot create two administrators; the loser gets 409. Admin-removing changes (demote, disable) take a second advisory lock so two admins cannot remove each other. The last active administrator cannot be demoted or disabled.
- **Accounts are local only** in Stage 1. A forgotten administrator password is reset with `menagerist identity reset-password`.
- **The interactive API docs sign in through the API itself** (2026-10-11). `/api/docs` is our own Swagger UI page: `POST /auth/login` with "Try it out" stores the cookies, and a small same-origin script (`swagger-init.js`) adds `X-CSRF-Token` from the CSRF cookie to unsafe `/api/v1` calls. The header is deliberately not in the OpenAPI schema, which keeps the generated frontend client unchanged; the Authorize button is hidden because a Cookie header cannot be set from JavaScript.

**Testing time**

- **There is no `Clock` port.** Entities set timestamps with `datetime.now(UTC)` as before, and tests freeze time with `time-machine` (a dev dependency; it works on Python 3.14).

**Consequence:** until the follow-ups below land, `owner_id` is nullable on four tables and members hold no permissions beyond using the app.

---

## Sign-in throttle, disabled accounts and user-management permissions (2026-10-11)

**Decision (2026-10-11):** four changes to Stage 1 identity, made together.

**Sign-in throttle (replaces the per-user-row lockout).** Failed password checks are counted in a `sign_in_attempts` table behind a `SignInAttemptRepository` port (in-memory twin, SQL adapter). A counter is keyed on a SHA-256 hash of the lower-cased username, and separately on a hash of the client address, so it exists whether or not the account does: an unknown username locks after the same five failures with the same 429 and `Retry-After`, which removes the existence oracle the old design admitted. Limits are 5 per username and 20 per address in a fixed 15-minute window (`MENAGERIST_IDENTITY_SIGN_IN_USERNAME_ATTEMPTS`, `MENAGERIST_IDENTITY_SIGN_IN_IP_ATTEMPTS`, `MENAGERIST_IDENTITY_SIGN_IN_WINDOW_MINUTES`). The failure that reaches the limit locks until the window ends. A lock is evaluated before any password is checked; a locked attempt still verifies the decoy hash so it costs the same time. A failure is one `INSERT ... ON CONFLICT DO UPDATE`, so concurrent failures serialise on the row and none is lost. Success clears the username counter and leaves the address counter alone. Expired rows are deleted lazily on each recorded failure. `POST /auth/password` (change password) applies the same limits to its current-password check, keyed on the user id and the address. The old `users.failed_attempts`, `failure_window_started_at` and `locked_until` columns are dropped. *(Superseded 2026-10-12: the lock is no longer checked before verifying; attempts are reserved first, so a burst cannot overshoot.)* Known cost: the address is `request.client.host` after Granian's proxy-header wrapper, which now trusts `X-Forwarded-For` only from peers in `MENAGERIST_API_TRUSTED_PROXIES` (addresses, CIDR networks or `*`, validated with pydantic's IP types; default `127.0.0.1`). Setting `*`, or listing a proxy that does not overwrite the header, lets the address counter be evaded or aimed at someone else's address. The username counter does not depend on it. An administrator lifts a username lock with `UnlockUser` (`POST /user/{id}/unlock`, `identity unlock`); a password reset also clears it.

**A disabled account is disclosed only after its password verified.** Correct credentials on a disabled account answer 403 `account_disabled` ("This account has been disabled. Ask an administrator."), so a person is not left guessing why a right password fails. A wrong password for a disabled account is the same generic 401 as any other, and every path spends one scrypt verify, so the answer is not a username oracle. A correct password on a disabled account is not a failure: it neither counts toward nor clears a lock.

**User management has its own permissions.** `IdentityPermission` (`identity:user:create`, `list`, `update`, `reset_password`, `unlock`) joins the catalogue; create, update, reset and unlock each imply list. The use cases run through `AuthorisedCommandHandler` / `AuthorisedQueryHandler`, so `PermissionAwareRoute` reflects them as `x-required-permission` and `/auth/me/permissions` lists them. The ad-hoc `require_admin` helper is gone. Admins and the system actor hold all of them; members hold none of these. Changing your own display name (`PATCH /auth/me`) needs no permission. `Permission` is now a real union of the graph and identity enums.

**The CLI takes the initial password from settings.** `IdentityCliSettings` (`MENAGERIST_IDENTITY_INITIAL_PASSWORD`, or a `menagerist_identity_initial_password` file in `/run/secrets`) is loaded only by the `identity` CLI and is not part of the server settings; the hidden, confirmed prompt is the fallback. A file is preferred because an environment variable appears in `docker inspect` and process listings.

**Readiness deliberately does not carry setup state.** A server with no administrator is healthy: the orchestrator should not restart it, and `/health/ready` should stay a statement about dependencies. Instead the lifespan logs one WARNING per worker at start ("No administrator exists yet: open /setup or run `menagerist identity create-admin`"); an unreachable database skips the check. This closes the earlier open idea of a readiness `warn`.

**Smaller changes made with it:** `users.last_login_at` records the last successful sign-in (not failures or session use) and is shown in Settings > Users and `identity list`; media content and thumbnails now answer `Cache-Control: private, no-cache` instead of a year-long `immutable`, so every response passes the ownership check before a 304; the Swagger UI assets are pinned to an exact version with Subresource Integrity hashes.

---

## Security fixes after the Stage 1 review (2026-10-12)

Fixes for the authentication security review (`.superpowers/sdd/2026-10-10-multi-user-stage-1/review-security-auth.md`). No schema change and no new migration.

- **A password change voids a sign-in in flight.** `Authenticator` now returns the stored hash the password matched (`VerifiedIdentity.credential_hash`); `SignIn` locks the row to start the session and refuses with the generic invalid-credentials error if the hash differs. Hashing still runs outside any transaction. Disabled and missing accounts were already re-checked.
- **One process-wide cap on hashing.** `BoundedPasswordHasher` wraps the hasher in the composition root with a semaphore sized by `MENAGERIST_IDENTITY_PASSWORD_HASH_CONCURRENCY` (default 2, minimum 1). Every scrypt hash and verify (sign-in including the decoy, change, reset, create, setup, the CLI) goes through it, so a flood queues instead of allocating about 32 MiB per request. Waiting calls hold a worker of the default thread pool; that is acceptable because only password work and small file operations use it.
- **Attempts are reserved, not recorded afterwards (replaces the overshoot cost above).** `SignIn` and `ChangePassword` count the attempt atomically (the same single upsert, now `RETURNING` the counter) and commit before verifying. An attempt whose count is over the limit is refused with the existing 429 and `Retry-After` without being checked (a decoy hash still equalises sign-in timing). A correct password clears the username (or user id) counter and gives the address's attempt back (`release_attempt`, matched on the window it was counted in), so success still never counts against the address; a correct password that leads nowhere (disabled account, refused new password) gives back every counted attempt. Parallel guesses against one username can therefore never have more than the limit checked, whatever addresses they come from. Refused attempts stay counted on both keys, which does not extend a fixed window.
- **Admin reset and unlock clear the password-change counter** (the user id key) as well as the username counter.
- **Cross-site guard on the public POSTs.** `POST /auth/setup` and `/auth/login` have no session, so the CSRF token cannot protect them, and the default CORS `*` let any page run first-run setup. A `refuse_cross_site` dependency (next to `verify_csrf`) answers 403 `cross_site_refused` when `Sec-Fetch-Site` is `cross-site`, or an `Origin` is present that is neither the request's own origin (scheme and host as seen after the trusted-proxy wrapper) nor a listed `MENAGERIST_API_CORS_ORIGINS` entry; `*` there never makes a cross-site request acceptable. Requests with neither header (curl, the CLI, tests) pass. The `cors_origins` default is unchanged and is for the owner to decide. Behind a TLS-terminating proxy that is not trusted, the scheme seen is `http`, so the `Origin` check refuses the browser until `MENAGERIST_API_TRUSTED_PROXIES` is set.
- **Failed sign-ins and lockouts are logged** as warnings `sign_in_failed` and `sign_in_throttled` with the client address and the first 12 hex characters of the username throttle key. The raw username is never logged because people sometimes type a password into that box.
- **Documented, not changed:** every client behind one proxy or NAT shares an address counter, so 20 failures lock them all (set `MENAGERIST_API_TRUSTED_PROXIES`); `MENAGERIST_IDENTITY_COOKIE_SECURE=true` behind a TLS-terminating proxy. The CLI still reuses a configured initial password for resets and there is no idle timeout; both are the owner's call.

---

## Security fixes after the Stage 1 review, second batch (2026-10-12)

Fixes for the leak and isolation reviews (`review-security-leaks.md`, `review-security-isolation.md`) and the owner's decisions on the open items from the first batch. No schema change and no new migration.

**Owner decisions**

- **CORS is same-origin by default.** `MENAGERIST_API_CORS_ORIGINS` now defaults to empty: the API serves the SPA and Vite proxies `/api`, so nothing needs cross-origin access. A separate frontend lists its origin; `*` is still accepted when set explicitly and is documented as not recommended. The cross-site guard on sign-in and setup was already written for an empty list. This supersedes "the `cors_origins` default is unchanged" above.
- **Attribute purges answer 204.** `PurgeNodeTypeAttribute` and `PurgeEdgeTypeAttribute` return nothing and the routes answer 204 No Content; the all-users count is only logged. The count was an oracle for how many items other people hold with a field, and an administrator has no special view of other people's content. `AttributePurgeResponse` is gone.
- **`identity reset-password` always prompts** (hidden, confirmed), unless `--from-settings` is passed, which reads `MENAGERIST_IDENTITY_INITIAL_PASSWORD` or the secret file as before. `create-admin` still uses the settings first and then the prompt. A bootstrap password that stays in `.env` or a secret file is therefore never applied silently to someone's account. This supersedes "the CLI still reuses a configured initial password".
- **Idle session timeout, with the absolute cap.** `MENAGERIST_IDENTITY_SESSION_IDLE_HOURS` (default 0, off; whole hours otherwise) ends a session unused for longer than that. `Session.is_idle(now, limit)` is checked in `GetCurrentUser` next to expiry, against `last_seen_at` (recorded at most once a minute, so any whole hour is accurate). An idle session is handled exactly like an expired one: 401, row removed. `MENAGERIST_IDENTITY_SESSION_TTL_HOURS` stays the hard cap whatever the activity. This supersedes "there is no idle timeout".
- **Two levels of version and readiness information.** The public `GET /api/v1/system/version` returns only `{name, current_version}` and the public `GET /api/health/ready` returns only `{"status": "pass"}` (200) or `{"status": "fail"}` (503), with the same `application/health+json` type; a warning still counts as ready. The commit, branch, build time and migration head (`GET /api/v1/system/version/detail`) and the per-check measurements (`GET /api/v1/system/health/ready/detail`) need the new permission `system:diagnostics:read`, held by administrators and the system actor (`SystemPermission` in `system/application/permissions.py`, `GetVersionDetail` and `GetHealthReadyDetail` are `AuthorisedQueryHandler`s). Liveness is unchanged. Container health checks, `scripts/healthcheck.py` and Playwright's `webServer` look at the status code only. The failing-check `output` is a fixed `check failed`; the real error is logged with the request id. The probes stay at `/api/health` and `/api/health/ready` (no session, so orchestrators and the Docker healthcheck keep working); every other system route lives under `/api/v1/system` (the public `version` on the unauthenticated v1 router, the diagnostics on the session-protected one), so the root `/api` holds probes only. The old `/api/version`, `/api/version/detail`, `/api/health/ready/detail` and `/api/browser-check` paths are gone (2026-10-23).
- **HSTS is not sent by the app.** It cannot know it is reached over HTTPS, and a wrong header is hard to undo. The deployment notes in README and CONTRIBUTING recommend it at the TLS-terminating proxy, with Caddy and nginx lines.

**Leaks**

- **Upload bodies are bounded before they are parsed.** FastAPI reads and spools the whole multipart form before any dependency runs, so an anonymous client could fill `/tmp`. `UploadLimitMiddleware` (pure ASGI, innermost) guards `POST /api/v1/media` and `/api/v1/media/attached`: a `Content-Length` over `MENAGERIST_MEDIA_MAX_UPLOAD_SIZE` plus 64 KiB of multipart overhead is answered 413 problem+json without reading the body, and a body with no length is counted as it arrives and cut off past the limit. FastAPI turns any error raised while reading the form into a 400, so after the cut-off the app is told the client disconnected and its answer is replaced by the 413. The check runs before authentication on purpose. The limit still applies to the file itself in `storage.store`.
- **Decompression bombs are refused.** `PillowImageProcessor` sets a 40 megapixel limit (`MAX_IMAGE_PIXELS`); Pillow's warning band and error band both raise the new `ImageTooLargeError` (a validation error, 400). `StageMedia` deletes the staged file before re-raising, `RegenerateThumbnails` skips such an asset, and both run the decode in `asyncio.to_thread` so it does not block the event loop. Not a configurable setting. Other formats above 40 megapixels are refused rather than stored without a thumbnail. A JPEG is allowed up to 300 megapixels (`MAX_JPEG_PIXELS`) because its thumbnail is decoded at 1/2 to 1/8 scale with `Image.draft`, so phone photos above 40 megapixels are accepted; the original is stored untouched.
- **500 and 422 bodies no longer echo.** A non-domain exception answers a fixed `Internal Server Error` / `An unexpected error occurred.` and is logged with its traceback and the request id. A failed example install therefore no longer names its cause in the response (the log has it). `RequestValidationError` has its own handler: problem+json with the same `detail: [{type, loc, msg}]` list the web client already reads, minus FastAPI's `input` and `ctx`, so a rejected password is never sent back.
- **Client file names are neutralised in logs** (`shared_kernel/log_safe.loggable`: control characters escaped, 100 characters at most) in `StageMedia` and `UpdateMedia`.

**Isolation**

- **Example-pack removal no longer races item creation.** Removing a pack's item type used to check "in use" in one transaction and delete (clearing the type on everyone's items) as the system actor in another. It now runs `DeleteUnusedNodeType`: one transaction that takes an exclusive row lock on the type (`NodeTypeRepository.get_for_removal`, `SELECT ... FOR UPDATE`), re-checks use across all people, and soft-deletes only if no item uses it, otherwise raising `NodeTypeInUseError`, which the pack target reports as the existing "kept, still in use". `CreateNode` and `UpdateNode` read the type with `get_by_slug(..., guard_item_write=True)`, a key-share lock that conflicts only with that exclusive lock (never with ordinary type edits), so an item written meanwhile makes the removal refuse, and a removal in progress makes the writer wait and find the type gone. It never clears a type on anyone's items. Relationship types were already re-checked inside `DeleteEdgeType`.

**Accepted for Stage 1, not changed**

- Creating private content with a new type name publishes that name as a shared item or connection type, and promoting a field copies its definition (and option lists) into the shared type. Types are shared vocabulary; a per-person vocabulary is a Stage 2 option.
- The example-pack "still in use" and "shared" answers can reveal that other people use a shared type. This follows from the all-people in-use check and is accepted.

---

## Cross-site guard trusts `Sec-Fetch-Site`, and proxy problems are visible (2026-10-13)

Behind a TLS-terminating proxy that was not in `MENAGERIST_API_TRUSTED_PROXIES`, every sign-in was refused: the app rebuilt its own origin as `http://host` while the browser sent `Origin: https://host`.

- **`Sec-Fetch-Site` decides first.** `cross-site` is refused, `same-origin` is accepted. Page script cannot set the header and every current browser sends it, so this does not depend on the proxy. The same approach is used by Go's `net/http` cross-origin protection. The header's specification is still a W3C working draft.
- **The `Origin` comparison stays as the fallback** (header missing, `same-site`, `none`, or any other value), with the full origin including the scheme, not only the host: stricter than Go's host-only fallback. An old browser behind an untrusted proxy still needs the proxy configured. A configured CORS origin is still accepted there; `*` is not.
- **A malformed `Origin` is refused** (it used to raise in `urlsplit` and answer 500).
- **Refusals are logged** with the claimed and seen origins and `Sec-Fetch-Site` (client text goes through `loggable`).
- **Misconfiguration is surfaced, never enforced.** `app.platform.proxy_signals` keeps only times (bounded, one hour) for two signals: forwarding headers from a peer outside the trusted list (noted by `ProxyHeaderObserver`, outside Granian's wrapper, so it sees the real peer) and a same-origin request whose `Origin` differs from the one the app saw. The first sighting of each per hour is logged as a warning with the fix, and `ProxyConfigurationCheck` reports a `warn` for `proxy:configuration` on the admin-only `/api/v1/system/health/ready/detail`. It never fails readiness: a configuration problem must not take the instance out of rotation, and a warning still counts as ready. The counts are per process.
- **Not chosen:** an explicit public-URL setting (stricter, but every proxied install would have to set it), a host-only fallback, and trusting every proxy by default (it would let anyone reaching the container spoof the address the sign-in throttle uses).
- **HSTS** stays at the proxy; the README now asks for it, because the guard now relies on the browser's own headers.

## Optional links between example packs (2026-10-14)

**Decision:** pack format version 5 lets a pack declare `links` to another pack (`with`, `from`, `to`, `type`). A link is an ordinary connection that is made once both packs are installed, whichever was added second, and removed when either goes. Removal is never blocked; this is the difference from an add-on (`requires`), which cannot exist without its base and blocks the base's removal. Authors choose: `requires` for content that cannot exist without the other pack, `links` for connections that are only nice to have.

**Shape:** the relationship type of a link is one the declaring pack defines (it exists whether or not the link ever applies); at least one end is `<with>:<ref>`. The catalogue checks at load that the `with` pack exists and defines every item a link names. Links take no part in the dependency cycle check.

**Recording:** a link is a `connection` record in the declaring pack's installation with ref `link:<with>:<n>` (`n` is its index in `links`). `Installation.record_late` records after the install finished, which `record` refuses. No new table or migration.

**Applying:** after a pack finishes installing, `apply_links` runs for that person's own installations only, for the pack's own links whose partner is installed and for other installed packs' links that point at it. A link is skipped, quietly, when an end is gone or no longer owned by its pack, when it was already applied, or when a connection of that type already joins the two items (so a kept link, or one the person made, is never duplicated). A target error is logged and skipped; it never fails or rolls back a pack that is already installed. `InstallResult.linked` and the API's `linked` count what an install made, in either installation, and the pack's own `created` counts stay about its own content.

**Removal:** removing a pack first settles the links other installations of the same person recorded `with` it (removed, or kept if edited), then removes the pack as before. Its own links are ordinary owned connections and go with it. A kept link keeps the item it touches under the existing "has your connections" rule.

**Content:** Music declares the four "Soundtrack of" links to Movies, with the relationship type `music-soundtrack-of`; the `soundtracks` add-on is gone (nothing had been released, so no migration). Ids in an existing development database's `soundtracks` installation just stop being listed, and its connections stay as the person's own.

**Known limit:** two installs running at the same instant could both try the same link. The skip-if-exists check makes a duplicate unlikely but does not rule it out; accepted.

**Not chosen:** a separate link-set record per pack pair (a new table and a second place for the UI to look) and a hidden generated add-on per pair (add-ons block removal of their base, the opposite of what links are for).

## The condition tree is the only stored form of a search (2026-10-15)

**Decision:** a search is one JSON condition tree: `{v, where, sort}`, with `where` a group (`and`, `or`, `not`) of conditions (text, type, favourite, tag, field, date). `v` is the format version, currently 1. The JSON is parsed into frozen domain types (`graph/domain/query.py`) and nothing else is stored or sent. The URL (`?f=`, base64url of the JSON) and, later, smart collections hold the same tree; a text syntax would be a parser and printer over it, not a second format.

**Limits:** depth 4, 50 conditions, text values of 200 characters. A condition that names a field the item type no longer has (deleted or archived) is not an error: it matches nothing, and the response lists it under `warnings` with its path so the page can mark it. A wrong operator for a field, a bad operand or a broken tree is a 400 naming the JSON path of the first bad condition.

**Why:** one form means the builder, the link, the API and saved collections cannot drift, and old links keep working because the version is in the data. Warning instead of failing keeps a shared link or a future saved collection usable after someone edits an item type.

**Not chosen:** storing a text syntax (it would need a parser on every read and a migration on every grammar change) and failing the whole search on a stale field (a saved search would break when a field was removed).

## Search is separate from the list, and pages by keyset on the sort values (2026-10-15)

**Decision:** `NodeRepository.search` and `search_count` sit beside `list` and `count` instead of adding a query parameter to them. `list` and `count` keep their plain-filter contract and `GET /node` is unchanged; `POST /node/search` takes the tree. Paging is keyset on `(sort values, id)`, nulls last, ties broken by id. The cursor is opaque base64url JSON. An offset would make deep pages slow and unstable while items change.

**One meaning, two engines.** The Python evaluator (`query_eval.py`, used by the in-memory adapter) is the reference semantics; the SQL compiler (`query_sql.py`) must agree with it. One scenario table in `test_node_search.py` runs against both adapters, and a new rule is added there first.

**Capped total.** The count is the slowest part of a search, so the response total stops at `TOTAL_CAP = 1000` and says `total_capped` when it stopped; the page shows "1,000+ items". An exact total of a large result is not worth seconds of waiting.

**Indexes.** Migrations add GIN indexes on `attributes` (`jsonb_path_ops`) and `tags`, trigram indexes on name, description and `attributes::text`, and four sort indexes on the owner plus the sort key: name ascending, name descending, created and updated. The descending timestamp indexes were left out: ties are rare and Postgres reads the ascending index backwards with a small incremental sort. Each extra btree costs a little on every write, and every update touches the `updated_at` index (it can never be a heap-only update). That is the price of 12 ms pages instead of seconds.

**Free text.** A text condition first narrows candidates with a trigram prefilter on name, description and `attributes::text`, then applies the exact check. The prefilter is a superset of the exact match (a table of 66 queries against 32 values pins that), and is skipped for queries it cannot serve safely: under three characters, or containing a double quote, a backslash or a control character. `unaccent` maps eleven other characters (U+02BA, U+201C, U+201D, U+201F, U+2033, U+301D, U+301E, U+FF02 to a double quote; U+2216, U+FE68, U+FF3C to a backslash), which JSON escaping would hide from the prefilter, so they skip it too. A test scans every Unicode code point against the real `unaccent` and fails with the code point if Postgres ever maps another character to a quote, a backslash or a control character. `SET LOCAL jit = off` is issued for text queries only (not app-wide): JIT compilation added about 0.8 s to a 70 ms query and helps nothing else we run.

**Measured** (100,000 items, one local Postgres, 51-item pages, eight timed runs each):

| Search | Before | After |
|---|---|---|
| Sort by name, first page | 2,189 ms | 12 ms |
| Sort by name, deep page | 2,253 ms | 15 ms |
| Sort by created or updated, first page | not measured | 11 to 12 ms |
| Text "alien", page | 824 ms | 70 ms |
| Text "alien", count (1,000 matches) | 13,949 ms | 52 ms |
| List `?q=alien` (`GET /node`) | 654 ms | 59 ms |
| Rating, descending | 450 ms | 255 ms |
| "director 42" within a type, page / count | 433 / 10,472 ms | 487 / 476 ms |

The "after" counts above are the uncapped counts; the API now stops counting at 1,000, which took the no-filter count from 62 ms to 4 ms.

Other pages (id order, type, containment filters, tags) were already 10 to 25 ms. At 10,000 items every page was under 60 ms except sort by name (217 ms before) and text (759 ms before).

**Known limits:** sorting on a field (rating) still scans. A free-text query with many candidates still pays for the exact check ("director 42" within a type, about 500 ms at 100,000 items). The Python fold (`text_match.fold`) and Postgres `lower(unaccent(...))` disagree on 878 characters of the Basic Multilingual Plane: letters `unaccent` transliterates without a combining mark (Æ, Œ, Ø, Ł, Đ, Þ, Ð, ı, Ħ, Ŧ, Ŋ, ĳ and their lower-case forms) and symbols such as ©, ½, « and ». Only the in-memory adapter, and so only tests, see the difference; `sort_key` also uses `lower` rather than `casefold`, so ß sorts differently there (the same difference existed before search).

Further known limits, left as they are for now:

- LIKE wildcards are escaped before `unaccent` folds the pattern, so fullwidth `％`, `﹪` and `＿` become wildcards and `＼`, `﹨` and `∖` become escapes in the text condition, field `~` and `GET /node?q=`. False positives only; the fix is to escape after folding, in SQL.
- The search cursor appears in a DEBUG log line (`searching nodes`); at DEBUG the SQL echo logs the same bound values anyway.
- `postgresql_ops` on the three trigram expression indexes in `models.py` is ignored when the models compile; the migrations are authoritative, and nothing builds the schema from the models.
- For a schema property without an explicit `x-menagerist.kind`, the backend infers fewer kinds (text, choice, date, number, boolean, multichoice) than the frontend, so a hand-made type can offer an operator the server rejects with a 400. Every schema the editor or a pack writes carries an explicit kind.

**Values the database cannot hold.** The parser rejects NaN, infinities, numbers outside the float8 range and text with lone surrogates with a 400 (`InvalidQueryError`), and reads only plain ASCII digits in relative and partial dates. A date operand must be `YYYY-MM-DD`, because stored dates are compared with it as text. A stored number outside the float8 range is treated as the wrong type (no match, sorts last) by both adapters, so one bad value never errors a whole query. A condition whose field, or a field it references, is gone is listed in `ResolvedQuery.stale` and matches nothing, whatever other conditions name the same field.

**`EXPLAIN` findings:** containment forms (choice, yes/no, multi-choice, tags) and name or description trigram searches use the GIN indexes, though at 20,000 items the planner prefers the owner index until a condition is selective. Number, date and partial-date comparisons, and sorting on a field, scan. That is acceptable at the sizes expected and is the first thing to measure if search feels slow; an expression index per hot field is the next step.

## Operators per field kind are one shared table (2026-10-15)

**Decision:** which filter operators each field kind supports lives in `shared/contracts/query-operators.json`. The backend table (`KIND_OPERATORS` in `field_kinds.py`) and the frontend table both have to equal it, and both test suites read the file.

**Why:** the backend has no field-type descriptors of its own (those exist only in the frontend registry), so there is nowhere on the server to declare operators per type. A shared fixture is the same device as the existing regex conformance file: it fails whichever side changes alone. The query shapes fixture (`query-shapes.json`) does the same for the structure of a tree, and `query-kinds.json` for the kinds that can compare with another field or be sorted on, and the operators that take no value.

**Not chosen:** a backend `FieldTypeDescriptor` (a second registry to keep in step with the frontend one) and generating one side's table from the other at build time (it hides the drift until the build).

## `not_in` is the type-scoped complement of `in` (2026-10-16)

**Decision:** a field condition can use `not_in` ("is not one of") wherever `in` is offered: text, link, email, phone and choice. It takes the same value as `in` (a list of 1 to 50 operands, each text up to 200 characters) and is parsed by the same code. It matches items of the condition's type for which `in` would not: the value is missing, of the wrong JSON type, or not in the list. Items of other types never match, exactly as for `!=`. Text kinds fold case and accents and a choice compares exactly, as `in` does.

**How:** `COMPLEMENT_OPERATORS` in `graph/domain/query.py` maps each complement to its positive form (`!=` to `=`, `not_in` to `in`). Both adapters evaluate the positive form and negate it inside the type check, so the two operators share one rule.

**Consequences:** a stale field still matches nothing under `not_in`, and so everything under a `not` group. On a table column, `not_in` means no row holds a listed value (as `!=` means no row equals), so an item with no rows matches. `not` over `not_in` within the type is `in`.

**Not chosen:** reading `not_in` as "every row is outside the list" for table columns (it would differ from `!=`) and an item-wide complement that also matched other types (it would differ from `!=` and make `or` across types surprising).

## Conditions on an item's own fields are addressed by key and kind (2026-10-16)

**Decision:** a field condition names either an item type (`type`) or a field kind (`field_kind`), never both and never neither. A per-item condition (`{"kind": "field", "key": "signed", "field_kind": "boolean", "op": "=", "value": true}`) applies to an item whose own `extra_schema` overlay declares that key with that kind and has not archived it. The value test is the existing one on `attributes[key]`. The change is additive, so there is no query version bump. Per-item conditions cannot use a table column (`sub_key`) or a field reference (`ref`), and there is no per-item sorting.

**Scope predicate:** `extra_schema IS NOT NULL AND extra_schema @> {"properties": {key: {"x-menagerist": {"kind": kind}}}}`, with archived fields excluded. The `IS NOT NULL` guard keeps the predicate from ever being NULL, so negating it is safe, and it keeps the predicate usable by the index. The check is on the item's own overlay, not on its type. The spec's claim that a per-item key cannot clash with a type key holds only per item: a `weight` field on a Game type and a Film item's own `weight` field are different fields, and the item's own overlay decides, so a type field can never match a per-item condition (the e2e test seeds a type with the same key and value to prove it). An item with no overlay never matches and never errors.

**Rulings:**

- **R14:** only fields with an explicit `x-menagerist.kind` are filterable per item, because `@>` containment needs the kind written down. Overlays made through the editor or by promotion always carry one; a field in an overlay made through the API without a kind is still found by text search only.
- **R15:** no stale warning. With no item declaring the field the condition just matches nothing, and the builder flags a key that is missing from the listing ("No item has this field.").
- **R16:** no table columns, field references or sorting per item.
- **R17:** the listing carries no option list, so a per-item choice or multi-choice field takes typed text in the builder. Adding options to the listing would remove the cost.

**Negation:** bare `not` around a per-item leaf is plain negation, as around a typed leaf, so it includes items that lack the field. Scoping comes from `!=` and `not_in`, which match only items that declare the field: "Signed != yes" never returns items with no such field.

**Index:** a partial GIN index `ix_nodes_extra_schema_gin` (`jsonb_path_ops`, where `extra_schema IS NOT NULL`) serves the containment test. `EXPLAIN` on the scope predicate shows a bitmap index scan on it when the condition is selective; a field most items declare may use the owner index or a sequential scan instead.

**Listing:** `GET /node/item-fields` returns the per-item fields in use as `{key, kind, label, count}`, one row per key and kind (the same key with two kinds gives two rows), for the actor's own items, archived fields excluded. It returns at most 200 rows, most used first and then by key. The label is the most common non-empty JSON Schema `title` in the group (ties by title), falling back to the key.

**Not chosen:** resolving per-item keys through the type (no type is involved) and a server-side stale-field warning (it would need a scan of every overlay on each search).

## Smart collections: a stored search, resolved through bridges (2026-10-17)

**Decision:** a collection has a `kind`, `manual` or `dynamic` (a smart collection). A smart collection stores a `definition`, the phase 1 condition tree (`{v, where, sort}`), as JSONB. The `collections` module treats it as opaque: it never parses or evaluates it. Members are not stored; they are whatever the search matches for the viewer, so they are always current.

**Rationale:** the query engine lives in `graph`, and the two modules must not import each other. Validation and resolution therefore go through ports that `entrypoints/api/shared/bridges/` implements over graph use cases, the same pattern as `ItemLookup` and `CollectionMembers`: `collection_definitions.py` (validate a definition and report warnings), `collection_items.py` (count matches, capped or exact) and `collection_members.py` (resolve a collection to a manual id set or a smart definition). Bridges now live in `shared/bridges/` and HTTP plumbing (middleware, conditional requests, problem responses) in `shared/http/`, so `shared/` keeps only authorisation and composition concerns. The access scope is applied last inside graph's repository, so a saved query never reaches another person's items, however it is reached.

**Rulings:**

- **R18:** the kind is fixed at creation. There is no manual-to-smart conversion; the data model would allow one later. Adding or removing items on a smart collection, and giving a manual collection a definition, are 409s (`CollectionKindError`); the kind is checked before the definition, so a manual collection given any definition (even a malformed one) is that 409, not a 400.
- **R19:** `GET /node?collection=<smart>` orders by id with the existing id paging and ignores the saved sort. The collection page runs `POST /node/search` with the stored definition so the saved sort applies.
- **R20:** a smart collection's `item_count` is the capped search count (`TOTAL_CAP`, 1,000) with an `item_count_capped` flag; cards and lists show "1,000+". `GET /collection/{id}/count` returns the exact, uncapped count (scoped to the caller, 404 for another owner's), and the collection page fetches it automatically in the background when the figure is capped, with a **Count exactly** retry if that request fails.
- **R21:** the definition is stored exactly as the client sent it once it parses and validates; nothing is rewritten, so relative dates stay relative. The parser rejects unknown keys (on the query, groups, every condition kind and sort keys) and names them with the path of the object, so what is stored is exactly what was validated; the browser decoder drops unknown keys, so only the server is strict. Before it reaches the checker, a definition over 32 KiB as JSON, nested deeper than 12 levels, or holding a NUL character, text that is not valid UTF-8 or a non-finite number is also refused. An invalid or over-limit definition is a 400 naming the path of the first bad condition. A definition stored before these limits that breaks them is shown as `definition: null` with a warning rather than failing the list. A definition that no longer validates when read (a field or type was removed) degrades to "matches nothing" plus warnings, never an error page.
- **R22:** `GET /node?collection=<smart>` keeps an exact `Total-Count`, as plain `GET /node` does. Only the collection card count is capped. Cost: an API client listing a huge smart collection through this route pays for an exact count; revisit by capping with a flag header.
- **R23:** collection slugs stay unique per owner, not global, so the id remains the canonical, always-resolvable form. Every `/collection/{id}` route accepts an id or a slug (scoped to the caller; another owner's slug is the same 404 as an unknown one), `PATCH` takes `slug` or `regenerate_slug` (both together is a 400), a taken slug is a 409, and a UUID-shaped slug, or one over 120 characters, is refused so a path segment is never ambiguous and the unique index row stays small. A concurrent rename onto a slug just taken is a 409 too (the repository maps the index violation). A slug change keeps no history: the old slug stops resolving, links by id keep working. The page replaces an id address with the slug (no extra history entry, and the query string and hash are kept). Collections only.
- **R24:** opening a smart collection is read-only. The search box, type select and ad-hoc filters narrow the results by ANDing onto the saved conditions and live in the address (`?f=`, `?q=`, `?type=`), so they can be shared and reloaded. A narrowed view can be saved as a new smart collection or, after a confirmation, overwrite the collection's definition; **Edit conditions** has explicit Save and Cancel. Both save actions are disabled with a reason when the combined tree exceeds the depth or condition limits or the text exceeds 200 characters. The saved definition is never edited implicitly.

**ETag:** a manual collection's ETag extra is its item count, unchanged. A smart collection's is `count:capped:hash`, the capped count, the capped flag and a hash of the sorted warnings, because `updated_at` does not move when items start or stop matching. Above the cap the body and ETag stay the same. `If-Modified-Since` is skipped for smart collections (only `If-None-Match` can give a 304); `Last-Modified` is still sent and `PATCH`'s `If-Unmodified-Since` is unchanged.

**Parameter ceiling:** a manual collection used to filter the item list with an `IN (ids)` list, bounded by the 32,767 bind-parameter limit; it now binds one array (see "Collection, media, description and name conditions"). A smart collection is resolved by the search engine and counted in SQL, with no id list, so it has no such ceiling.

**Known limits:**

- The in-memory `count_matching` does not evaluate conditions; it counts every live item. Tests that need real counts for a smart collection use the Postgres bridge tests.
- The definition checker runs as `SYSTEM_ACTOR`, because validation needs the item types and not an owner's data; the scope is still applied to every count and listing.
- Fixed in the frontend: the collection page addresses every call by id once the collection has loaded, so the ETag cache (keyed by path) holds one entry per collection and definition saves carry `If-Match`.
- "Save as new, linked to this collection" was built with the "in collection" condition (2026-10-23).
- Not chosen: converting a collection between kinds, a slug history, and an in-process cache for the exact count (to add only if a benchmark shows the need).

## Device details captured at sign-in, frontend labelling with bowser (2026-10-17)

**Decision:** Sessions store `user_agent` (truncated to 256 characters), `client_ip`, `client_platform` (truncated to 64 characters), and `client_mobile` captured once upon session creation. The API returns these raw values, and the frontend derives user-facing labels ("Firefox on Linux", "Chrome on Windows") using `bowser`.

**Rationale & Key Choices:**
- **`bowser` over `ua-parser-js`:** `bowser` is licensed under MIT, making it fully compatible with Menagerist's Apache 2.0 licence. `ua-parser-js` 2.x is licensed under AGPL-3.0-or-later, which is incompatible with Apache 2.0 and excluded from this project.
- **Client Hints for platform and mobile:** Low-entropy Client Hints (`Sec-CH-UA-Platform`, `Sec-CH-UA-Mobile`) are sent by default over HTTPS and localhost without requiring an explicit `Accept-CH` opt-in. Because Chromium freezes OS versions in user-agent strings, Client Hints provide the accurate source for platform and form-factor hints. Browsers that do not send Client Hints (Firefox, Safari) fall back to `bowser` user-agent parsing.
- **No fingerprinting:** Canvas, font, audio, or hardware fingerprinting and high-entropy Client Hints (such as device model) are intentionally avoided to respect user privacy and avoid brittle heuristics.
- **Sign-in address only:** Tracking the latest IP address on every request would require a database write on every single authenticated request, adding write contention and unnecessary tracking. Recording only the address at sign-in keeps request overhead minimal while providing sufficient device context.
- **Current device protection:** Ending one's own current session through the devices API is refused with a 409 Conflict. Sign-out has its own dedicated flow that also clears authentication cookies and prevents accidental lockouts.

**Not chosen:** Parsing user agents on the backend (adds runtime dependencies and container bloat when the frontend can resolve labels on display) and tracking latest IP addresses per request (adds database write amplification and privacy degradation).

## Backend tests run in parallel with pytest-xdist (2026-10-18)

**Decision:** `poe test-backend` and `poe test-backend-integration` (hence `test-backend-all` and `coverage`) run with `-n auto --maxprocesses=6 --dist loadscope`. `pytest-xdist` is added to the backend dev dependency group. The flags are in the `poe` tasks, not in `addopts`, so targeted and IDE runs stay serial; `-n 0` or `PYTEST_XDIST_AUTO_NUM_WORKERS` changes the worker count.

**Rationale:**
- **Small dependency:** `pytest-xdist` (with `execnet`) is dev-only, pure Python, adds nothing to the Docker image and falls under the existing Renovate "python dev dependencies" group. The suite takes roughly 10 minutes serially (3,780 unit and 586 integration tests), which is the main cost of every `poe coverage` run.
- **`loadscope`:** it keeps a module's tests on one worker, which protects module-scoped fixtures and the Postgres state a module builds up. `worksteal` measured the same on two cores (unit 421 s against 426 s), so the safer option wins.
- **One container per worker:** the session-scoped `postgres_container` fixture already runs once per worker process, so each worker gets its own container, database and migrated schema. Nothing hard-codes a database name, port or shared path, and the worker cap bounds the number of containers.
- **Coverage:** pytest-cov combines worker data; per-layer totals before and after match to the decimal (domain, application and shared kernel 100.00%, adapters 98.62%, platform 94.43% combined).
- **Measured on 2 cores (`nproc` = 2):** unit 610 s serial, 426 s parallel (1.43x); integration 506 s serial, 373 s parallel (1.36x). Unit tests are CPU-bound, so two cores cannot do much better; integration is partly waiting on Postgres. Six workers on six real cores should scale closer to linearly for the unit suite, plausibly 3x to 4x (an estimate, not a measurement).

**Consequence:** the unit suite ran in parallel four times with no failures. The integration suite failed once in four parallel runs: `test_adding_twice_stores_one_row` counted every row in `collection_members`, which other modules sharing the worker's database had left committed, so it only passed when it ran before them. It now counts the rows of its own collection. This is the only test that needed fixing. New tests must not depend on module order or write to fixed paths, ports or database names. Each integration worker holds a Postgres container, so memory use grows with the worker count.

**Update (2026-10-18): configurable workers and a faster frontend suite.**
- `--workers N` (`-w N`) on `poe test-backend`, `test-backend-integration`, `test-backend-all`, `test-and-status`, `coverage` and `test` (also `test-frontend`) sets the worker count. Backend default `auto` (one per CPU), `0` serial; the `--maxprocesses=6` default was dropped, so a many-core machine may want `-w 4` because each worker starts a Postgres container. `test-backend` is now a `cmd` task (it was `shell`) so the value expands without interpreter-specific syntax. `test-frontend` passes it to vitest as `--maxWorkers` only when given.
- **Vitest `isolate: false`, adopted for files that are safe to share.** Measured on 2 cores (1,684 tests, 70 files): default 206 s (`--maxWorkers=1` the same, so the default is already one worker here), `--pool=threads` 216 s, `isolate: false` for every file 27 to 31 s but with 73 to 90 failures. The failures came from module state shared between files: `registry.test.ts` cleared the field-type registry that other files rely on (fixed by restoring it in `afterAll`), and files using `vi.mock('$lib/api/client', ...)` leaked their mock into other files through cached modules (not fixable per test). So `vitest.config.ts` runs two projects: files that call `vi.mock`, `vi.doMock`, `vi.stubGlobal`, `vi.stubEnv`, `vi.resetModules`, `vi.useFakeTimers` or touch `globalThis.` (found by scanning the test sources) stay isolated, and the rest run with `isolate: false`. The suite then takes about 67 s (five runs: 67, 68, 67, 68 and 77 s), always 1,684 of 1,684 passing. The `--pool=forks` default was not re-measured separately (it is vitest's default).
- **Consequence:** a test that changes module-level state in a shared file must restore it; tests that mock or stub globals are routed to isolation automatically by the scan.

---

## Direction: roles as data, implied permissions

**Direction (2026-10-10), not built:**

- Permissions stay fixed in code, per module, as enums. Each module declares an `IMPLIES` catalogue (holding one permission also grants others) and the grant is expanded to its transitive closure when an actor's permissions are loaded. Grants only; there are no denies. *Superseded 2026-10-22: the catalogue is now an `implied()` method on each enum; see "Content permissions as enums with `implied()` (2026-10-22)".*
- Roles become data later: a roles table where admin means everything, member means a default set, and people can define their own roles. That replaces the `Role` enum and `MEMBER_PERMISSIONS`.
- Resource-specific access (sharing grants on a particular item or collection) is not a role permission. It is deferred to Stage 2 and goes through `AccessPolicy`.

---

## Follow-ups: accounts and ownership

Open items from Stage 1; none is scheduled.

- **A universal `handle`/`_handle` template for all use cases** *(done 2026-10-22: every use case has a final `handle` and implements `_handle`, with `self.scope(actor)` for content)*; a single place for a future activity log is still open.
- **Combined Authorised and Scoped handlers** when one use case needs both. Example: Stage 3 public-link creation needs a permission gate and an owner scope.
- **Per-person favourites** once sharing exists (an existing follow-up: the favourite flag is on the item, so it would be shared).
- **Make the owner columns NOT NULL** (items, connections, files, example installations) after every deployment has claimed its data.
- **Open idea, decided against (2026-10-11):** a readiness `warn` for "setup not completed" (see the 2026-10-11 entry).
- **Stage 2:** sharing, through a sharing `AccessPolicy` and a wider SQL scope.
- **OIDC and trusted-proxy sign-in** as further `Authenticator` adapters.

---

## Verified logical backups and portable user archives (2026-10-19)

Backups belong to a separate bounded context, with shared application use cases for CLI, API and future schedulers. A logical NDJSON snapshot works in the distroless image without adding PostgreSQL client binaries and supports owner filtering for user exports. Database adapters reflect the live schema so pre-migration snapshots can record the revision that actually exists. Sessions and sign-in attempts are excluded; user archives also exclude account credentials.

Archives and private staging files live on the persistent backup volume rather than the restricted `/tmp` tmpfs. Each member has a checksum, and instance archives have a separate compressed-byte digest. API uploads stream raw archive bodies without multipart buffering. Verification and revision checks precede restore writes; media compensation participates in the transaction so a failed restore leaves no partial database changes.

Instance restore is exposed through the CLI and a public first-run route guarded by the same setup lock as first-administrator creation. There is no authenticated live restore route. CLI user transfers require an explicit account UUID, use that account as the scoped actor and keep archives in a private owner namespace.

Automatic pre-migration backup was opt-in at first and became the default on 2026-10-22 (`MENAGERIST_BACKUP_BEFORE_MIGRATE=true`; set it to `false` to opt out), because a failed upgrade is the moment a restorable archive matters most. Both migration entrypoints take a verified archive only for an existing schema with pending upgrades; a backup failure stops DDL. `--no-backup` is the explicit opt-out. Pre-migration retention is separate from ordinary backup retention, and restoring an old archive requires a database at its recorded revision.

---

## CSRF protection from browser request headers (2026-10-20)

Supersedes the double-submit parts of the identity section (the readable `menagerist-csrf` cookie and `X-CSRF-Token` header) and of the interactive-docs entry (Swagger adding that header).

A cookie-name mismatch between frontend and backend made every signed-in unsafe request fail with 403 `csrf_failed`. Rather than align the names, the token is gone: `verify_csrf` now checks headers that browsers set themselves, and the session cookie is `SameSite=Strict`.

- **Rule.** A POST, PUT, PATCH or DELETE that carries the session cookie must come from the app's own pages. `Sec-Fetch-Site: same-origin` allows it and `cross-site` refuses it. Otherwise (`same-site`, `none`, or no header, as on plain-HTTP installs) `Origin` must equal the app's own origin as seen after the trusted-proxy wrapper; a missing, `null` or malformed `Origin` is refused. The check fails closed. Safe methods and requests with no session cookie are not checked. A refusal is 403 `csrf_failed`.
- **Why not a token.** Go's `http.CrossOriginProtection` and Datasette take the same approach and OWASP names Fetch Metadata as the primary signal. Double-submit can be passed by anyone who can plant cookies (a sibling subdomain, plain HTTP). It also removes the cookie name that had to be agreed between stacks. A session-bound token can be added later as an extra layer if OIDC with `SameSite=Lax` or a cross-origin cookie SPA ever needs it.
- **CORS plays no part.** CORS never carries credentials here, so a listed `MENAGERIST_API_CORS_ORIGINS` entry gets no extra trust for cookie requests (it still counts on the public sign-in and setup routes, which keep `refuse_cross_site`).
- **Removed.** The CSRF cookie, `X-CSRF-Token`, `MENAGERIST_CSRF_COOKIE_NAME` (a leftover value is ignored) and their frontend and Swagger plumbing. The Swagger page still sends same-origin credentials and strips the placeholder `Cookie` header, and now adds `Origin` to generated curl snippets (a forbidden header name for `fetch`, so only the snippet shows it).
- **Cost.** Scripts that use the session cookie must send `Origin: <the server's origin>`; API tokens (future) will avoid the cookie, and the check is then skipped for requests a bearer token authenticates. *Built 2026-10-23: see "Personal access tokens (2026-10-23)".*
- **Follow-ups.** A `__Host-Http-` session cookie with a strict reader and WebKit/Firefox e2e tests; tighter CORS lists and an open-CORS warning.

### Explicit CORS lists and an open-CORS warning (2026-10-21)

The CORS middleware names its methods (GET, POST, PUT, PATCH, DELETE), request headers and exposed response headers instead of `*`, so a preflight for anything else gets 400, and `ETag` and `Retry-After` are now readable by a listed origin. Credentials stay off, so this narrows what a listed site may ask for and does not change who can use a session. A test checks every route method and every header declared in the OpenAPI schema against the lists. `MENAGERIST_API_CORS_ORIGINS=*` logs a start-up warning and shows as a warn-only `cors:configuration` readiness check; it is a fixed setting, so it does not use the runtime proxy signals. `Authorization` joins the request headers when API tokens arrive.

### `__Host-Http-` session cookie and strict reader (2026-10-21)

Over HTTPS (a `Secure` cookie) the session cookie is `__Host-Http-menagerist-session`; over plain HTTP it keeps the plain name. The prefix makes browsers that support it (Chrome and Edge 140+, Firefox 143+) refuse a same-named cookie set by a sibling subdomain, a plain-HTTP page or page script. Safari does not enforce it yet, and a disguised name is not stopped by any browser, so the reader is strict too: exactly one cookie with the exact name, read from the raw `Cookie` headers, else no session. A duplicated cookie or a name that only matches once latin-1 spaces are trimmed (Starlette's own parser trims them and keeps the last duplicate) gives no session, so a tossed cookie can sign someone out but not in. `verify_csrf` reads the cookie the same way. Switching between HTTP and HTTPS means signing in again.


---

## Declared access stances behind one guard (2026-10-22)

*Superseded in part 2026-10-22: `Shared` is removed and `Content` now carries a permission; see "Content permissions as enums with `implied()` (2026-10-22)".*

**Decision:** every use case declares who may call it with `access = ...` (`Public`, `System`, `OwnAccount`, `Shared`, `Content`, `Requires(permission)`), and the final `handle` on the `UseCase`/`CommandHandler`/`QueryHandler` bases checks it through one `AccessGuard` before calling `_handle`. The guard also holds the ownership rules (`scope_for`, `assert_can_view/modify/delete`) that the `AccessPolicy` port held. The `Scoped*` and `Authorised*` bases, `AccessPolicy` and `get_access_policy` are gone. No behaviour changed for any caller.

**Rationale:**

- "Plain" handlers meant three things (public flows, own-account actions, the shared catalogue), and a use case could not need both a permission and an ownership filter through the bases. A deliberately open use case looked the same as a forgotten check.
- API tokens need "session only" and "grantable" as first-class ideas. With one guard, that changes one place, not every handler.
- Enforcement is by tests rather than the type system: an architecture test fails a concrete use case with no stance, and the `Public`, `System`, `Shared` and `Content` sets are pinned by name (the `Shared` pin is gone; see the 2026-10-22 entry), so widening access shows up in review. `Requires` is not generic over the permission type; a test checks that its permission is catalogued and belongs to the use case's own module.

**Choices worth keeping:**

- **`Shared` stance** (*superseded 2026-10-22: removed, those use cases are `Requires`*). Item types, connection types, presets and query validation are open to any signed-in actor. Making them `Requires(permission)` later is a one-line change per use case, done with the tokens plan.
- **`Content` and `Shared` carry no permission yet** (*superseded 2026-10-22: both now carry one and `MEMBER_PERMISSIONS` is the content set*). `MEMBER_PERMISSIONS` is empty and no scoped use case checked a permission, so one here would lock members out.
- **The anonymous actor is refused before any permission lookup** for every stance except `Public`, because `RoleAuthorisationAdapter` treats any non-admin, non-system actor as a member and a later non-empty member grant would otherwise reach it.
- **`System` is for background and CLI jobs** and admits only the system actor. `OwnAccount` refuses the system actor.
- **`Public` use cases still take the guard**, for one constructor shape.
- **`PermissionAwareRoute` documents only `Requires` stances** (*now `Requires` and `Content`*), and a test pins the set of documented operations, so the migration could not add or drop an OpenAPI permission.

**Tradeoff:** a stance is exclusive. A use case that needs both a permission and an owner scope (public-link creation in a later stage) has no stance for it yet.

---

## Content permissions as enums with `implied()` (2026-10-22)

**Decision:** every owned-content and catalogue use case now has a real permission, held by all members. Permissions are members of per-module enums deriving `PermissionEnum` (`shared_kernel/permission.py`), and each enum owns its implications in an `implied()` method; the central `IMPLIES` dicts are gone. `Content(permission)` and `Requires(permission)` both require a permission, and the `Shared` stance is removed (its use cases are `Requires`). 14 member permissions were added to the 16 admin ones, 30 in all, and `MEMBER_PERMISSIONS` is exactly that content set. No behaviour changed for any user, client or CLI command.

**Rationale:**

- API tokens need something to carry. A token holds a subset of permissions, so content access had to be expressed as permissions before tokens could be limited to "read only".
- An enum that owns `implied()` keeps a permission and its implications in one place, so adding a permission cannot forget the catalogue entry.
- Pins moved from "who is open" to "what each use case needs": `tests/architecture/test_permission_mapping.py` pins every use case's permission, the catalogue of 30 and that every non-admin permission is a member permission. `test_no_direct_ownership_checks.py` keeps ownership comparisons inside `AccessGuard`, so sharing later changes one place.

**Choices worth keeping:**

- **The strings are a public contract.** Permission strings appear in OpenAPI (`x-required-permission`), tests, and, since 2026-10-23, in stored token grants (see "Personal access tokens (2026-10-23)"), and soon in roles. They are never renamed. A permission that proves too coarse is split by making the coarse one imply the finer ones, which needs no data migration.
- **Coarse first.** The vocabulary is user-facing (`graph:item:*`, `graph:type:*`, `media:item:*`, `collections:collection:*`, `presets:preset:*`, `examples:pack:read|install`, `backup:own_data:export|import`), one read and one write per resource. Existing admin strings such as `graph:node_type:delete` keep their names. Each write or install implies its read counterpart.
- **Member grant equals the content set.** Members hold every content permission, so nothing changes for them; the permissions only bite once a token or a data-driven role holds fewer. Export, import and pack install are their own permissions so a "read only" token never includes them.
- **`Content` is the only stance that may call `scope()`.**
- **Composite use cases need every inner permission.** `UploadAndAttachMedia`, `PromoteExtraSchemaField` and `ImportUserArchive` call other guarded use cases; the tokens plan records the inner permissions.
- **One allow-listed exception:** `install_example_pack.py` still compares ownership directly until sharing lands.

**Tradeoff:** a permission per resource is a wide vocabulary to maintain, and a mapping pin means every new use case needs an edit in review. That friction is the point.

---

## Personal access tokens (2026-10-23)

*Supersedes the Phase 4 sketch in `docs/superpowers/plans/2026-10-20-api-tokens-and-permissions.md`; the task plan is `docs/superpowers/plans/2026-10-23-api-tokens.md`.*

**Decision:** a signed-in person can create personal access tokens (`mnst_<id>_<secret>`) that act as them with a chosen subset of their permissions, for scripts and for Swagger. Tokens live in the `identity` module (`ApiToken`, `ApiTokenRepository`, `ApiTokenGenerator`, use cases, SQL and in-memory adapters). The secret is shown once and stored as a hash. Personal access tokens were chosen over OAuth: a person issues a credential to themselves, which needs no authorisation server, consent screen or client registration. OAuth is added only if third-party apps appear; verification sits behind `get_current_actor`, so a second bearer format would not touch the guard.

**Intersection model:** `Actor.grants` is `frozenset[str] | None`; `None` means a session with no ceiling. `RoleAuthorisationAdapter.effective_permissions` returns the owner's permissions intersected with the token's expanded grants, so a token never exceeds its owner, loses a permission the moment its owner does, and an administrator's token holds no admin permission unless one were grantable. The guard and every use case are unchanged. Grant strings that name no catalogue permission add nothing.

**Session-only stances:** `OwnAccount` is refused for token actors (`RoleAccessGuard`), so a token cannot create, list, rotate or revoke tokens, change the password or manage devices. Those routes read only the cookie, so a request carrying a bearer header gets a 401 there. `Public` and `System` are unchanged.

**Rulings (R1 to R12) and their costs:**

- **R1 limits (settles Q5):** default lifetime 90 days, maximum 365, at most 20 active tokens per user, expiry mandatory, `last_used_at` written at most once a minute. Settings `api_token_default_days`, `api_token_max_days`, `api_tokens_per_user`. Cost: three values to tune.
- **R2 grantable set:** the content permissions except `backup:own_data:export` and `backup:own_data:import` (`TOKEN_GRANTABLE_PERMISSIONS` in `entrypoints/api/shared/authorisation.py`); no admin permission. A leaked token cannot mass-export or overwrite an account. Cost: widening is a one-line edit and a changed pin.
- **R3 revoke deletes:** the row is removed, as sessions are; a revoked and an unknown token are both a 401. Cost: no audit trail beyond log lines.
- **R4 password events:** `ChangePassword` and `ResetPassword` delete the user's tokens, so a password change signs out everywhere, tokens included. Cost: scripts need a new token.
- **R5 schemes:** only `Authorization: Bearer` is a token credential; another scheme is ignored and the cookie path runs. An empty or malformed bearer value is a 401.
- **R6 bearer is authoritative:** with a bearer header the cookie is never read, and a bad token never falls back to it. This lives in `get_session_token`, which returns `None` beside a bearer header, so every cookie-only route refuses such a request; that is what makes skipping CSRF for bearer requests safe.
- **R7 disabled or password-expired owner:** refused as for a session (401 `invalid_token` for a disabled owner, `password_expired` otherwise).
- **R8 composites:** a composite use case needs every inner permission, pinned by a table test (`UploadAndAttachMedia`, `PromoteExtraSchemaField`, `ImportUserArchive`). Cost: a token with only `graph:type:write` cannot promote a field.
- **R9 no `WWW-Authenticate`:** the error handler has no per-exception headers. Cost: strict RFC 6750 clients get no hint.
- **R10 no admin view:** administrators cannot list or revoke others' tokens; disabling the user stops them. Cost: a later `identity:token:*` permission.
- **R11 CORS:** `Authorization` is not in `CORS_REQUEST_HEADERS`; there is no cross-origin browser client. Cost: one list entry later.
- **R12 rotation, no extension:** expiry is never extended. `RotateApiToken` keeps the name and grants, issues a new secret and expiry, and deletes the old row at once, so it does not count against the limit. As built, an expired token cannot be rotated (404), grants the owner no longer holds are dropped, and it is refused if none remain. Create and rotate need the password and share the sign-in-style throttle.

**Changed in the build:** request and response fields are snake_case (`expires_in_days`, `last_used_at`), the repository convention; `grants` is `list[str]`, so an unknown or unheld grant is a 400 rather than a 422; `GET /api/v1/tokens/grants` lists what the caller may grant; the `api_tokens` table is skipped by backups (as `sessions`); and the access log carries `token_id`, never the header or secret.

**Not done:** an admin view of others' tokens (R10), `WWW-Authenticate` (R9), the CORS `Authorization` header (R11), OAuth or refresh tokens unless third-party apps appear.

**OpenAPI documentation:**

- **Bearer is documented from behaviour.** `PermissionAwareRoute` derives the bearer scheme from `get_current_actor` and `TOKEN_GRANTABLE_PERMISSIONS`: a `Requires` or `Content` route accepts a token only if its permission is grantable, so admin-only, token-management and account routes list the cookie scheme alone. The planned per-permission flag was not needed. Swagger's Authorize dialog has a "Browser session" block and an API token block; the banner distinguishes session, token and both by calling `GET /api/v1/auth/me/permissions`.
- **Central error components.** `entrypoints/api/openapi_responses.py` adds shared `ProblemDetail` and `ValidationProblem` schemas and `components.responses` for 401 (with `invalid_token` where a token is accepted), 403, 404, 422 and 500, all `application/problem+json` with named examples. A route's own `error_response(...)` entry always wins.
- **Every error example must match its status** (`status` equals the response code, `type` from the exception's `problem_type`, a route-specific `instance`, no placeholders). `tests/entrypoints/api/test_openapi_response_examples.py` enforces it for every operation, so a new route needs accurate descriptions and examples.

**Tradeoff:** a wider surface to guard (a second credential, a table of secrets) and a few accepted costs above. Bearer-authoritative and session-only stances keep that surface from reaching account management.

## Removing an example pack purges what it created; exports skip deleted rows (2026-10-23)

**Decision:** removing an example pack hard-deletes what the removal removes: the item and the connections that touch it, collections and their memberships, and cover attachments with the assets and stored files only they used. Stored files go only after the transaction commits. Anything the person edited, connected to their own content or still uses is kept exactly as before, and item types and presets stay soft-deleted (their rows keep slugs reusable and other rows may still name them). The purge use cases are `System`-only, pinned in the stance tests and reachable from no route. Personal exports and restores ignore soft-deleted items, connections and collections.

**Rationale:**

- The old removal only set `deleted_at`, and the export selected rows by owner alone, so every install and remove added another copy of the pack to every later export. Nothing ever hard-deleted content, so the rows also never left the database.
- A pack can be reinstalled from the catalogue, so a soft-deleted copy has no value.
- Skipping soft-deleted rows in the export fixes the symptom for everything deleted by hand too, and matches the vocabulary tables, which already ignored them.

**Consequences:**

- Removal is no longer recoverable. No undo was ever offered.
- **Behaviour change:** an item a person deleted by hand is no longer in their export. A future "Recently deleted" view (restore, and purge on request) will need its own export rule; until it exists, hand-deleted content stays soft-deleted and nothing purges it automatically.
- Rows left behind by earlier removals stay as they are: no clean-up command was built, because none is needed for this deployment.
- A purge removes every connection touching the item, whoever owns the other end, so callers must first confirm the item has none of anyone else's; pack removal keeps such items.
- `media_assets` has no `deleted_at`, so the export cannot filter it; an asset attached only to a soft-deleted item is exported as an orphan, which is harmless.
- Not built, by decision: a retention purge of hand-deleted content (`data purge-deleted`), superseded by the planned "Recently deleted" view.

## Collection, media, description and name conditions (2026-10-23)

**Decision:** four condition kinds join the search and smart-collection tree, additively (`v` stays 1): `collection` ("in" or "not in" a list of collections), `media` ("has" or "has no" media, optionally an image or a document), `description` (contains, is empty, is not empty) and `name` (contains, is). `description` and `name` are plain graph conditions, matched like free text (case- and accent-insensitive, `%` and `_` literal). `collection` and `media` need data that other modules own, so graph gets a small port of external predicates (`ExternalConditions`, with `CollectionDefinitions` to read stored smart definitions) that `entrypoints/api/shared/bridges/` implements over the collection and media tables; graph never imports either module. The collections page also offers **Save as new, linked to this collection**.

**Rulings:**

- **R25:** foreign data enters through the injected port, not as pre-resolved id lists and not by graph importing foreign tables. The SQL form is an `EXISTS` subquery (attachments by `target_id`, memberships by `item_id`); the in-memory evaluator has its own sibling implementation. Not chosen: an `id = ANY(array)` of foreign ids, because "has no media" would ship an array as large as the library. Cost: the bridge is a second place that knows SQL shapes.
- **R26:** a manual collection resolves by membership rows. A smart collection is inlined at query-preparation time from its stored definition (depth limit 3, a visited trail, at most 50 expansions per query) and is resolved under the owner's visibility, so a smart collection referenced by another is evaluated the same way as on its own page. Anything not visible to the caller (another person's, deleted or unknown) is stale: it matches nothing, carries a warning, and is indistinguishable from an id that never existed.
- **R27:** `media` counts attachments of the item itself, from any attribute key, whose asset is `attached` (staged and orphaned assets do not count, nor do thumbnails) and owned by the caller. `type: image` is a content type starting `image/`, `type: document` is any other. There is no soft-delete column on assets; orphaned is the deleted state.
- **R28:** "Save as new, linked" stores `in collection <this>` AND the ad-hoc conditions (filters, search text, type). Deleting the parent later makes that condition stale: the child matches nothing and shows a warning.

**Semantics as built:**

- The wire form keeps `mode` (`any` or `none` for `collection`, `has` or `none` for `media`). The internal collection port has no mode: it answers "any of these manual collections", and graph composes `none` as NOT over the live targets (manual predicates and inlined smart groups).
- An all-stale leaf matches nothing in both modes: `not in` a deleted collection is not "every item", consistent with stale field conditions. With a mix, stale ids contribute nothing and `none` negates the live ones.
- Like other leaves, `not in collection` and `media: none` are plain negations and match items of any type.
- Cycles: saving a definition whose collection list reaches the collection being saved, directly or through other smart collections, is a 400 naming the path (`a > b > self`). A cycle that does not involve the saved collection, a chain deeper than 3 or more than 50 expansions degrade to stale plus a warning, at save and at read, never recursion or a 500. A stored smart definition that no longer parses makes that target stale.
- The access scope is still applied last, and the predicates filter by owner too, so a condition cannot reveal another person's items, collections or media (tested through search, counts, `GET /node?collection=` and saving).
- The picker leaves the collection being edited out, so the page cannot offer a self reference; other loops are refused by the server and the message is shown in the dialog.

**Performance (100,000 items, one owner, Postgres 18, tables analysed, median of 5):** the new conditions cost 30 to 80 ms for a page plus the capped count; media has AND a 5,000-member manual collection is the slowest combination at about 240 ms (two semi joins make the planner scan `nodes`; below the 300 ms threshold, so left). `EXPLAIN` shows `ix_media_attachments_target_id`, `media_assets_pkey` and `collection_members_pkey` used per candidate row. No index or migration was added. An earlier run on un-analysed tables measured 820 ms and 1.6 s for the manual and combined cases; those were not reproducible after `ANALYZE`, and autovacuum analyses after a real import. A rewrite of `collection_predicate` that moved ownership out of the correlated subquery measured no gain and was not applied.

**Parameter ceiling removed:** `GET /node?collection=<manual>` used `id IN (ids)`, one bind per member (about 340 to 560 ms at 5,000 members, and asyncpg refuses more than 32,767 parameters). `NodeRepository.list` and `count` now bind one array (`id = ANY(:array)`): 158 ms at 5,000 members, 124 ms with a type filter, no cliff, same semantics.

**Known slow spot (undecided):** `GET /node?q=` counts exactly with no cap, so a very common term (15% of items) costs about 0.9 s, nearly all in the unaccent recheck of the trigram hits; a rarer term is instant. It is older than these conditions. The `SearchNodes` path is capped and takes about 100 ms. Options: cap it with `total_capped` like search, or drop the exact total for `q`. Not changed, because it is an API decision.

**Save as new, linked:** offered on smart collection pages (alongside "Save as new smart collection" and "Update this collection") and on manual pages when the search text or type is set (the only ad-hoc narrowing a manual page has), where it is the only save. The dialog says the new collection always holds the items of this one that match, so it follows it. It is blocked, with a reason, when the combined tree would exceed the depth or condition limits or the text is over 200 characters.

**Frontend:** the decoder drops unknown keys (only the server is strict) and requires canonical UUIDs for collection ids. While the collection list loads, chips read "a collection" and rows do not claim deletion; a failed read shows "Could not load your collections." with Retry. A removed collection reads "Deleted collection" in chips and "a collection that no longer exists" in summaries.

**Tests:** one scenario table (`test_node_search_external.py`) runs on both adapters; `tests/e2e/smart-collection-conditions.spec.ts` covers the builder, saving, stale references, both linked saves, the cycle message, isolation through a second user and the picker error state.

**Known limits:** a chain of nested smart collections deeper than 3 is a warning, not a refusal; the picker loads all collections (paged, at most 20 pages of 50).

## Connection conditions (2026-10-24)

**Decision:** a `connection` condition joins the search and smart-collection tree, additively (`v` stays 1): `{"kind": "connection", "mode": "exists" | "none" | "to", "relationship"?: slug, "direction"?: "out" | "in" | "any", "item"?: uuid, "where"?: group}`. `exists` needs at least one live connection, matching `relationship` and `direction`, whose far item is live, in the caller's scope and satisfies `where` if given. `none` is the negation of the same test. `to` is `exists` with the far item equal to `item`, and takes no `where`. `exists` and `none` take no `item`. The far-end `where` may not contain another connection condition, and its conditions count towards the 50-condition limit. Connections are internal to `graph`, so unlike `collection` and `media` they need no external-predicate port: the SQL adapter compiles them to correlated `EXISTS` over `edges`, and the in-memory evaluator reads the in-memory edge store.

**Rulings:**

- **S2 (shape):** as above. Soft-deleted connections and far items never count, and neither does a connection outside the caller's scope.
- **S3 (direction):** `out` means this item is the source and `in` that it is the target. For a relationship type declared non-directional the direction is ignored and either end matches. With no `relationship`, `out` and `in` apply to the stored source and target literally. `to` with a non-directional relationship also ignores direction. Cost: one more rule to explain in the builder.
- **S4 (stale):** an unknown or deleted `relationship`, or a `to` item that is deleted or not visible, makes the whole condition false with a warning carrying its path, in every mode, so `none` over a stale relationship matches nothing rather than everything. The warning text is the same for deleted, foreign and unknown items, so it does not reveal existence. A stale field inside a far-end `where` is stale only inside that filter (nested warning path, such as `where.children[1].where.children[0]`): the filter matches no far item, so `exists` is false and `none` is true, because there is nothing to exclude. Under `not` the result inverts as for any stale leaf.
- **S5 (in-memory parity):** `InMemoryNodeRepository` reads the same edge store that `InMemoryEdgeRepository` writes, wired once by `build_in_memory_graph_repos`; constructed without edges it behaves as before. One scenario table (47 scenarios, plus warnings, paging and a bare repository) runs against both adapters, the Postgres run being `integration`-marked.
- **Far-end collections (Sam's decision):** a far-end `where` may use a `collection` condition, including a smart collection that itself has connection conditions. That gives a second connection level through the back door, but it is bounded by the existing nesting limit (3) and expansion cap (50), both adapters agree (tested), and conditions inside an inlined collection do not count towards the caller's 50, because the limit applies to each parsed definition.
- **`to` and the far item:** `to` is checked at resolution (the item must be visible) and does not join the far node in SQL.

**Performance (Postgres 18, 100,000 items, 300,000 edges, one owner, about 30% of items without edges, best of 3):**

| condition | first page (51) | count capped at 1,001 | exact count |
|---|---|---|---|
| exists | 0.023 s | 0.049 s | 3.4 s |
| exists, relationship, out | 0.020 s | 0.198 s | 0.39 s |
| none | 0.030 s | 0.148 s | 0.79 s |
| none, relationship | 0.030 s | 0.145 s | 0.67 s |
| exists, far-end tag (14% of items) | 0.56 s | 0.70 s | 2.3 s |
| exists, far-end type | 0.60 s | 0.61 s | 2.3 s |
| exists, far-end name = (selective, 8 hits) | 1.6 s | 4.2 s | 4.3 s |

`EXPLAIN` shows `ix_edges_source_id` and `ix_edges_target_id` used as nested loops for `exists`, and index-driven merge anti joins for the first page of `none`; no scan per item. A far-end filter that is not selective becomes a hashed sub-plan. The slow case is a selective far-end filter (`name =` matching 8 items): the planner sometimes starts from the 300,000 edges instead of the filtered far set, costing about 1.6 s for a first page. Partial composite indexes on `(source_id, target_id)` and `(target_id, source_id)` where `deleted_at IS NULL` changed no timing, so no index or migration was added. Typical libraries are far smaller.

**Counting:** the exact, uncapped count for `exists` (3.4 s here) is slow, but the app never asks for it on the hot path: it uses the first page and the count capped at `TOTAL_CAP` (1,000), and fetches the exact figure in the background only for display. Revisit if an uncapped count is ever needed synchronously.

**Frontend:** the builder gains a Connection row (relationship, direction, an item picker for "Is connected to", and "Where the linked item..." as a nested group that cannot hold another connection). The picker searches on the server (`GET /node?q=`) rather than loading every item. Chips and summaries read "Has a linked item via Directed by", "Has no linked item" and "Connected to Casablanca"; user-visible text says connection, linked item and relationship, never node or edge. `shared/contracts/query-shapes.json` carries 11 valid and 16 invalid connection cases for both parsers.

**Tests:** `test_query_connection_scenarios.py` (both adapters), `test_query_connection.py`, `test_query_resolution_connection.py`, `frontend/tests/query-connections.test.ts`, and `tests/e2e/smart-collections-connections.spec.ts` (building and saving "films with no viewing", connected to an item, a far-end type filter, a deleted relationship type, and isolation through a second user).

## Smart collections in example packs (2026-10-24)

**Decision:** pack format version 6 lets a collection carry a `definition` (a smart-collection query tree) instead of `items`. Giving both, or neither, is a parse error, as is `definition` in a file below version 6. Installing creates a `kind=dynamic` collection with the definition as given, in the same step as manual collections, after item types, relationship types and items exist so validation sees them.

**Rulings:**

- **S6 (portable definitions):** a pack definition may name only things a pack can name stably: item type slugs, relationship slugs, field keys, and the tag, text, type, date, favourite, name, description, media and connection `exists` / `none` conditions. The parser rejects a `collection` condition and a connection `item` (they are ids), with the path in the message. It does so by walking the JSON generically, because `examples` cannot import `graph`. Everything else is checked at install by the same definition checker `POST /collection` uses (`GraphDefinitionChecker`, over the search repositories), which replaced `RejectingDefinitionChecker`. A definition it refuses fails the step and rolls the whole install back. A definition that is only stale (a field or relationship the pack does not define) is accepted with a warning, as everywhere else, so a content test asserts every shipped definition has no warnings and the expected matches. Cost: no pack smart collection can refer to another collection or one specific item.
- **S7 (installed packs do not change):** nothing migrates an existing install. People who installed a pack earlier keep their hand-built lists until they remove and reinstall it. Cost: the shipped example and an old install differ.
- **S8 (what converted):** only where the pack's own data holds an honest rule. *Still to try* (games) became "a board game with a condition recorded and no *Played at* connection", which matches the old hand-built list exactly (the wishlist games have no condition). *Running low* (parts) became "stock at or under the part's own reorder level" (`in_stock <= {"ref": "reorder_at"}`, type `parts-part`). Field-to-field comparison was already available as a `ref` operand (same type, one comparable kind), so no new condition was needed; an earlier note that it did not exist was wrong. It is not identical to the old list: it matches LM317, the 10-turn trimmer and the solder wire reel (1 in stock, reorder at 1), and no longer lists the 470 uF capacitor (12 in stock, reorder at 10), which was only ever there by hand ("close to the line"); no operator reproduces the old list, and the data was left alone. The Parts pack is at version 6. *Games for two* stays manual: it is a judgement ("good with just the pair of us"), and a player-count rule would match nearly every game. One collection was added: *No poster yet* (movies), films with no *For* connection pointing at them from a poster. Games, Movies and Parts packs are at version 6; other packs and all pack ids are unchanged.

**Consequences:** a smart collection counts as an entity of kind `collection` in the installation, with a content hash over its name, description, empty member list and definition, so changing the definition counts as an edit and the collection is kept on removal, as a rename is. A smart collection has no members, so none of the "kept because a surviving collection holds it" logic applies to it. Because a rule runs over everything the person owns, *Still to try* also picks up an installed add-on's games that have a condition and no game night. Installing twice is refused as before, and a clashing type slug still stops the install before anything is created.

## Personal exports can be listed and deleted (2026-10-24)

**Decision:** `GET /me/exports` lists the caller's unexpired personal exports (`id`, `size`, `created_at`, `expires_at`), newest first, and `DELETE /me/export/{backup_id}` removes one (204). Both use the existing `backup:own_data:export` permission, `Content` stance and cookie route class of the other personal export routes, so they are no more reachable by tokens than export itself. Another account's export, an unknown id and an expired export are all the same 404.

**Retention:** exports expire 24 hours after creation (`user_export_ttl_hours`, already a setting). Each account has its own store, so listing and deleting see only its own archives.

**Cleanup:** no new mechanism. Creating, downloading, listing and deleting an export all prune that account's expired archives first, and `backup prune` already removes expired exports across every account (`cleanup_user_exports`). An expired export is therefore never shown or served, even if nothing has pruned it yet. No scheduler was added.

**Also:** unknown paths and wrong methods under `/api` now answer with the usual problem+json body (`NotFoundError`, `MethodNotAllowedError`; `Allow` is kept). Paths outside `/api` and the SPA fallback are unchanged, and these default responses are not added to every operation in OpenAPI.

## OpenAPI links (2026-10-24)

**Decision:** success responses that return an id carry OpenAPI `links` to the operations that take it, so a client or Swagger can follow an id from one call into the next.

**Generated:** `entrypoints/api/openapi_links.py` runs in `configure_openapi()`. For a collection path (`/node`) and its item paths (`/node/{node_id}`, `/media/{asset_id}/promote`), every 2xx JSON response of an operation on the collection (create, list) or on the item itself (get, update) whose body has an `id` links to the other operations under the item path, mapping the path parameter to `$response.body#/id` (a list uses `#/0/id`, the first item). Links are named after the target's `operationId` (`GetNode`, `DeleteNode`). It skips paths with more than one path parameter, item paths with no collection to take an id from, and lists on the item path (`GET /media/for-node/{node_id}` returns assets, not nodes). A link a route declares is never overwritten, and a target the route already links to is not linked twice. The personal API token routes fall out of the convention.

**Written on the routes:** the personal export routes, because the list lives at `/me/exports` while the item routes are under `/me/export`. `POST /me/export` and `GET /me/exports` link to `DownloadExport` and `DeleteExport`.

**Swagger plugin:** `static/swagger-init.js` wraps Swagger UI's `operationLink` component (via `wrapComponents`) and adds an "Open `<operationId>`" button. Clicking it shows the target's tag and operation, turns on Try it out, fills the path parameters from the last response of the operation that offered the link (if that response has the link's status code), and scrolls to it. No dependency was added. Swagger UI is pinned at `swagger-ui-dist@5.33.0` (published 2026-09-16) with Subresource Integrity, as before; the plugin relies on the `operationLink` component name and the `layoutActions.show` / `specActions.changeParam` actions of that version, so check them when bumping it.

**Limits:** only `$response.body#/json/pointer` expressions are evaluated, by the plugin and by the generator; the other runtime expressions are neither generated nor followed. A link that cannot be evaluated still opens its target, with the field empty. Only the first list item is offered. Links are documentation: nothing enforces that the id is accepted by the target.

## Text search counts are capped (2026-10-24)

**Decision:** `GET /node?q=...` counts at most 1,001 matches, as smart collections and `POST /node/search` already do. `Total-Count` is then at most 1000, and `Total-Count-Capped: true` is added when there were more; it is absent otherwise. This also covers `q` combined with `?collection=` for a smart collection. Lists without `q` keep an exact `Total-Count`. Both headers are documented on the operation and `Total-Count-Capped` is CORS-exposed.

**Why:** for a very common term at 100,000 items the exact count behind `Total-Count` took about 0.9 s on every page, and the first page only needs the rows. The repository `count` takes the same optional `limit` as `search_count` (a `LIMIT` inside the counted subquery).

**Exact count on demand:** `GET /node/count` takes the same filters as `GET /node` (one shared parameter model, no paging) and returns `{"count": n}` with no cap, under the same `Content(ITEM_READ)` stance and scope. It is the slow, cheap-to-skip read: a client shows the capped figure ("1,000+") first and swaps in the exact one when this returns. This supersedes the "flag header" follow-up in R22 for the `q` case only; `?collection=<smart>` without `q` is still exact.

**Header convention:** no capped header existed (the other capped counts are body fields: `total_capped`, `item_count_capped`), so `Total-Count-Capped` is new, named after `Total-Count`.

## Recently deleted: restore and purge (2026-10-25)

**Decision (backend, as built):** items and collections get `GET /node/deleted`, `POST /node/{id}/restore`, `DELETE /node/{id}/purge` and the same three under `/collection` (fixed paths registered before `/{id}`). Use cases: `ListDeletedNodes`, `RestoreNode`, `PurgeDeletedNode`, `ListDeletedCollections`, `RestoreCollection`, `PurgeDeletedCollection`. "Restore" here is bringing a deleted row back, not backup restore.

- **T1 scope:** items and collections only. Connections, item types, relationship types, presets and media assets are not in Recently deleted.
- **T2 restore an item:** clears `deleted_at` and nothing else (`SoftDeletable.restore`). Connections and memberships were never touched by the delete, so they reappear; a connection deleted on its own stays deleted. Deleting an item type clears `type` only on live items, so a deleted item keeps the slug of a type deleted later. Restore then answers 409 (`NodeTypeDeletedError`) naming the slug. No API brings a deleted type back (there is no type restore); the way out is to create an item type with the same slug, since deleted slugs are reusable.
- **T3 restore a collection:** the only uniqueness rule is the per-owner slug among live collections (partial unique index `uq_collections_slug_live`; names are not unique). A live collection holding the slug is a 409 naming it, checked in the use case and backed by the index (a race gives the same 409). No automatic renaming. Memberships and a smart definition are untouched. Restore takes the collection id only: a deleted collection's slug does not resolve.
- **T4 purge:** hard-deletes one row already in the caller's Recently deleted list; a live row, an unknown id and another account's row are all 404. New permissions `graph:item:purge` and `collections:collection:purge` are held by members and administrators but are not token-grantable (subtracted in `TOKEN_GRANTABLE_PERMISSIONS`, so a token actor is refused with 403 even with every grantable grant); each implies nothing. An item's purge goes through the new `ItemDependents` port (bridge `item_dependents.py`), which reuses the `System`-only `PurgeAttachment` (asset and stored file only if no other attachment uses it; file removed after that commit) and `PurgeItemMemberships`; then the use case removes the item's connections (live or deleted) and the item. Dependents go first so an interrupted purge leaves the item in Recently deleted to be purged again; the steps are separate transactions, as for pack removal. A collection purge removes its memberships and the row. The existing `System` purge use cases and who may call them are unchanged.
- **T5:** restore uses the delete permission (`graph:item:write`, `collections:collection:write`).
- **T6 listing:** newest deleted first (ties by id descending), `limit` 1 to 100, `after` is the id of the last row of the previous page (a row no longer in Recently deleted gives an empty page), `Link` and an exact `Total-Count`. Rows are `DeletedNodeResponse` (`id`, `name`, `type`, `deleted_at`) and `DeletedCollectionResponse` (`id`, `name`, `kind`, `deleted_at`). **Deviation:** no `q` in version 1, so there is no capped count; the page filters in the browser. Restore returns the normal item or collection response; purge is 204.
- **T7, T8:** no retention and no empty-all, as planned. Exports still ignore deleted rows.
- **Smart collections:** one that refers to a purged (or deleted) collection reads as empty with the "That collection no longer exists." warning, never an error; restoring the referred collection makes it evaluate again.

## Retention purge of deleted content (2026-10-25)

**Decision (backend, as built):** deleted items, connections and collections are hard-deleted once they have been deleted for longer than a retention period, by `menagerist data purge-deleted [--older-than-days N] [--dry-run]`, meant to be run from cron. It completes the "no retention" gap left in Recently deleted (T7).

- **Scope:** instance-wide, across all owners, because the CLI has no signed-in person. Rows with `deleted_at` before the cutoff only; live rows, and soft-deleted item types, relationship types and presets, are never touched.
- **Setting:** `MENAGERIST_RETENTION_DELETED_DAYS`, default 30, minimum 1 (`RetentionSettings`, in `INSTANCE_SETTINGS`). `--older-than-days N` overrides it for one run; below 1 is refused with exit code 1.
- **Use cases:** `PurgeExpiredNodes` (graph) and `PurgeExpiredCollections` (collections), `System` stance, pinned in the stance tests. Commands carry an aware `older_than` and `dry_run` (and a `batch_size`, default 100); results return counts. The new `list_deleted_before(cutoff, limit)` and `count_deleted_before(cutoff)` reads on the node, connection and collection repositories are unscoped and ordered oldest first (ties by id); the content-scope architecture test lists them as exemptions. Work runs in bounded batches until nothing is left, each row in its own transaction.
- **Same path as a person's purge:** an item goes through `ItemDependents` (memberships, attachments, then assets and stored files only they used, files removed after their commit), then its connections (live or deleted), then the row. A row restored between listing and purging is re-checked and skipped. Collections remove their memberships with the row; items stay.
- **Connections:** those deleted on their own and old enough go first and are the ones counted; connections that go with a purged item are not counted separately, so a dry run gives the same numbers as the real run.
- **Composition:** `PurgeDeletedContent` in `entrypoints/api/shared/purge_deleted.py` (shared by the CLI and the scheduler) runs the graph purge then the collections purge and sums the counts; the modules import nothing from each other.
- **Dry run** changes nothing and prints "Dry run: nothing was deleted". A second run is a no-op. The command prints the cutoff (UTC) and the counts for items, connections and collections.
- **Media assets** have no `deleted_at`, so there is nothing to purge by age beyond what an item purge already removes (an asset and its file go only when no other attachment uses it). Orphaned and staged media keep their own TTL via `media cleanup`.
- **Scheduler:** the `data.purge_deleted` job (`entrypoints/api/shared/data_jobs.py`) calls the same composition with the same retention cutoff. It runs only when `MENAGERIST_RETENTION_PURGE_SCHEDULE` is set (empty by default) and cannot be started by hand from the Scheduled tasks page, because a permanent deletion should not be one click.

## Expired credentials and unused media are purged by scheduled jobs (2026-10-28)

**Decision:** three jobs contributed by their own modules (`modules/<name>/adapters/scheduling/jobs.py`) run in the worker, alongside the existing backup and run-history jobs: `identity.purge_expired` (sessions and API tokens, `MENAGERIST_IDENTITY_PURGE_EXPIRED_SCHEDULE`, default `15 4 * * *`) and `media.cleanup` (`CleanupExpiredMedia`, `MENAGERIST_MEDIA_CLEANUP_SCHEDULE`, default `30 * * * *`). An empty schedule turns a job off. The in-line sweeps are removed: `SignIn` no longer deletes expired sessions and `CreateApiToken` no longer deletes expired tokens.

**Rationale:** sign-in is the hottest, most security-sensitive write path, and an unbounded `DELETE` inside its transaction was housekeeping riding on a user action. Neither sweep was needed for correctness: an expired or idle session is rejected, and deleted, when it is presented, and the token limit counts only unexpired tokens (`count_active(now=...)`). The cost is that a deployment with no worker leaves expired rows in place until one runs, which is harmless and already visible through the worker readiness check.

Two more jobs finish the picture. `media.remove_stray_files` (`RemoveStrayMediaFiles`, `MENAGERIST_MEDIA_STRAY_FILES_SCHEDULE`, default `45 3 * * 0`) deletes stored files whose asset row no longer exists, which is what a failed file delete after a committed row delete, or a crashed upload, leaves behind; it only considers files older than the staged-upload window, because an upload writes its file before its row exists. `media.cleanup` now removes rows in batches of 100 per transaction and deletes the files after each commit (`on_commit`), so a failure leaves a stray file rather than a row pointing at nothing.

**Alternatives rejected:** keeping the sweeps as a fallback (two code paths doing the same deletion, one of them on the sign-in path).

**Jobs describe themselves.** `JobDefinition` carries a plain-language `title` and `description`, returned by `GET /api/v1/scheduling/jobs` and shown on Administration > Scheduled tasks; a catalogue test fails a job without them. A schedule key is the key of the setting that holds it, so whether an administrator can change it at runtime is read from the settings catalogue (`Tunable()`), not listed beside the job.
