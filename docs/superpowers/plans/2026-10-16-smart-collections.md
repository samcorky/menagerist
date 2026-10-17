# Smart collections (phase 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A person can save a search as a smart collection whose members are always current, open it, see its conditions, and edit them, alongside the existing manual collections.

**Architecture:** A collection gains `kind = dynamic` and a stored `definition` (the phase 1 query tree, opaque to the `collections` module). `collections` never imports `graph`: validation and member resolution go through small ports in `collections` and `graph`, implemented as bridges in `entrypoints/api/shared/` over graph use cases, as `ItemLookup` and `CollectionMembers` already are. The collection page runs the saved query through `POST /node/search`; `GET /node?collection=` resolves a smart collection through the same engine.

**Tech Stack:** FastAPI, SQLAlchemy/Postgres JSONB, Alembic, SvelteKit 5 runes, shadcn-svelte, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-14-smart-collections-advanced-search-design.md`, phase 2. Rulings and conventions from phases 1 and 1b: `.superpowers/sdd/2026-10-14-query-engine-advanced-search/progress.md`, `.superpowers/sdd/2026-10-16-per-item-field-conditions/progress.md`.

## Global Constraints

- Dependency direction `entrypoints → adapters → application → domain`; the `collections` and `graph` modules never import each other (the architecture tests enforce it); classes in `application/` are handlers or named `*Command/*Query/*Result/*Permission`; commands use the unit of work and `commit()`, queries read through a repository.
- Every port ships a first-class in-memory adapter next to the real one; application and router tests use the in-memory adapters; only tests of the real persistence adapters are integration-marked.
- Domain and application stay at 100% line and branch coverage; run only relevant checks via `uv run poe ...`; Postgres tests need Docker.
- Svelte files go through the `svelte:svelte-file-editor` agent. British English. UI copy: "smart collection", "condition", "match all / any"; never "node", "edge" or "graph".
- The access scope is always applied last: a saved query can never reach another person's items. A saved query is evaluated for the viewer; there is no sharing yet.
- No agent runs `git add` or `git commit`; the user commits after each task.
- Existing manual collections, `GET /node` without `collection`, and the existing collection UI keep working unchanged.

## Review Focus

- **Scope:** a smart collection saved by one person never returns another person's items, including through `GET /node?collection=` and counts.
- **Kind rules:** adding or removing items on a smart collection is a 409; a manual collection never has a definition; the kind cannot be changed after creation (R18).
- **Stale definitions:** a definition naming a field or type that was later removed still loads; the collection page shows the warnings; the card count does not error.
- **Invalid definitions:** a malformed or over-limit definition on create or update is a 400 with the path of the first bad condition, never a 500; a definition whose query no longer validates when read (item type changed) degrades to "matches nothing plus warnings", not an error page.
- **Combined filters:** `GET /node?collection=<smart>&q=...&type=...&favourite=...` ANDs those filters with the saved query; sorting and paging stay consistent across pages.
- **Cost:** a smart collection's count is a capped count (`TOTAL_CAP`, `total_capped` as in search), never an unbounded scan or an `IN (ids)` list.

## Rulings made while planning

- **R18:** The kind is fixed at creation; there is no manual-to-smart conversion. Cost if wrong: a later "convert" feature; the data model allows it.
- **R19:** `GET /node?collection=<smart>` orders by id with the existing id paging and ignores the saved sort; the collection page uses `POST /node/search` with the stored definition so its saved sort applies. Cost if wrong: other consumers of `GET /node?collection=` see id order.
- **R20:** The item count of a smart collection is the capped search count (up to `TOTAL_CAP`), returned with a `item_count_capped` flag; the collection ETag uses `updated_at` and that count.
- **R21:** The definition is stored exactly as the client sent it after it parses and validates; nothing is rewritten (so relative dates stay relative).

---

### Task 1: Collection domain, storage and kind rules

**Files:**
- Modify: `backend/src/app/modules/collections/domain/collection.py`, `domain/errors.py`
- Modify: `adapters/persistence/{models,collection_repository,in_memory_collection_repository}.py`
- Create: Alembic migration (check `alembic heads`; add upgrade and downgrade): nullable JSONB `collections.definition`
- Modify: `application/{create_collection,update_collection,add_items_to_collection,remove_item_from_collection}.py`
- Test: `backend/tests/modules/collections/...` (domain, application, repository on both adapters, migration)

**Interfaces:**
- Produces: `CollectionKind.DYNAMIC = "dynamic"`; `Collection.definition: dict[str, Any] | None`; `Collection.create(..., definition: dict | None = None)` sets `kind` DYNAMIC iff a definition is given; `Collection.replace_definition(definition: dict)` (dynamic only, touches `updated_at`); `CollectionKindError(ConflictError)` raised when items are added to or removed from a dynamic collection, when a definition is given to or replaced on a manual one.
- Consumes: shared-kernel error base types (409 maps to the existing conflict base).

- [ ] **Step 1: Write failing tests**: create manual (definition None) and dynamic; replace_definition on dynamic ok, on manual raises; add/remove membership on dynamic raises `CollectionKindError` (409 at the API in Task 3); round-trip of `definition` through both repository adapters including nested JSON; the migration adds the column nullable and existing rows load as manual; deleting and restoring unaffected.
- [ ] **Step 2: Run, expect failure.**
- [ ] **Step 3: Implement** the domain, model column, migration, repository mapping (both adapters) and use-case guards. `CreateCollectionCommand` and `UpdateCollectionCommand` gain an optional `definition`; at this task the definition is stored as given (validation arrives in Task 2).
- [ ] **Step 4: Run lint-backend, typecheck-backend, test-backend, Postgres tests for the collections repository and migration, architecture and cqrs tests; domain and application at 100%.**

**Checkpoint:** user may commit.

---

### Task 2: Validation and counting ports with graph-side bridges

**Files:**
- Create: `backend/src/app/modules/collections/ports/definition_checker.py` (`DefinitionChecker` Protocol)
- Modify: `backend/src/app/modules/collections/ports/item_lookup.py` (add `count_matching`)
- Create: graph application use cases `validate_query.py` (`ValidateQuery`) and extend `search_nodes.py` only if a count-only entry is needed (reuse `search_count` with `TOTAL_CAP`)
- Modify: `backend/src/app/entrypoints/api/shared/collection_items.py` (+ new `collection_definitions.py`) bridges; in-memory adapters for the new ports under `collections/adapters/persistence/`
- Modify: `collections` application: `CreateCollection`, `UpdateCollection`, `GetCollection`/`ListCollections` (`summarise`) to use them
- Test: application tests with the in-memory adapters; bridge tests like `tests/entrypoints/api/shared/test_collection_items_bridge.py`

**Interfaces:**
- Produces: `DefinitionChecker.check(definition: Mapping[str, Any], scope: AccessScope) -> list[DefinitionWarning]` (raises the collections `InvalidCollectionError` subtype carrying the JSON path for a malformed definition; returns warnings for stale fields); `ItemLookup.count_matching(definition, scope, *, cap: int) -> tuple[int, bool]` (count, capped); `DefinitionWarning(path: str, message: str)` value type in the collections domain.
- Consumes: graph `parse_query`, `resolve_fields`, `SearchNodes`/`search_count`, `TOTAL_CAP`; the bridge translates graph's `InvalidQueryError` into the collections error so neither module imports the other.

- [ ] **Step 1: Failing tests**: create/update with a malformed definition raises the collections invalid error with a path (400); a definition with a stale field is accepted and `check` returns the warning; `summarise` for a dynamic collection returns the capped count and flag; for a manual one it is unchanged; the in-memory adapters agree with the bridge on the same fixtures; scope: another owner's items are never counted.
- [ ] **Step 2: Run, expect failure.**
- [ ] **Step 3: Implement ports, in-memory adapters and the bridges** (R21: store as sent). `CollectionSummary` gains `item_count_capped: bool = False` and `warnings`.
- [ ] **Step 4: lint, mypy, `test-backend`, the bridge integration tests, architecture + cqrs tests; domain/application 100%.**

**Checkpoint:** user may commit.

---

### Task 3: API: collection schemas, router, `GET /node?collection=` and ETag

**Files:**
- Modify: `modules/collections/adapters/api/collection/{router,schemas}.py`, `adapters/api/dependencies.py`
- Modify: `modules/graph/ports/collection_members.py`, `adapters/persistence/in_memory_collection_members.py`, `entrypoints/api/shared/collection_members.py`, `modules/graph/application/list_nodes.py`
- Test: router tests for both modules, `tests/entrypoints/test_cross_user_isolation.py`, bridge integration tests

**Interfaces:**
- Produces: collection create/update bodies accept `definition`; responses include `kind`, `definition`, `item_count`, `item_count_capped`, `warnings: [{path, message}]` (warnings only on single-collection `GET`); add/remove membership endpoints return 409 for a smart collection (RFC 9457); the `CollectionMembers` port in graph gains `resolve(collection_id, scope) -> CollectionSource | None` where `CollectionSource` carries either `ids` or a `definition` (replace `item_ids`; update the in-memory adapter and every caller and test); `ListNodes` with a smart collection ANDs the saved query with `q`/`type`/`favourite`/`ids` filters by building one `Query` and calling the repository's `search` in id order (R19), applying the access scope last.
- Consumes: Task 2 ports; the existing ETag helpers in `entrypoints/api/shared/conditional_request.py` (read how the router builds the ETag today; for smart collections use `updated_at` and the capped count, R20).

- [ ] **Step 1: Failing tests**: create via API with a definition (201, `kind=dynamic`); invalid definition 400 with a path; update definition; add/remove items 409; `GET /node?collection=<smart>` returns exactly the matching items, ANDed with `q` and `type`, paging with `Link` works across a page boundary, another user's smart collection is 404 and their items never appear; a smart collection with a stale field returns warnings on `GET /collection/{id}` and an empty list on the node list; ETag changes when an item starts matching.
- [ ] **Step 2: Run, expect failure.**
- [ ] **Step 3: Implement.** Regenerate the client with `uv run poe generate-frontend-client` after the router change.
- [ ] **Step 4: lint, mypy, `test-backend`, relevant Postgres tests, architecture + cqrs; domain/application 100%.**

**Checkpoint:** user may commit.

---

### Task 4: Frontend model for smart collections (plain TypeScript)

**Files:**
- Modify/Create under `frontend/src/lib/` (read how collections are modelled today; keep new logic in `.ts` modules): collection types, `saveSmartCollection(name, query)`, `updateDefinition(id, query)`, a loader that fetches a collection and, for a smart one, runs `runSearch` with its definition and the saved sort
- Test: `frontend/tests/*.test.ts`

**Interfaces:**
- Consumes: the regenerated client (`kind`, `definition`, `item_count`, `item_count_capped`, `warnings`), phase 1 `runSearch`, `decodeQuery`, `describeCondition`.
- Produces: pure functions the Svelte work in Task 5 calls; a `smartCollectionSummary(definition, lookup)` that returns the same chip texts as the filter builder (reuse `summary.ts`); a shared "count label" helper that prints `1,000+` when capped.

- [ ] **Step 1: Failing tests** for each function, including a definition the decoder rejects (shown as "These conditions can't be shown", never a crash), warnings passed through, and the capped label.
- [ ] **Step 2: Implement; lint-frontend, typecheck-frontend, test-frontend.**

**Checkpoint:** user may commit.

---

### Task 5: Smart collection UI (Svelte)

**Files:** (through the `svelte:svelte-file-editor` agent)
- Items page and filter builder: a **Save as smart collection** action (dialog with a name field; reuse the existing new-collection dialog pattern) when filters are active
- Collections list: a smart collection card shows a "Smart" badge and its capped count; the New collection dialog stays manual-only
- Collection page for a smart collection: conditions shown as chips (read-only), **Edit conditions** (opens the builder bound to the stored definition, saves via `updateDefinition`), results from `POST /node/search` with the saved sort, warnings shown as in the items page, "Add to collection" and remove-from-collection controls hidden or disabled with an explanation ("Items are added automatically by the conditions"), and the item page's collection chips/membership dialog never offer a smart collection as a target
- Tests: component/SSR tests where the harness allows; visual check on the isolated e2e stack in light and dark, desktop and mobile

- [ ] **Step 1: Failing tests, then implement.** Keep accessible names stable; use design tokens only.
- [ ] **Step 2: lint-frontend, typecheck-frontend, test-frontend; view the screenshots.**

**Checkpoint:** user may commit.

---

### Task 5b: Exact count on request

**Files:** backend `modules/graph/adapters/api/node/router.py` + a graph query handler (reuse `search_count` without the cap), `modules/collections/adapters/api/collection/router.py` and schemas; frontend `src/lib/collections/smart.ts` and the collection page (Svelte, via the Svelte agent).

**Interfaces:**
- Produces: `GET /collection/{id}/count` (smart or manual) returning `{count: int}` exactly (uncapped), scoped to the caller, 404 for another owner's collection; the collection page shows `1,000+` when `item_count_capped` is set and offers **Count exactly**, which calls it once and shows the exact figure; cards and lists keep the capped count.
- Consumes: Task 2 `ItemLookup.count_matching` (extend with `cap: int | None`, `None` meaning exact) and the existing bridge.

- [ ] **Step 1: Failing tests**: exact count above the cap (e.g. 1,005 items) on both adapters; another user gets 404; a stale or malformed definition returns 0 without error; the generated isolation test covers the new route; frontend test that the page calls it once and only when capped.
- [ ] **Step 2: Implement; lint, typecheck, `test-backend`, `test-frontend`, architecture + cqrs tests; domain/application 100%.**
- [ ] **Step 3: Optional cache (only if a benchmark shows the need):** an in-process cache around this one call, keyed on the owner's access scope, the definition hash, the newest `updated_at` of the owner's items, the item types' newest `updated_at`, and today's date. Skip unless measured.

**Checkpoint:** user may commit.

---

### Task 5c: Editable collection slugs and slug URLs

**Files:** backend `modules/collections/application/{update_collection,create_collection}.py`, `adapters/api/collection/{router,schemas}.py`, `ports/collection_repository.py` (`get_by_slug` exists), a small `resolve` query handler; frontend `src/routes/collections/[id]/+page.ts` and `+page.svelte`, the collection links and the rename dialog (Svelte, via the Svelte agent), `src/lib/collections/*`.

**Rulings:** R23 slugs stay per owner (not global), so ids remain the canonical, always-resolvable form; a slug change does not keep the old slug (no history; links by id keep working). Collections only; item and connection types are out of scope.

**Interfaces:**
- Produces: `PATCH /collection/{id}` accepts an optional `slug` (normalised with `Slug`, unique among the owner's live collections, 409 if taken, 422 if empty or UUID-shaped) or `regenerate_slug: true` (rebuilds from the current name with the existing free-suffix logic); both together are a 422; `GET /collection/{id_or_slug}` (and its sub-routes where the id is a path parameter) accepts either a UUID or a slug, scoped to the caller, with the same 404 for another owner's collection; `Collection.rename_slug(slug)`; slugs that parse as UUIDs are rejected on create and update so a path segment is never ambiguous.
- Frontend: collection links use the slug (`/collections/<slug>`); a page opened by id replaces its address with the slug; the rename dialog gets a Slug field with **Regenerate from name** and a note that changing the slug changes the link; a 404 on a stale slug shows the normal not-found state.

- [ ] **Step 1: Failing tests**: change slug (ok, conflict, empty, UUID-shaped, unusable characters); regenerate from a renamed collection with a taken name (suffix); ids and slugs both resolve; another owner's slug never resolves (404, same as unknown); a deleted collection's slug is free again; ETag/If-Match behaviour unchanged for PATCH; frontend: link helper uses the slug, id page canonicalises, dialog emits the right body.
- [ ] **Step 2: Implement; regenerate the client; lint, typecheck, test-backend, test-frontend, architecture + cqrs; domain/application 100%; the generated isolation test covers the slug path.**
- [ ] **Step 3:** e2e additions in Task 6 (rename slug, open by slug, regenerate).

**Checkpoint:** user may commit.

---

### Task 6: End-to-end test, documentation, full gates

**Files:** `frontend/tests/e2e/smart-collections.spec.ts` (new), `docs/DECISIONS.md`, `docs/ARCHITECTURE.md` and `backend/README.md` where collections are described, the spec (phase 2 status)

- [ ] **Step 1: e2e** on the isolated stack only: build a filter on the items page, save as a smart collection, see it on the Collections page with its count, open it and see the matching items, create a new matching item and see it appear on reload, edit the conditions, remove a field via the API and see the warning, confirm adding items is not offered, and that another user cannot open it (404). Run three times in a row.
- [ ] **Step 2: DECISIONS entry**: kind and definition storage, the bridge pattern, R18-R21, the capped count, the 32,767-parameter ceiling removal for smart collections.
- [ ] **Step 3: Full gates:** `uv run poe lint && uv run poe typecheck && uv run poe test && uv run poe coverage`; revert formatter changes to unrelated docs.
- [ ] **Step 4: Stop for review**, then a whole-phase review on the strongest model with the Review Focus list as its checklist.

**Checkpoint:** user may commit.

---

## Self-Review

**Spec coverage (phase 2).** `kind=dynamic` and definition → Task 1; validation port and member resolution through a bridge → Tasks 2-3; `GET /node?collection=` through the engine → Task 3; computed count and ETag → Tasks 2-3; 409 on add/remove → Tasks 1 and 3; save-as, edit, collection page changes → Tasks 4-5; removal of the `IN (ids)` ceiling for smart collections → Task 3 (search, not id lists); e2e → Task 6. Pack changes are phase 4; "in collection" is phase 2b.

**Placeholders.** None intended. Tasks 2 and 3 name ports and signatures but leave the exact wiring to the implementer reading the existing bridges, which is deliberate: those files are the pattern to follow.

**Type consistency.** `definition` is `dict[str, Any] | None` in the domain, the model and the API; `DefinitionWarning` (collections) mirrors graph's `QueryWarning` field for field; `item_count_capped` appears in the summary, the schema and the frontend model.
