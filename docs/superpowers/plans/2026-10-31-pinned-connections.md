# Pinned Connections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended here) or superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an item type pin up to two of its relationships so they show inline on its cards and item page and can be filled in as fields on the item form, so a signature no longer needs a long name like "Tobias Wren on Chronicle Drive maxi poster".

**Architecture:** The pin is type-level metadata in the item type's `attributes_schema` at `x-menagerist.pinned_connections`, beside `highlights`; it needs no new column and no pack format change. A new read-only query returns the pinned far-end items for a page of items in one request. The item form turns each pinned relationship into a picker that creates or removes the underlying connections, which stay the single source of truth.

**Tech Stack:** FastAPI, SQLAlchemy, PostgreSQL; SvelteKit (Svelte 5 runes), shadcn-svelte, Vitest, Playwright.

**Spec:** None written separately. The decisions below were agreed in conversation (2026-10-31) and stand in for it.

## Decisions (agreed or my call)

- **Agreed:** shorten pack signature names (option 1); pinned connections shown on cards and the item page (option 2); pinned connections also fillable as form fields (option 3). No derived/templated names, and no "reference" field type that stores an id in the item's own data.
- **My call:** the key is `x-menagerist.pinned_connections`, a list of `{ "relationship": <edge type slug>, "direction": "out" | "in" }`, at most 2. `out` means this item is the connection's source (a signature `on` a poster); `in` means it is the target.
- **My call:** pinned data is type-only, like `highlights`. It is not merged from an item's `extra_schema`.
- **My call:** a dangling pin (relationship deleted, far item deleted or outside the actor's scope) is silently skipped, as dangling highlights are.
- **My call:** on cards the pinned values are plain text (the card is already one link); on the item page they are links.
- **Agreed:** the endpoint is `GET /api/v1/node/pinned`, a one-word sub-path like `/random` and `/search`; the full meaning lives in the operation id `list_pinned_connections`. The declaration type is `PinnedConnection` (matches the schema key) and the resolved row is `PinnedConnectionTarget`.

## Global Constraints

- British English in copy, comments and docs.
- Backend: layering `entrypoints → adapters → application → domain`; every use case sets `access = ...` and implements `_handle`; new `Content` use cases are added to the pinned set in `backend/tests/architecture/test_access_stances.py`; every new port method gets an in-memory implementation in a sibling file; strict mypy; domain/application/shared_kernel coverage stays at 100%.
- Frontend: Svelte 5 runes; fetch through `src/lib/api/client.ts`; never hand-edit `src/lib/api/generated/`, regenerate with `poe generate-frontend-client`; internal hrefs via `resolve()`; fixed-choice inputs use `ui/native-select`; collector-facing terms only (say "connection", never "edge" or "node" in the UI).
- Run tasks with `poe ... --mode agent`. Use targeted tests while iterating; run `poe coverage` and `poe typecheck-backend` before finishing backend work, and `poe typecheck-frontend`, `poe lint-frontend`, `poe test-frontend` before finishing frontend work.
- **Never run `git add` or `git commit`** (AGENTS.md). Where the template would commit, the step is "leave for the user".
- Do not add error handling or abstractions beyond these tasks.

## Review Focus

1. A pin names a relationship that has since been deleted: the card and page render without it and without an error (Task 3 and Task 6 tests).
2. A pinned far item is soft-deleted or belongs to another user: it is omitted for the actor (Task 3 test with two users).
3. A page of 100 items with pins: one request, not one per card (Task 6 test counts calls).
4. One item with many connections on a pinned relationship: the card shows the first values and "+N", never a long overflowing line (Task 6 test).
5. An item is retyped: the new type's pins apply immediately and nothing needs migrating (Task 3 test).
6. Saving the form creates the item but a connection fails: the item exists, the error names the failed connection, and re-saving does not duplicate the ones that worked (Task 8 test).
7. A long pinned name wraps instead of truncating (Task 6 e2e).

---

## Part A: The pack stopgap

### Task 1: Short signature names in the `conventions` pack

**Files:**

- Modify: `backend/src/app/modules/examples/packs/conventions.json`
- Test: `backend/tests/modules/examples/application/test_shipped_packs.py` (runs over every pack; no edit needed)

**Interfaces:**

- Produces: signature items named by signer only (for example `Tobias Wren`); item `ref`s unchanged so connections and collections still resolve.

- [ ] **Step 1:** Edit `conventions.json` directly: rename each `signature` item's `name` to the signer's name only (for example `Tobias Wren on Chronicle Drive maxi poster` becomes `Tobias Wren`). Leave every `ref` unchanged so the connections and the "Signatures" and "Signed wall" collections still resolve.
- [ ] **Step 2:** Run `poe test-backend --mode agent` and `cd frontend && npx vitest run tests/example-packs.test.ts`. Expected: pass.

---

## Part B: Pinned connections on cards and the item page

### Task 2: Validate `pinned_connections` in the schema metadata

**Files:**

- Modify: `backend/src/app/modules/graph/application/schema_meta.py` (add `MAX_PINNED_CONNECTIONS = 2` and `_check_pinned_connections`, called from `check_meta_shape` beside `_check_highlights`)
- Test: `backend/tests/modules/graph/application/test_schema_meta.py`

**Interfaces:**

- Produces: `check_meta_shape` rejects, with `InvalidSchemaError`, a `pinned_connections` that is not a list, has more than 2 entries, has an entry that is not an object with a non-empty string `relationship` and a `direction` of `"out"` or `"in"`, or repeats a `(relationship, direction)` pair. A missing or empty list passes.

- [ ] **Step 1:** Write `test_check_meta_shape_accepts_valid_pinned_connections` (one entry, two entries, empty list, absent) and a parametrised `test_check_meta_shape_rejects_bad_pinned_connections` covering: `"no"`, three entries, `[{"relationship": "x"}]`, `[{"relationship": 5, "direction": "out"}]`, `[{"relationship": "x", "direction": "sideways"}]`, and a duplicate pair.
- [ ] **Step 2:** Run `uv run pytest backend/tests/modules/graph/application/test_schema_meta.py -q`. Expected: the new tests fail.
- [ ] **Step 3:** Implement `_check_pinned_connections(root: object) -> None` in `schema_meta.py`. Follow `_check_highlights` for the error-message style (`f"{NAMESPACE}/pinned_connections ..."`). It does not check that the relationship exists (validation has no repository access); dangling pins are skipped at read time.
- [ ] **Step 4:** Re-run; expected pass. Confirm `merge_attribute_schemas` leaves `pinned_connections` out of the merged result, as it does `highlights`, and add `test_merge_keeps_pinned_connections_type_only` if the existing highlights test has no equivalent.

### Task 3: `ListPinnedConnections` query

**Files:**

- Create: `backend/src/app/modules/graph/application/list_pinned_connections.py`
- Modify: `backend/src/app/modules/graph/ports/edge_repository.py`, `backend/src/app/modules/graph/adapters/persistence/edge_repository.py`, `backend/src/app/modules/graph/adapters/persistence/in_memory_edge_repository.py` (add `list_for_nodes`)
- Test: `backend/tests/modules/graph/application/test_list_pinned_connections.py`, plus repository tests beside `test_edge_repository.py`, `test_in_memory_edge_repository.py`, `test_edge_repository_scope.py`
- Modify: `backend/tests/architecture/test_access_stances.py` (pin `ListPinnedConnections` in the `Content` set)

**Interfaces:**

- Produces, port: `EdgeRepository.list_for_nodes(node_ids: Collection[uuid.UUID], *, types: Collection[str], scope: ContentFilter, limit: int) -> list[Edge]`: live edges in `scope` of one of `types` where source or target is in `node_ids`, ordered by id.
- Produces, application: `@dataclass(kw_only=True, frozen=True) class PinnedConnectionTarget: node_id: uuid.UUID; relationship: str; direction: Literal["out", "in"]; other_id: uuid.UUID; other_name: str; other_type: str | None`; `@dataclass(kw_only=True) class ListPinnedConnectionsQuery: node_ids: list[uuid.UUID]` (at most 100, else `ValidationError`); `class ListPinnedConnections(QueryHandler[GraphRepos, ListPinnedConnectionsQuery, list[PinnedConnectionTarget]])` with `access = Content(GraphPermission.ITEM_READ)`.
- Behaviour: fetch the items with `repos.nodes.list(ids=..., scope=self.scope(actor))`; read each item's type pins via the node type repository (`attributes_schema` → `x-menagerist.pinned_connections`); one `list_for_nodes` call for the union of pinned relationship slugs; resolve far items with `repos.nodes.list(ids=..., scope=...)` and drop links whose far item is missing, deleted or out of scope; keep a link only when its direction matches the anchor's pin (`out`: anchor is source).

- [ ] **Step 1:** Write failing application tests with the in-memory repos: `test_returns_pinned_far_items_for_each_node`; `test_skips_relationships_the_type_does_not_pin`; `test_respects_direction` (a pin `out` ignores an incoming edge of the same type); `test_skips_deleted_and_foreign_far_items` (two users, per Review Focus 2); `test_ignores_a_pin_whose_relationship_does_not_exist` (Review Focus 1); `test_retyping_an_item_changes_which_pins_apply` (Review Focus 5); `test_rejects_more_than_100_ids`; `test_item_without_a_type_returns_nothing`.
- [ ] **Step 2:** Write failing repository tests for `list_for_nodes` in both repositories: filters by type, matches either end, excludes soft-deleted edges, honours `ContentFilter` scope, honours `limit`.
- [ ] **Step 3:** Run them; expected: fail on missing names.
- [ ] **Step 4:** Implement the port method (SQL: `source_id IN :ids OR target_id IN :ids`, `type IN :types`, scope, `ORDER BY id`, `LIMIT`), its in-memory twin, then the use case.
- [ ] **Step 5:** Update the pinned `Content` set in `test_access_stances.py`.
- [ ] **Step 6:** Run `uv run pytest backend/tests/modules/graph -q`, then `poe typecheck-backend --mode agent`. Expected: pass.

### Task 4: `GET /node/pinned` endpoint and generated client

**Files:**

- Modify: `backend/src/app/modules/graph/adapters/api/node/router.py`, `backend/src/app/modules/graph/adapters/api/node/schemas.py`, the node dependency wiring that provides use cases
- Test: `backend/tests/modules/graph/adapters/api/test_node_router.py` (or the existing node router test file)
- Regenerate: `frontend/src/lib/api/generated/` via `poe generate-frontend-client`

**Interfaces:**

- Produces: `GET /api/v1/node/pinned?node_id=<uuid>&node_id=<uuid>...` (repeatable parameter, operation id `list_pinned_connections`) returning `list[PinnedConnectionTargetResponse]` with the `PinnedConnectionTarget` fields, `other_*` flattened to `other_id`, `other_name`, `other_type`. Declare it before the `/{node_id}` route so it is not read as an id.

- [ ] **Step 1:** Write router tests: returns connections for two items; `400`/`422` for more than 100 ids; a second user does not see the first user's connections; an unauthenticated call is `401`.
- [ ] **Step 2:** Run to see them fail, implement the route and response model (no `try/except`; domain errors map globally), run to pass.
- [ ] **Step 3:** Run `poe generate-frontend-client` and confirm `listPinnedConnections` exists in the generated client. Do not edit generated files by hand.

### Task 5: Choose pinned connections in the item type editor

**Files:**

- Modify: `frontend/src/lib/schema-meta.ts` (add `PinnedConnection = { relationship: string; direction: 'out' | 'in' }`, `readPinnedConnections(schema): PinnedConnection[]`, `withPinnedConnections(schema, entries): schema`; add the field to `SchemaMeta`)
- Modify: `frontend/src/lib/components/type-editor-dialog.svelte` (and `schema-editor.svelte` if the schema is built there)
- Test: `frontend/tests/schema-meta.test.ts`, `frontend/tests/schema-editor-keys.test.ts` (round-trip), `frontend/tests/e2e/manage-item-types.spec.ts` (or a new `pinned-connections.spec.ts`)

**Interfaces:**

- Produces: `readPinnedConnections` skips malformed entries and returns at most 2; `withPinnedConnections` writes the list (removing the key when empty) and keeps every other metadata member.

- [ ] **Step 1:** Write unit tests: reads a valid list; skips malformed entries; `withPinnedConnections(schema, [])` removes the key; other members survive; `itemsToSchema` round-trips `pinned_connections` untouched (guards against the editor dropping it).
- [ ] **Step 2:** Implement the helpers.
- [ ] **Step 3:** In the type editor add a "Show on cards" section under the highlight controls: up to two rows, each a `ui/native-select` of relationships worded for the type ("Signed by", "Shows") with direction chosen implicitly from the relationship's forward/reverse label (list each relationship twice: forward label = `out`, reverse label = `in`). Use collector-facing words only.
- [ ] **Step 4:** Add an e2e test that pins a relationship in the editor and sees it saved after reload.
- [ ] **Step 5:** Run `poe test-frontend --mode agent`, `poe typecheck-frontend --mode agent`.

### Task 6: Show pinned connections on cards and the item page

**Files:**

- Create: `frontend/src/lib/pinned-connections.ts` (`loadPinnedConnections(ids: string[]): Promise<Map<string, PinnedConnectionTarget[]>>`, chunking at 100 ids; `formatPinned(targets, max): { label: string; names: string[]; more: number }[]`)
- Create: `frontend/src/lib/components/pinned-connections.svelte` (props: `groups`, `linked: boolean`; wraps text, never truncates)
- Modify: `frontend/src/lib/components/node-card.svelte`, `node-grid-card.svelte` (new optional `pinned` prop, rendered after highlights, counted against the surface limit)
- Modify: `frontend/src/routes/items/+page.svelte`, `frontend/src/routes/collections/[id]/+page.svelte`, `frontend/src/routes/+page.svelte` (load once per visible page, pass down)
- Modify: `frontend/src/routes/items/[id]/+page.svelte` (render under the title from the connections already loaded; no new request)
- Modify: `frontend/DESIGN_GUIDELINES.md` (§3.2 card contents, §7c: pinned values wrap on the item page, single line with "+N" on cards), `docs/field-types.md` (document `pinned_connections` beside highlights), `docs/DECISIONS.md` (record the decision)
- Test: `frontend/tests/pinned-connections.test.ts`, `frontend/tests/e2e/pinned-connections.spec.ts`

**Interfaces:**

- Consumes: `listPinnedConnections` from Task 4; `readPinnedConnections` from Task 5.
- Produces: `NodeCard`/`NodeGridCard` accept `pinned?: { label: string; names: string[]; more: number }[]`.

- [ ] **Step 1:** Write `pinned-connections.test.ts`: groups connections by relationship and orders by the type's pin order; `more` counts names past the cap (cap 2 names per group on cards); an item with no connections gives no groups; chunking sends two calls for 150 ids (Review Focus 3, assert on a mocked client).
- [ ] **Step 2:** Implement `pinned-connections.ts` and the component; wire the cards and the three list pages (one `loadPinnedConnections` per loaded page, not per card).
- [ ] **Step 3:** Item page: derive the pinned groups from `edges`/`nodesById`; show them as links under the title.
- [ ] **Step 4:** e2e `pinned-connections.spec.ts`: create a type with a pin, a poster and a signature connected by the pinned relationship; the signature card on `/items` shows the poster's name; a deleted relationship type leaves the card without an error (Review Focus 1); a very long pinned name wraps on the item page (Review Focus 7); a seven-link item shows two names and "+5" (Review Focus 4).
- [ ] **Step 5:** Update the three docs. Run `poe check-changed --mode agent`, `poe test-frontend --mode agent`, and `poe test-e2e -w 1 tests/e2e/pinned-connections.spec.ts tests/e2e/item-page-layout.spec.ts`.

### Task 7: Pin the `conventions` pack's relationships

**Files:**

- Modify: `backend/src/app/modules/examples/packs/conventions.json`
- Test: `backend/tests/modules/examples/application/test_shipped_packs.py` (existing), plus a new assertion in `backend/tests/modules/examples/application/` that the installed Signature type pins `conventions-on` and `conventions-at`

- [ ] **Step 1:** Add `pinned_connections` to the `x-menagerist` block of each item type's `attributes_schema`: Signature pins `conventions-on` (`out`) and `conventions-at` (`out`); Photo pins `conventions-with` (`out`) and `conventions-at` (`out`); Collectable pins nothing.
- [ ] **Step 2:** Write the failing assertion, make the edit, run the example tests (`uv run pytest backend/tests/modules/examples -q`) and the frontend `example-packs` test. Expected: pass.

---

## Part C: Connections as form fields

### Task 8: Reusable target picker, then pinned fields on the new-item form

**Files:**

- Create: `frontend/src/lib/components/connection-target-picker.svelte` (extracted from the inline picker in `routes/items/[id]/+page.svelte` around lines 1030-1070; same behaviour, props `value: NodeResponse[]`, `onchange`, `excludeId?`)
- Modify: `frontend/src/routes/items/[id]/+page.svelte` (use the extracted component; behaviour unchanged)
- Modify: `frontend/src/routes/items/new/+page.svelte` (one picker per pinned relationship of the chosen type; after `createNode`, call `createEdges` once per pinned relationship with the chosen targets)
- Test: `frontend/tests/e2e/connect-items.spec.ts` (must still pass after the extraction), new `frontend/tests/e2e/pinned-connection-fields.spec.ts`

**Interfaces:**

- Consumes: pins from Task 5; `createEdges` (already used by the item page): `{ source_id, target_ids, type }` for `out` pins; for `in` pins create with the new item as target, one `createEdge` per chosen source.
- Produces: a form field labelled with the relationship's forward label (`out`) or reverse label (`in`).

- [ ] **Step 1:** Extract the picker as a pure refactor; run `connect-items.spec.ts` and the item-page layout spec before and after. Expected: pass both times.
- [ ] **Step 2:** Write the failing e2e: choose a type with two pins, pick a poster and an event in the form, save, and see both connections on the item page; a failed second connection (force it with a route intercept) keeps the item, shows which connection failed, and re-saving does not duplicate the first (Review Focus 6).
- [ ] **Step 3:** Implement the form fields and the save sequence. Treat "target already connected by this type" as success (`createEdges` already skips duplicates).
- [ ] **Step 4:** Run `poe test-frontend --mode agent`, `poe typecheck-frontend --mode agent`, `poe lint-frontend --mode agent` and the two specs above.

### Task 9: Pinned fields when editing an existing item

**Files:**

- Modify: `frontend/src/routes/items/[id]/+page.svelte` (in the item's edit mode, show the same pinned pickers, prefilled from `edges`; on save, diff against the current connections: create the added, delete the removed)
- Test: extend `frontend/tests/e2e/pinned-connection-fields.spec.ts`

- [ ] **Step 1:** Write the failing e2e: edit a signature, swap its event, save; the old connection is gone, the new one present, and unrelated connections (not pinned) untouched.
- [ ] **Step 2:** Implement using the existing `createEdges` and `deleteEdge` handlers and their undo toasts. Follow the page's current save handler for attribute edits; do not add a second save path.
- [ ] **Step 3:** Run the same frontend checks as Task 8 plus `poe test-e2e -w 1 tests/e2e/pinned-connection-fields.spec.ts`.

---

## Final gate

- [ ] `poe coverage --mode agent` (full backend gate), `poe typecheck-backend --mode agent`, `poe lint-backend --mode agent`.
- [ ] `poe typecheck-frontend --mode agent`, `poe lint-frontend --mode agent`, `poe test-frontend --mode agent`, then the full `poe test-e2e`.
- [ ] Leave all changes unstaged and uncommitted for the user.

## Self-review notes

- **Coverage of the three agreed options:** Task 1 (option 1), Tasks 2-7 (option 2), Tasks 8-9 (option 3). The derived-name and reference-field options are explicitly out of scope.
- **Known gaps the implementer should confirm before starting:** the exact file that provides node use cases to the router (Task 4); whether `NodeTypeRepository` can fetch several types by slug in one call (Task 3, add a method with an in-memory twin if not); the name of the item page's edit-mode save handler (Task 9).
