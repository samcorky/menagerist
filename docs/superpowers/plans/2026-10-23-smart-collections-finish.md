# Smart collections: finish (create dialog, connection conditions, example packs) and example pack purge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the smart collections work after phase 2: create a smart collection from "New collection", add connection conditions (spec phase 3), and let example packs ship smart collections (spec phase 4). Part D fixes a separate bug found on the way: removing an example pack only soft-deletes what it created, so the rows pile up in the data export.

**Architecture:** Everything extends the phase 1 query tree and the phase 2 `kind=dynamic` collection. Connection conditions are graph-internal (edges live in `graph`), so they need no external-predicate port: the SQL adapter compiles them to `EXISTS` / `NOT EXISTS` over `edges` and the in-memory adapter reads the in-memory edge store. Packs carry a `definition` instead of `items` and rely on the install path that already validates definitions through the collections bridge.

**Tech Stack:** FastAPI, SQLAlchemy on Postgres, SvelteKit 5 runes, shadcn-svelte, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-14-smart-collections-advanced-search-design.md` (phases 3 and 4; the "Condition kinds", "Semantics worth fixing now" and "Performance" sections), `docs/DECISIONS.md` ("Smart collections: a stored search, resolved through bridges", R18 to R24) and `docs/superpowers/plans/2026-10-18-collection-description-media-conditions.md` (R25 to R28).

## Prerequisite

Run Tasks 2 to 6 of `2026-10-18-collection-description-media-conditions.md` first (the `media` and `collection` conditions, their frontend model, the builder rows, "Save as new, linked" and the end-to-end gates). Its Task 1 (description and name) is done. This plan edits the same files (`domain/query.py`, `query_sql.py`, `query_eval.py`, the builder components), so the two plans run one after the other, never in parallel. Task 1 below needs only the existing builder; Tasks 2 to 7 need that plan's Tasks 2 and 3 (the `ExternalConditions` provider threading in `query_sql.py` and `query_eval.py`); Part C needs everything before it.

## Global Constraints

- Never create, stage or push commits; the user commits at the checkpoints.
- British English; comments short and factual; the UI never says node, edge or graph ("connection", "linked item", "relationship").
- `entrypoints → adapters → application → domain`; `graph` and `collections` never import each other; `examples` imports neither.
- `.svelte` and `.svelte.ts` files go through the `svelte-file-editor` subagent. UI follows `frontend/DESIGN_GUIDELINES.md` (44 px targets, design tokens only).
- Subagents: Sonnet 5.5 at medium effort at most; Haiku for mechanical work; always pass `model` and `effort`.
- Coverage floors: domain, application, shared_kernel 100%; adapters 80%; platform 70%. Run `poe coverage` at the end of each part.
- The query format changes only additively (no version bump); `v` stays 1. Limits stay depth 4, 50 conditions, 200-character text, 50-item lists.
- A pack's `version` changes only if the pack uses a new format feature; existing packs and their ids are untouched.

## Rulings made while planning

- **S1 (create dialog):** "New collection" gains a kind choice, "List you fill" (default) and "Smart: matches conditions". Choosing Smart shows the existing query builder inline (the dialog is a sheet on mobile) and requires at least one condition; it saves through the existing `saveSmartCollection`. The kind is still fixed at creation (R18). Cost: no empty smart collection; a user wanting "everything" adds a trivial condition.
- **S2 (connection shape):** `{"kind": "connection", "mode": "exists" | "none" | "to", "relationship"?: slug, "direction"?: "out" | "in" | "any" (default "any"), "item"?: uuid, "where"?: group}`. `exists` needs at least one live connection matching `relationship` and `direction` whose far item is live, in the caller's scope and satisfies `where` if given; `none` is `NOT EXISTS` of the same; `to` is `exists` with the far item equal to `item` and takes no `where`. `exists` and `none` take no `item`. `where` cannot itself contain a connection condition (one level only); its conditions count towards the 50-condition limit. Soft-deleted connections and far items never count.
- **S3 (direction):** `out` means this item is the source, `in` means it is the target. For a relationship type declared non-directional the direction is ignored (either end matches). With no `relationship`, `out` and `in` apply to the stored source and target literally. Cost: one extra rule to explain in the builder help text.
- **S4 (stale):** an unknown or deleted `relationship` slug, or an `item` that is deleted or not visible, makes the condition false with a warning carrying its path (as stale fields do); under `not` it inverts and is flagged the same way. A far-end `where` naming a removed field is stale inside that `where`, with the nested path.
- **S5 (in-memory parity):** `InMemoryNodeRepository` gains read access to the in-memory edge store (the same object `InMemoryEdgeRepository` writes), wired in `build_in_memory_graph_repos`; constructed without edges it behaves as today. One shared table of scenarios runs against both adapters (the Postgres run is `integration`-marked), as for earlier conditions.
- **S6 (packs):** pack format 6 lets a collection carry `definition` (a query tree object) instead of `items`; giving both, or neither, is a parse error. A pack definition may use only things a pack can name stably: item type slugs, relationship slugs, field keys and the portable condition kinds. The pack parser rejects `collection` conditions and a connection `item` id (they would need id remapping), by walking the JSON generically (examples cannot import graph). Everything else is validated at install by the collections module's definition check; a definition that does not validate rolls the install back like any other failure. Today the install wiring passes `RejectingDefinitionChecker` (`entrypoints/api/shared/bridges/example_targets.py`), which raises for any definition, so Task 7 replaces it with the real checker used by the collection routes. Cost: no pack smart collection can reference another collection or one specific item.
- **S7 (installed packs):** nothing migrates existing installs; people who already installed a pack keep their hand-built lists. Cost: the shipped example and an old install differ until the pack is reinstalled.
- **S8 (which collections convert):** convert a hand-built pack collection only where an honest rule exists in that pack's own data (field keys read from the pack file in the task, not guessed); otherwise leave it manual and say why in the task report. Candidates: parts *Running low*, games *Games for two* and *Still to try*; add one or two connection-based collections, for example films with no viewing connected (`none`, `in`, `movies-of`) and games never played (read the real relationship in `games.json`).

## Review Focus

1. A connection whose far item is soft-deleted, or whose edge is soft-deleted, does not match (Task 3).
2. `not` over a connection with a far-end `where`, and `none` for an item with no connections at all (Task 3).
3. A renamed or deleted relationship type: the saved collection loads, shows a warning, and its card count does not error (Tasks 2, 3).
4. `none` and `exists` stay index-backed on a large owner (100,000 items, 300,000 edges): EXPLAIN shows index lookups on `edges.source_id` / `target_id`, not a scan per item (Task 3).
5. Installing the same pack twice, or into an account that already has a type with the same slug, does not duplicate or break a pack smart collection (Task 7).
6. A pack smart collection survives uninstall and reinstall correctly, and its count equals what the pack data implies (Task 8).

---

## Part A: Create from "New collection"

### Task 1: Smart option in the New collection dialog

**Files:**
- Modify: `frontend/src/routes/collections/+page.svelte` (via the `svelte-file-editor` subagent), `frontend/src/lib/smart-collections.ts`
- Test: `frontend/src/lib/smart-collections.test.ts`, `frontend/tests/e2e/smart-collections.spec.ts`

**Interfaces:**
- Consumes: `saveSmartCollection(name, query)`, `describeSaveError`, `validateCollectionName`, the builder state (`builder-state.svelte.ts`) and `query-builder.svelte`, `isEmptyQuery` (or the equivalent in `lib/query/`; if none exists add `hasConditions(query: Query): boolean` to `lib/query/tree.ts`).
- Produces: `canCreateSmart(name: string, query: Query): string | null` in `smart-collections.ts` (the first reason it cannot be created, or `null`): name rules first, then "Add at least one condition."; the description field is sent for both kinds.

- [ ] **Step 1: Failing tests.** `canCreateSmart`: blank name, over-long name, no conditions, a valid case; if `saveSmartCollection` does not take a description today, extend it and test that the body carries it. E2E (isolated stack): open New collection, choose Smart, the builder appears, Create is disabled until a condition exists, create "Cheap parts" with one condition and land on its page showing the Smart badge and its matching items; choosing List you fill hides the builder and creates a manual collection as before; cancel discards state; the choice and builder are reachable by keyboard and usable at phone width.
- [ ] **Step 2: Implement** the helper, then dispatch `svelte-file-editor` (Sonnet, medium) for the dialog, reusing the builder components unchanged.
- [ ] **Step 3: Run** `poe lint-frontend`, `poe typecheck-frontend`, `poe test-frontend`; the new e2e three times; screenshots at desktop and phone width in light and dark.

**Checkpoint:** user may commit.

---

## Part B: Connection conditions (spec phase 3)

### Task 2: Domain, parser and resolution

**Files:**
- Modify: `backend/src/app/modules/graph/domain/query.py` (new `ConnectionCondition`, parser entry, limits), `backend/src/app/modules/graph/application/query_resolution.py` (validation and stale handling), `backend/src/app/modules/graph/application/prepare_query.py`
- Test: `backend/tests/modules/graph/domain/test_query_connection.py`, `backend/tests/modules/graph/application/test_query_resolution_connection.py`

**Interfaces:**
- Produces: `ConnectionCondition` frozen dataclass `(mode: Literal["exists","none","to"], relationship: str | None, direction: Literal["out","in","any"], item: uuid.UUID | None, where: Group | None)`; the parser accepts exactly the keys in S2 (an unknown key, a bad mode or direction, an `item` outside `to`, a missing `item` for `to`, a `where` with `to`, or a `where` containing a connection each raise the query-format error naming the path); `ResolvedQuery` gains `relationships: Mapping[str, RelationshipInfo]` with `RelationshipInfo(slug: str, directional: bool)` for each slug a connection names, and `visible_items: frozenset[uuid.UUID]` for each `to` item that exists in scope; unknown slugs and invisible items produce warnings (S4) with the condition path.

- [ ] **Step 1: Failing tests.** Parser: every valid form of S2, every rejection above, nesting depth and the 50-condition count including the far-end `where`. Resolution: a known relationship resolves with its `directional` flag; an unknown slug and a deleted edge type warn and are marked stale; a `to` item that is deleted, another owner's or unknown warns; a stale name inside the far-end `where` warns with a nested path (`where.children[0].where...` in the existing path style); validation uses the same lookups as field validation and performs no per-condition queries beyond one batched edge-type read and one batched node-id read.
- [ ] **Step 2: Run, expect failure.**
- [ ] **Step 3: Implement** following how `TagCondition` and `FieldCondition` are parsed, limited and resolved; add the edge-type and node lookups the resolution step needs to the existing graph read ports only if the current ones cannot answer them.
- [ ] **Step 4: Run** lint, mypy, `poe test-backend`, architecture and cqrs tests; domain and application 100%.

### Task 3: Evaluation on both adapters

**Files:**
- Modify: `backend/src/app/modules/graph/adapters/persistence/query_eval.py`, `query_sql.py`, `in_memory_node_repository.py`, `unit_of_work.py` (in-memory wiring per S5), `node_repository.py` if search needs the edge relation passed
- Test: a shared scenario table in `backend/tests/modules/graph/adapters/test_query_connection_scenarios.py` run on both adapters; Postgres-marked variant with EXPLAIN checks

**Interfaces:**
- Consumes: `ConnectionCondition`, `ResolvedQuery.relationships` and `visible_items` (Task 2), `matches()` for the far-end `where`.
- Produces: SQL compilation of `exists` / `none` / `to` as correlated `EXISTS` / `NOT EXISTS` over `edges` joined to the far `nodes` row (live edge, live far node, far node owned within the caller's scope, direction rules of S3, far-end `where` compiled with the same function used for the main tree against the aliased far-node table), and the Python evaluator with identical semantics; `InMemoryNodeRepository(edges: EdgeStore | None = None)`.

- [ ] **Step 1: Failing scenarios** (each asserted on both adapters): `exists` with and without `relationship`; each `direction`; a non-directional type matching from either end; `none`; `none` for an item with no edges; `to` an item, and `to` a deleted item (stale, no match); a soft-deleted edge and a soft-deleted far item do not count (Review Focus 1); far-end `where` on type, field and tag; `not` over a connection with a far-end `where` (Review Focus 2); a relationship slug that was deleted after saving matches nothing and warns (Review Focus 3); another owner's far item never matches; combined with sort, paging and `Total-Count`. Postgres only: at 100,000 items and 300,000 edges the plan uses the edge indexes (Review Focus 4); record timings for `exists`, `none` and a far-end `where` in the task report and add an index in a migration only if the numbers justify it.
- [ ] **Step 2: Run, expect failure.**
- [ ] **Step 3: Implement** the compiler and evaluator; wire the in-memory edge store; keep `GET /node` and `list` untouched.
- [ ] **Step 4: Run** lint, mypy, `poe test-backend`, the Postgres tests for the repository and search, architecture and cqrs tests; domain and application at 100%, adapters above 80%.

**Checkpoint:** user may commit.

### Task 4: Frontend model for connection conditions (plain TypeScript)

**Files:**
- Modify: `frontend/src/lib/query/types.ts`, `codec.ts`, `tree.ts`, `operators.ts`, `summary.ts`, `warnings.ts`, `limits.ts`, `builder-state.svelte.ts` is **not** touched here (Task 5)
- Test: `frontend/src/lib/query/*.test.ts` alongside each module

**Interfaces:**
- Produces: `ConnectionCondition` type matching S2; `decode`/`encode` round-trip it (and reject malformed forms into the existing "These conditions can't be shown" state, never a crash); `summariseCondition` words such as "Connected to anything by Directed by", "Has no linked item", "Connected to Casablanca" (item names are resolved by the caller and passed in, so `summary` stays pure); `countConditions` includes the far-end `where`; warnings from the response map to the right row path; `canNestConnection(depth)` is false inside a far-end `where`.

- [ ] **Step 1: Failing tests** for each of the above, including a far-end `where` round-trip, the limit count, the stale-warning path mapping and a rejected nested connection.
- [ ] **Step 2: Implement; run** `poe lint-frontend`, `poe typecheck-frontend`, `poe test-frontend`.

### Task 5: Builder rows for connections (Svelte)

**Files:**
- Modify (via `svelte-file-editor`): `frontend/src/lib/components/query-condition-row.svelte`, `query-group.svelte`, `query-builder.svelte`, `query-chips.svelte`, and `builder-state.svelte.ts`
- Test: component tests where the harness allows; Playwright in Task 6

**Interfaces:**
- Consumes: the connection model (Task 4), the relationship list the app already loads for the connection UI, and the existing item picker used when creating a connection (reuse it; do not build a second).
- Produces: a "Connection" condition kind with a mode select ("Has a connection", "Has no connection", "Is connected to"), a relationship select ("Any relationship" first), a direction select shown only for directional relationships ("Either way", "From this item", "To this item"), for `to` an item picker, and for `exists` an optional "Where the linked item…" nested group using the same row components but offering no connection kind (Task 4's `canNestConnection`). Labels use the relationship's own labels and reverse labels where they exist. Stale rows show the warning text from the response.

- [ ] **Step 1: Implement** through the subagent (Sonnet, medium) with the Task 4 helpers green; keep accessible names stable and use design tokens only.
- [ ] **Step 2: Run** lint-frontend, typecheck-frontend, test-frontend; check at desktop and phone width in light and dark and view the screenshots.

### Task 6: End-to-end, documentation and gates for Part B

**Files:**
- Modify: `frontend/tests/e2e/smart-collections.spec.ts`, `docs/DECISIONS.md`, `docs/superpowers/specs/2026-10-14-smart-collections-advanced-search-design.md` (mark phase 3 implemented), `backend/README.md`, `frontend/README.md`, `shared/README.md` if the operator fixture changes

- [ ] **Step 1: E2E** on the isolated stack: build "films with no viewing" with a `none` connection and save it; see the right items; connect a viewing and see the film leave on reload; build "connected to <item>" and "has a connection where the linked item is a <type>"; delete the relationship type via the API and see the warning with an empty list and no error; another account cannot open it (404). Run three times in a row.
- [ ] **Step 2: DECISIONS entry** for S2 to S5 (shape, direction rule, stale behaviour, the in-memory edge store) and the measured timings; update the spec status.
- [ ] **Step 3: Full gates:** `poe lint`, `poe typecheck`, `poe test`, `poe coverage`.
- [ ] **Step 4: Stop for review**, then a whole-part review (strongest permitted model) with Review Focus 1 to 4 as its checklist.

**Checkpoint:** user commits Part B.

---

## Part C: Example packs with smart collections (spec phase 4)

### Task 7: Pack format 6, install and uninstall

**Files:**
- Modify: `backend/src/app/modules/examples/domain/pack.py` (`PackCollection.definition`), `adapters/platform/pack_parser.py` (`PACK_VERSIONS = (1, 2, 3, 4, 5, 6)`, collection keys), `application/install_example_pack.py`, `application/removal.py`, `application/uninstall_example_pack.py` if needed, `ports/pack_targets.py` (the collection target creates a dynamic collection from a definition), `entrypoints/api/shared/bridges/example_targets.py` (delete `RejectingDefinitionChecker`; `CollectionPackTarget` builds `CreateCollection` with the real definition checker and passes the definition; the in-memory counterpart too), and the install dependency wiring that supplies the checker, the pack JSON schema if one exists under `shared/`
- Test: `backend/tests/modules/examples/domain/test_pack.py`, `adapters/platform/test_pack_parser.py`, `application/test_install_example_pack.py`, `test_uninstall_example_pack.py`, a Postgres install test

**Interfaces:**
- Produces: `PackCollection(ref, name, description, item_refs: tuple[str, ...] = (), definition: Mapping[str, Any] | None = None)` with the invariant "exactly one of items and definition" (S6); the parser accepts `definition` only at version 6 and applies S6's generic rejections (a `collection` condition, a connection `item`) with the path in the message; the install creates a `kind=dynamic` collection with the definition as given, in the same ordering step as manual collections (after item types, relationship types and items, so validation sees them); `PackCounts.collections` counts both kinds.

- [ ] **Step 1: Failing tests.** Parser: v6 with `definition` parses; `definition` at version 5 is rejected; both or neither of `items` and `definition` rejected; a `collection` condition and a connection with `item` rejected with paths; a non-object definition rejected. Install: a pack with a manual and a smart collection creates one of each, the smart one's stored definition equals the pack's, and its count reflects the installed items; a definition naming a field or type the pack does not create fails validation and **rolls the whole install back**; installing twice does not duplicate (Review Focus 5); installing into an account that already owns a clashing type slug follows the existing clash rules and never half-installs. Uninstall: the smart collection goes with the pack; reinstall after uninstall recreates it (Review Focus 6); a smart collection has no members, so none of the "kept because of a surviving collection" logic applies to it.
- [ ] **Step 2: Run, expect failure.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** lint, mypy, `poe test-backend`, Postgres tests for installs, architecture and cqrs tests; domain and application at 100%.
- [ ] **Step 5:** a test that `RejectingDefinitionChecker` is gone and that the install path uses the same checker as `POST /collection`.
- [ ] **Step 6: Frontend:** the examples page and pack preview show smart collections with the existing "Smart" badge wording and no item list (check `routes/settings/examples/+page.svelte` and the pack preview components; edit through `svelte-file-editor` only if a change is needed), with a Vitest or component test for the copy.

### Task 8: Convert and add pack collections, then gates

**Files:**
- Modify: `backend/src/app/modules/examples/packs/{parts,games,movies}.json` (and `index.json` only if pack versions or descriptions need to change), `backend/tests/modules/examples/packs/` (pack content tests), `docs/DECISIONS.md`, `backend/README.md`, the example pack authoring doc if one exists (`grep -ri "pack format" docs backend/README.md`)

- [ ] **Step 1: For each candidate in S8,** read the pack's own item types and field keys and decide: convert (replace `items` with a `definition` and bump that pack to version 6) or leave manual with a one-line reason in the report. A converted collection has a content test that installs the pack on the in-memory adapters and asserts the exact item names the definition matches (not just a count), so a later edit to the pack data that changes the answer is noticed.
- [ ] **Step 2: Add** one or two connection-based collections (S8) with the same kind of content test.
- [ ] **Step 3: E2E** on the isolated stack: install the Parts pack, open *Running low* (or its replacement) and see the right items with the Smart badge; uninstall and see it gone; reinstall.
- [ ] **Step 4: DECISIONS entry** (S6 to S8) and update the spec's phase 4 status; note S7 (installed packs do not change).
- [ ] **Step 5: Full gates:** `poe lint`, `poe typecheck`, `poe test`, `poe coverage`, the examples and smart-collection Playwright specs three times.
- [ ] **Step 6: Stop for review,** then a whole-part review with Review Focus 5 and 6 as its checklist.

**Checkpoint:** user commits Part C.

---

## Part D: Purge what example packs remove

Independent of Parts A to C; it can run first, or any time after the prerequisite. Findings (read from the code, not run):

- Every delete in the app is a soft delete (`SoftDeletable`; repositories filter `deleted_at IS NULL`). There is no hard delete for items, connections, collections or presets. The one hard delete is media cleanup (`CleanupExpiredMedia`, `System` stance, which also removes the stored files).
- `UninstallExamplePack` settles entities through `GraphPackTarget.remove` (`DeleteNode`, `DeleteEdge`, `DeleteUnusedNodeType`, `DeleteEdgeType`), `CollectionPackTarget.remove` (`DeleteCollection`), and the preset and cover targets. All soft-delete. The `example_installations` row is kept with `mark_removed()` as history.
- The per-person data export (`backup/adapters/persistence/user_database_snapshot.py`, `_predicates`) selects `nodes`, `edges`, `collections`, `media_assets` and `example_installations` by `owner_id` only, so soft-deleted rows are exported and a restore re-imports them. Vocabulary tables are already filtered by `deleted_at IS NULL`, so the content tables are the inconsistent ones.
- Collection membership rows have no foreign key to items (DECISIONS: "a membership row stores a collection id, an item id and when it was added"); `edges` have foreign keys to `nodes`, so connections must be purged before their items.

### Rulings (Part D)

- **P1:** removing a pack **hard-deletes** what it removes: the entity and everything that exists only because of it (connections of removed items, collection memberships, attachments and the assets and files only those attachments used). Entities the removal *keeps* (edited by the person, or still in use) are untouched. Cost: removal is no longer recoverable; no undo was ever offered, and the pack can be reinstalled.
- **P2:** the per-person export and the restore ignore soft-deleted content rows (`deleted_at IS NULL` on `nodes`, `edges`, `collections`, `media_assets`), matching the vocabulary tables. This fixes the export for all soft-deleted rows, not just packs. Cost: an item the person deleted by hand is not in their export; a future trash or undo feature needs its own export rule.
- **P3:** rows already left behind by earlier uninstalls are cleaned by an explicit command, `menagerist data purge-removed-examples [--dry-run]`, which purges only soft-deleted rows listed by `example_installations` records marked removed and owned by the same person. It touches nothing else. Cost: one command to run after upgrading; nothing happens automatically to existing data.
- **P4:** soft-deleted rows the person deleted by hand are purged after a retention period by an explicit command, `menagerist data purge-deleted [--older-than-days N] [--dry-run]`, default 30 days (setting `MENAGERIST_RETENTION_DELETED_DAYS`, minimum 1). Like `media cleanup` (the only existing cleanup, run from the CLI by cron or the operator) nothing runs it automatically. It purges `nodes`, `edges`, `collections` and `media_assets` rows whose `deleted_at` is older than the cutoff, and never touches soft-deleted item types, relationship types or presets (their deleted rows keep slugs reusable and other rows may still name them). Cost: deleted items are unrecoverable after the window; there is no undo feature to protect, so the window is a courtesy for restoring by hand from the database.

### Task 9: Hard-delete ports and use cases

**Files:**
- Create: `backend/src/app/modules/graph/application/purge_node.py` and `purge_edge.py`; `backend/src/app/modules/collections/application/purge_collection.py`; the media equivalent (read `media/application/cleanup_expired_media.py` and `delete_media.py` first and follow the smaller change: a purge for an item's attachments and the assets only they referenced)
- Modify: the repository ports and both adapters for `nodes`, `edges`, `collections` and `collection_members` (`purge` methods named to match each port's vocabulary), the preset repository if presets are soft-deleted, `tests/architecture/test_access_stances.py`, `tests/architecture/test_permission_mapping.py`
- Test: unit tests per use case on the in-memory adapters; Postgres tests for the repositories (connections before items; rows in other modules that point at an item)

**Interfaces:**
- Produces, all with `access = System()` (run from the uninstall flow as `SYSTEM_ACTOR`, like `DeleteUnusedNodeType`): `PurgeNode` (hard-deletes the node and its connections), `PurgeEdge`, `PurgeCollection` (the collection and its membership rows), and the media purge, which removes stored files through `MediaStoragePort` only after the transaction commits. An unknown id is treated as already gone.

- [ ] **Step 1: Failing tests.** Each purge removes the row and its dependants and nothing else (another item's connection to a third item survives; an asset still attached elsewhere survives); an unknown id is a no-op; a purged item's id disappears from `collection_members`; the stances are pinned `System` and no route reaches them.
- [ ] **Step 2: Run, expect failure.**
- [ ] **Step 3: Implement** the use cases and repository methods.
- [ ] **Step 4: Run** lint, mypy, `poe test-backend`, the Postgres tests, architecture and cqrs tests; application 100%.

### Task 10: Uninstall purges, exports skip deleted rows

**Files:**
- Modify: `backend/src/app/entrypoints/api/shared/bridges/example_targets.py` (the graph, collection, cover and preset targets switch from delete to purge for entities the removal actually removes), `modules/backup/adapters/persistence/user_database_snapshot.py` and `in_memory_user_database_snapshot.py` (P2), `user_database_restorer.py` and its in-memory twin (skip incoming soft-deleted content rows)
- Test: `backend/tests/modules/examples/application/test_uninstall_example_pack.py`, the bridge tests for the example targets, the backup snapshot and restorer tests, and a Postgres "install, uninstall, export" test

- [ ] **Step 1: Failing tests.** After installing and uninstalling a pack nothing it created remains in `nodes`, `edges`, `collections`, `collection_members`, `media_attachments` or `media_assets` (query the tables, not the repositories, so soft-deleted rows would show); something the person edited, or connected to their own item, is kept and not purged; install, uninstall, install gives a clean second install; an export of a person with soft-deleted content contains none of it and an export-then-restore round trip loses nothing live; restoring an old archive that contains soft-deleted rows ignores them without error; re-running an interrupted uninstall still works and the purge is idempotent.
- [ ] **Step 2: Run, expect failure.**
- [ ] **Step 3: Implement.** Keep the `RemoveResult` mapping (`REMOVED`, `ALREADY_GONE`, `REFUSED_IN_USE`) and the in-use checks exactly as they are; only the removal verb changes.
- [ ] **Step 4: Run** lint, mypy, `poe test-backend`, the Postgres tests for installs and exports, architecture and cqrs tests.

### Task 11: Clean up existing leftovers, docs and gates

> **Dropped (Sam, 2026-10-23):** no clean-up command for rows left by earlier removals (P3 is not built). Only the DECISIONS entry and the gates were done; see "Removing an example pack purges what it created" in `docs/DECISIONS.md`.

**Files:**
- Create: `backend/src/app/modules/examples/application/purge_removed_example_leftovers.py` (a `System` use case) and its CLI command `data purge-removed-examples [--dry-run]`, registered the way the `backup` and `identity` commands are in `entrypoints/cli/`
- Modify: `backend/README.md`, `CONTRIBUTING.md` (operations note), `docs/DECISIONS.md`
- Test: use case tests on in-memory adapters; CLI tests in the style of `tests/entrypoints/cli/test_backup_commands.py`; a Postgres test

**Interfaces:**
- Produces: `PurgeRemovedExampleLeftovers` returning counts per entity kind. It reads installation records marked removed, finds the entity ids they list that are still soft-deleted, and purges them with the Task 9 use cases. It never touches a live row, or a soft-deleted row that no removed installation lists (P3). `--dry-run` prints the counts and changes nothing.

- [ ] **Step 1: Failing tests.** Dry run changes nothing and reports counts; a real run purges only listed soft-deleted rows; a live entity that a removed installation still lists (kept by the person) is not purged; a soft-deleted item the person deleted by hand is not purged; a second run does nothing.
- [ ] **Step 2: Implement.**
- [ ] **Step 3: DECISIONS entry** for P1 to P4, naming the export change as a behaviour change, and an operations note: after upgrading, run `menagerist data purge-removed-examples --dry-run`, then without the flag, after taking a backup (the pre-migration backup does not cover this command).
- [ ] **Step 4: Full gates:** `poe lint`, `poe typecheck`, `poe test`, `poe coverage`; the examples Playwright specs once.
- [ ] **Step 5: Stop for review** with these checks: nothing live is purged; foreign-key order; files removed only after commit; the export no longer contains deleted rows; an old archive still restores.

### Task 12: Retention purge of hand-deleted content (P4)

> **Deferred (2026-10-23):** superseded by a planned "Recently deleted" view with restore and purge on request (hand-deleted content stays soft-deleted until then). Do not build `data purge-deleted`.

**Files:**
- Create: `backend/src/app/modules/graph/application/purge_deleted_content.py` (or one use case per module if the module boundary demands it: graph owns nodes and edges, collections owns collections, media owns assets; compose them in an entrypoints-level command, never by cross-module imports), the CLI command `data purge-deleted`
- Modify: `backend/src/app/platform/config/` (a `DeletedRetentionSettings` or a field on an existing group; add its getter to `INSTANCE_SETTINGS`), the repository ports and adapters from Task 9 (`list_deleted_before(cutoff)` style reads), `backend/README.md`, `CONTRIBUTING.md`, `docs/DECISIONS.md`
- Test: use case and CLI tests on in-memory adapters; Postgres tests

**Interfaces:**
- Consumes: the Task 9 purge use cases. Produces: `PurgeDeletedContent` with `PurgeDeletedContentCommand(older_than: datetime, dry_run: bool)` returning counts per kind, `System` stance; the command prints the counts and the cutoff.

- [ ] **Step 1: Failing tests.** Only rows with `deleted_at` older than the cutoff are purged (a row deleted a minute ago and one deleted 31 days ago, same owner); live rows, soft-deleted types and presets are never touched; a deleted item's connections and memberships go with it and a connection soft-deleted on its own goes when it is old enough; assets and files are removed after commit; `--dry-run` changes nothing; the minimum retention of 1 day is enforced; a second run is a no-op.
- [ ] **Step 2: Implement; DECISIONS entry (P4);** document the command next to `media cleanup` as something to run from cron.
- [ ] **Step 3: Run** lint, mypy, `poe test-backend`, Postgres tests, architecture and cqrs tests; then the full gates once for Part D.

**Checkpoint:** user commits Part D.

---

## Self-Review

- **Spec coverage:** phase 3 (connection conditions: engine in Tasks 2 and 3, both repositories, builder in Tasks 4 and 5), phase 4 (format bump, conversions, connection-based examples in Tasks 7 and 8), and the create-from-"New collection" gap (Task 1). Phases 2b and 2c stay in their own plan, named as the prerequisite; "currentUser()" and the account-to-item link stay out of scope (spec section "Future").
- **Types:** `ConnectionCondition`, `RelationshipInfo`, `ResolvedQuery.relationships` and `visible_items`, `PackCollection.definition` and `canCreateSmart` are named the same wherever they recur; the connection wire form is S2 everywhere.
- **Risks I could not verify without running code:** the exact shape of the existing `ResolvedQuery`, the path style for warnings and whether the far-end `where` can reuse the main-tree compiler against an aliased table (Task 3 may need a small refactor of `query_sql.py`); whether the games and movies packs hold fields that make an honest rule (S8 says to leave a collection manual rather than invent one).
- **Proportion:** each task gives signatures, rules and test assertions; compiler and evaluator bodies are left to the implementer.
