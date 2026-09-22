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

**Rationale:** Constraints affect validity, so they are standard keywords (the `x-menagerist` principle). Patterns built from escaped literals, `^` and `$` behave the same in Python `re` and JavaScript's `u`-flag RegExp, which a shared fixture (`contract/fixtures/regex-conformance.json`) checks in both suites. Two anchored halves keep `a` valid for `^a` plus `a$` and let each half say which part failed. Free-form regex was left out: the two dialects differ (lookbehind, named groups, `\d`), and a user pattern would run unbounded in Python `re` (ReDoS).

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

**Rationale:** Reuses the existing field-type registry, editor components, validation and search unchanged for per-item fields, instead of a parallel typed-field system. `backend-surface.md` scopes WI-19d to "a column and API fields, not a port" — this session is that plumbing. The frontend UI to add typed per-item fields (WI-18b/18c) is separate and builds on this.

**Tradeoff:** No item-page UI yet to create or edit `extra_schema` entries directly; only the API surface exists. WI-17 attribute search does not yet exclude non-searchable overlay fields (for example a per-item rating) the way it does for type fields, since exclusions are computed per type, not per node — left for later. No migration path to remove per-item fields beyond archiving them inside `extra_schema` itself, same as a type schema.

---

## Reusable field and list presets: copy-on-apply with provenance

**Decision:** A new `presets` backend module (own hexagonal layers, no dependency on `graph`) stores saved fields, field groups (`field_set`, "field group" in the UI) and lists (`choice_list`) as `{kind, label, description, definition, version, builtin}`, soft-deletable, with a definition-shape check per kind (`application/preset_definitions.py`). Applying a preset **copies** its definition into the target schema with a fresh key (WI-20) and records `x-menagerist.origin: {preset, version}` on the property; provenance is metadata only and never affects validation. Editing a preset's `definition` bumps `version`, so a copy showing an older version can offer "update available". `field` (a single field, "Save for reuse" from a schema-editor field) and `choice_list` (a set of options, "Save these options as a list" / "Use a saved list" on a choice field, with "Update options" reusing the WI-9/10 in-use warning) are wired up this session; `field_set` is stored and validated but has no save/apply UI yet.

**Rationale:** Copy-on-apply keeps every node type's schema a standalone JSON Schema both validators already understand, so deleting a preset never breaks a type that used it — the alternative, a live link, is parked as a v2 idea (`SyncChoiceList`). The `group` field kind's UI label changes to "Table" (code name unchanged) to free "Field group" for the new reusable-set concept.

**Tradeoff:** No UI yet for saved fields from a custom detail, for field groups (save/apply as a labelled section), for per-item application (needs the WI-19d overlay's own editor), or for packs/import-export/built-ins (WI-19c). These are separate, later items.

---

## Multi-add uses a single `CreateEdges` batch command

**Decision:** `POST /edge/batch` (`CreateEdgesCommand`/`CreateEdges`) connects one source to several targets of the same relationship type in one transaction, sharing the same attributes across every new connection. A target already connected by an edge of that type (in either direction) is skipped, not duplicated, using the same `list_for_node` paging the purge use cases already use. The item page's "Connect item" form becomes a multi-select; on success it shows a count (created, and skipped if any) with a 5-second Undo that deletes the created edges individually.

**Rationale:** The spec calls this out explicitly as structural over convention: N client calls to `POST /edge` would not be atomic and could leave a half-connected state on a partial failure, whereas the batch command commits once. Reusing `list_for_node` for the duplicate check avoids a new repository method.

**Tradeoff:** Undo removes the created edges one at a time (no batch delete exists), best-effort. Creating new items inline from the picker (typing a name that doesn't match anything) is not implemented; only existing items can be selected.

---

## Rank-based matching for kind-less properties (WI-12)

**Decision:** `FieldTypeDescriptor` gained an optional `rank?: (prop) => number`. `descriptorForProp` now picks the highest-ranked descriptor whose `fromSchema` matches an unkinded (API-authored) property, defaulting unranked matches to `1`; ties fall back to registration order. An explicit `x-menagerist.kind` is unaffected — it was, and remains, a direct lookup.

**Rationale:** Correctness no longer depends on import order in `field-types/index.ts`. No current built-in kind actually needs a non-default rank: every scalar's `fromSchema` already excludes the shapes the others claim (checked directly — `text` excludes `format`/`enum`, `date`/`choice` require them, `rating`/`longtext` only ever match an explicit `kind`), so this is infrastructure for the overlapping kinds the spec anticipates (multi-choice, partial date, identifier, URL/email), not a fix for a live bug.

**Tradeoff:** None beyond the small added surface on the descriptor type.

---

## Required-field marker is neutral, not red

**Decision:** In the attributes editor, a required field's asterisk is `text-muted-foreground`, not `text-destructive`. When the field is currently empty, the asterisk is replaced by a small "Recommended" text hint instead. Neither ever blocks saving.

**Rationale:** Required is advisory only (WI-6, guidelines §16a); a red asterisk reads as a validation error even though nothing is actually being validated. Implements open question 58 (owner decision, 2026-09-21), which had been recorded but not yet built.

---

## A table (group) field's column order is stored explicitly

**Decision:** A `group` property's own metadata gains a `columns` member: an ordered array of its sub-property keys, written by `toSchema` from the in-memory sub-field order and read by `fromSchema`, `GroupInput.svelte` and `GroupView.svelte` via a shared `orderedColumns(prop)` helper (`field-types/group/columns.ts`). A property with no `columns` (saved before this fix, or authored through the API) falls back to `Object.entries` order. The backend's `check_meta_shape` validates `columns` is an array of strings, alongside the other property metadata members.

**Rationale:** Verified directly against Postgres: nested JSONB object keys are not stored in insertion order (`{zeta_field, region, a_long_custom_name, aa, k1}` came back as `{aa, k1, region, zeta_field, a_long_custom_name}`), the same reordering WI-18a already found for loose attribute keys. A table field's columns were derived from `Object.entries(prop.items.properties)` with no explicit order recorded anywhere, unlike top-level fields (`x-menagerist.layout`), so a table's column order silently scrambled after any save and reload.

**Tradeoff:** Existing table fields saved before this fix keep their JSONB-scrambled order until re-saved from the schema editor — the same no-migration pattern as every other `x-menagerist` addition.
