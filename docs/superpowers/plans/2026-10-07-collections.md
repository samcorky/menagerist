# Collections (manual shelves) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a person create named shelves ("My vinyl"), put items on them from the item page or the shelf page, and browse a shelf with the same search and filters as the items page.

**Architecture:** A new `collections` bounded context owns the `Collection` entity, its memberships, and its use cases. It never imports `graph`: it owns an `ItemLookup` port, and `graph` owns a `CollectionMembers` port; adapters in `entrypoints/api/shared/` bridge them (the pattern used by `examples` and `ChoiceListSource`). The item list gains an `ids` repository filter and a `collection` query parameter. The frontend adds a Collections page, a shelf page and an "Add to collection" action.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy and Alembic, pytest (plus testcontainers, archunitpython); SvelteKit with Svelte 5 runes, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-07-collections-design.md`. Read it first.

**State of this plan:** implemented (2026-10-07). See the spec's "What changed during implementation" for deviations; deferred minors are in the ledger kept under `.superpowers/sdd/` while the work was in progress.

## Global Constraints

- Collections are first-class entities, not items. User-visible text says *collection*; never node, edge or graph.
- Soft delete everywhere (`deleted_at`). Primary keys `uuid7`. Timestamps set in domain methods via `datetime.now(UTC)`. Entity dataclasses `kw_only=True, eq=False`.
- The application owns every constraint. Database indexes and primary keys are backstops, and must agree with the rule the use case checks.
- Dependency rule `entrypoints → adapters → application → domain`; `collections` must not import `graph` or `presets`, and `graph` must not import `collections` (architecture tests enforce it).
- Every port ships an in-memory sibling adapter in `adapters/persistence/`. Commands depend on `UnitOfWork` and commit; queries depend on a repository and do not.
- Coverage floors: domain 100%, application 100%, shared_kernel 100%, adapters 80%, platform 70%.
- `mypy --strict` including tests (every test function annotated and docstringed); ruff select-ALL; mccabe at most 8. Test file basenames must be unique (no `__init__.py` in `backend/tests`).
- British English in copy, comments and docs. Comments short and only where intent is unclear. Google-style docstrings.
- Never commit, stage or push. The user commits.
- All `.svelte` and `.svelte.ts` work goes through the `svelte-file-editor` subagent. Read `frontend/README.md` and `frontend/DESIGN_GUIDELINES.md` first; use `resolve()` for hrefs, `delayedLoading` for loading states, toasts via `svelte-sonner`, `ResponsiveDialog`/`ConfirmDialog` for confirmations, and return focus after dialogs.
- Regenerate the API client with `poe generate-frontend-client` after any API change; never edit `src/lib/api/generated/`.

## Execution order and parallelism

```
Phase 1 (graph: ids filter + collection filter) ──┐
Phase 2 (collections module, backend) ────────────┼─► Task 2.8 (bridges) ─► Task 2.9 (API) ─► Phase 3 (frontend) ─► Phase 4 (docs)
```

Tasks 2.1 to 2.7 do not depend on Phase 1 and may run alongside it. Task 2.8 needs both. Run subagent tasks one at a time (they share the working tree).

## Rulings made while planning

- **Which shelves is an item on:** `GET /api/v1/collection?item_id=<id>` (a filter on the list) replaces the spec's `GET /collection/membership?item_id=`, which would collide with `/{collection_id}`. Update the spec's API table to match.
- **Slug uniqueness is global among live collections** for now (multi-user later). Slug derivation: `slugify(name)`, falling back to `collection` if that is empty (a name of only symbols), then `-2`, `-3`, … until free. An explicit slug is normalised with `Slug` and conflicts with 409.
- **Adding an unknown or deleted item** is a `ValidationError` (422) listing the ids; adding an item already on the shelf is a silent no-op.
- **Counts and liveness:** membership rows for deleted items stay; reads and counts go through `ItemLookup`, so they are ignored.

## Review Focus

- A shelf containing an item that is later deleted: the shelf's count and `?collection=` list ignore it, with no error. Pin in Tasks 2.5 and 1.3.
- A collection that is deleted: its `?collection=` list is a 404, not an empty list. Pin in Task 1.3.
- Adding the same item twice, or two requests racing to add it: one membership, no error. Pin in Task 2.5 (use case) and Task 2.6 (primary-key backstop).
- A name made only of symbols ("★★★") or empty after trimming: empty is a 422; symbols give slug `collection`. Pin in Tasks 2.2 and 2.4.
- A very large shelf passed as an `IN (...)` list: the adapter chunks nothing but the port hides it; document the limit and test with several hundred ids. Pin in Task 1.2.
- Deleting a shelf then creating one with the same name: the slug is reusable. Pin in Task 2.6 (partial index) and Task 2.4.

---

## Phase 1: `graph` filters by ids and by collection

### Task 1.1: `ids` filter on the node repository

**Files:** `backend/src/app/modules/graph/ports/node_repository.py`; `.../adapters/persistence/node_repository.py`; `.../in_memory_node_repository.py`; tests under `backend/tests/modules/graph/` next to the existing repository tests.

**Interfaces:**
- Produces: `NodeRepository.list(..., ids: collections.abc.Collection[uuid.UUID] | None = None)` and `NodeRepository.count(..., ids: collections.abc.Collection[uuid.UUID] | None = None)` (`import collections.abc`; do not confuse with the `Collection` entity). `None` means no restriction; an empty collection means no results.

- [ ] **Tests first (in-memory and integration):** `ids` restricts `list` and `count`; combines with `type`, `q`, `favourite`, `after`, `limit`; `ids=set()` returns nothing and counts zero; ids of deleted nodes never appear; paging by `after` stays in id order.
- [ ] Implement in the port, the SQL adapter (`NodeModel.id.in_(ids)`; short-circuit to an empty result for an empty collection) and the in-memory adapter.
- [ ] Checks: `poe lint-backend`, `poe typecheck-backend`, targeted tests.

### Task 1.2: `CollectionMembers` port in `graph`

**Files:** `backend/src/app/modules/graph/ports/collection_members.py`; `.../adapters/persistence/in_memory_collection_members.py`; tests.

**Interfaces:**
- Produces:

```python
class CollectionMembers(Protocol):
    async def item_ids(self, collection_id: uuid.UUID) -> set[uuid.UUID] | None:
        """Return the item ids on the collection, or None if it does not exist."""
```

- [ ] In-memory adapter holds a dict of collection id to ids (`None` result for an unknown id) so graph tests can drive it.
- [ ] Tests: unknown collection gives `None`; known gives its ids, including several hundred.

### Task 1.3: `ListNodes` accepts `collection`

**Files:** `.../application/list_nodes.py`; `.../adapters/api/node/router.py`; `.../adapters/api/dependencies.py` (inject the source like `choice_lists`); tests for the use case and router.

**Interfaces:**
- `ListNodesQuery` gains `collection: uuid.UUID | None = None`. `ListNodes` takes an optional `CollectionMembers` (required when `collection` is set).
- A missing or soft-deleted collection raises the graph `NotFoundError` subtype (404).

- [ ] **Tests first:** `collection` restricts to members; combines with `q`, `type`, `favourite` and paging; the total counts the same restriction; unknown collection is 404; a deleted item on the shelf is ignored; a collection with no members returns an empty list and total 0 (not 404).
- [ ] Implement: resolve ids through the port, pass `ids=` to both `list` and `count`. Router: `collection: uuid.UUID | None = None` query parameter. Until Task 2.8 provides the real source, `dependencies.py` wires an empty in-memory/no-op source behind a clearly named function so the app still starts; Task 2.8 replaces it.
- [ ] Checks as above, plus `poe generate-frontend-client` (committed generated types are ignored by git, so just confirm `typecheck-frontend` passes).

---

## Phase 2: `collections` backend module

### Task 2.1: Module skeleton and architecture rule

**Files:** `backend/src/app/modules/collections/{__init__,domain/__init__,application/__init__,ports/__init__,adapters/__init__}.py` and `adapters/{api,persistence}/__init__.py`; `backend/tests/architecture/test_architecture.py`.

- [ ] Add `test_collections_module_is_independent_of_graph_and_presets` mirroring the `examples` rule, and a reverse rule that `graph` does not import `collections`. Run it first and see it fail only if the module imports something forbidden (it passes on an empty module; keep it as a guard).
- [ ] Checks: architecture tests.

### Task 2.2: Domain

**Files:** `.../collections/domain/{collection,errors}.py`; `backend/tests/modules/collections/domain/test_collection.py`.

**Interfaces:**
- Produces `CollectionKind` (`MANUAL`), `Visibility` (`PRIVATE`), `Collection`, `Membership`, `InvalidCollectionError`, exactly as in the spec's domain section; `Collection.create(*, name, slug, owner_id, description=None)` and `rename(name)`.

- [ ] **Tests first:** create sets id (uuid7), timestamps, kind and visibility defaults; name is trimmed; empty or over-120 names raise `InvalidCollectionError`; `Slug` normalises an explicit slug; rename changes the name, touches `updated_at`, leaves the slug alone; soft delete via the mixin. 100% domain coverage.

### Task 2.3: Ports and in-memory adapters

**Files:** `.../ports/{collection_repository,membership_repository,item_lookup,unit_of_work}.py`; `.../adapters/persistence/in_memory_*.py` for each; `backend/tests/modules/collections/conftest.py` (a `World` with in-memory repos and a configurable `ItemLookup`, as in `tests/modules/examples/conftest.py`).

**Interfaces:**

```python
class CollectionRepository(Protocol):
    async def add(self, collection: Collection) -> None: ...
    async def save(self, collection: Collection) -> None: ...
    async def get(self, collection_id: uuid.UUID) -> Collection | None: ...        # live only
    async def get_by_slug(self, slug: str) -> Collection | None: ...                # live only
    async def list(self, *, after: uuid.UUID | None, limit: int) -> list[Collection]: ...

class MembershipRepository(Protocol):
    async def add(self, membership: Membership) -> None: ...
    async def remove(self, collection_id: uuid.UUID, item_id: uuid.UUID) -> None: ...
    async def item_ids(self, collection_id: uuid.UUID) -> set[uuid.UUID]: ...
    async def collection_ids_for(self, item_id: uuid.UUID) -> set[uuid.UUID]: ...

class ItemLookup(Protocol):
    async def live_ids(self, ids: Sequence[uuid.UUID]) -> set[uuid.UUID]: ...     # which of these are live items
```

- [ ] `CollectionsRepos` bundle and a `UnitOfWork` Protocol following `modules/examples/ports/unit_of_work.py`.
- [ ] Adapter tests: round trip, live-only reads, `list` ordered by id with keyset paging, membership add/remove/lookups both ways.

### Task 2.4: Application: create, get, list, update, delete

**Files:** `.../application/{create_collection,get_collection,list_collections,update_collection,delete_collection}.py` and tests (one file each, unique basenames).

**Interfaces:**
- `CreateCollectionCommand(name, description=None, slug=None)` returning the `Collection`; `ListCollectionsQuery(after, limit, item_id=None)` returning collections with `item_count` (members that are live items, via `ItemLookup`) and, when `item_id` is given, only shelves holding that item; `UpdateCollectionCommand(collection_id, name=None, description=None)` (slug is not updatable); `DeleteCollectionCommand(collection_id)`. Unknown or deleted ids raise a `CollectionNotFoundError`. ETag/`If-Match` handling follows the node type update use case.

- [ ] **Tests first:** slug derived from the name; derived slug gets `-2`, `-3`; name of only symbols gives `collection`; explicit slug conflict raises `ConflictError`; slug reusable after delete; update changes name and description only; delete is soft and leaves items and memberships; list with `item_id` filters; counts ignore deleted items.

### Task 2.5: Application: add and remove items

**Files:** `.../application/{add_items_to_collection,remove_item_from_collection}.py` and tests.

**Interfaces:**
- `AddItemsToCollectionCommand(collection_id, item_ids: list[uuid.UUID])` returns the number actually added; `RemoveItemFromCollectionCommand(collection_id, item_id)`.

- [ ] **Tests first:** adds several; duplicates in the request and items already on the shelf are skipped silently; any unknown or deleted id raises `ValidationError` naming them, and nothing is added; unknown collection is 404; removing an item not on the shelf is a no-op; an item deleted after being added no longer counts.

### Task 2.6: Persistence and migration

**Files:** `.../adapters/persistence/{models,collection_repository,membership_repository,unit_of_work}.py`; `backend/src/app/alembic/versions/h9c0d1e2f3a4_create_collections.py` (parent `g8b9c0d1e2f3`; confirm the head with `alembic heads` first); register the models where the others are; integration tests (`@pytest.mark.integration`).

- [ ] `CollectionModel(IdentifiableMixin, TimestampedMixin, SoftDeletableMixin, Base)`: `name`, `slug`, `description`, `kind`, `owner_id`, `visibility`; `__tablename__ = "collections"`; a **partial unique index on `slug WHERE deleted_at IS NULL`** (a backstop only; the use case already checks).
- [ ] `CollectionMemberModel`: composite primary key `(collection_id, item_id)`, `added_at`; no foreign key to `nodes` (cross-module references use ids); a foreign key to `collections`.
- [ ] Integration tests: round trip; live-only `get`/`get_by_slug`; the partial index rejects two live rows with one slug and allows reuse after soft delete; the membership primary key rejects a duplicate; `collection_ids_for`.
- [ ] Migration checks: pytest-alembic tests pass (upgrade and downgrade).

### Task 2.7: Router skeleton, schemas and dependencies (no cross-module wiring yet)

**Files:** `.../adapters/api/collection/{router,schemas}.py`; `.../adapters/api/dependencies.py`; include the router in `entrypoints/api/__init__.py`; router tests with in-memory dependencies.

- [ ] Endpoints and error mapping exactly as in the spec's API table, with the ruling above for `GET /collection?item_id=`. Routers translate only; named Pydantic models; `route_class=PermissionAwareRoute` on the leaf router.
- [ ] Router tests: each endpoint, each error status, ETag on `PATCH`, `Link`/`Total-Count` on the list, `PUT .../item` with a bad id returns 422 naming it.

### Task 2.8: Cross-module bridges

**Files:** `backend/src/app/entrypoints/api/shared/collection_items.py` (implements `ItemLookup` through the real graph repository/use cases and the `ids` filter from Task 1.1); `.../shared/collection_members.py` (implements graph's `CollectionMembers` from the collections repositories, returning `None` for a missing or deleted collection); replace the placeholder wiring from Task 1.3; bridge tests, including an in-process FastAPI test that creates a collection, adds items and lists `GET /node?collection=<id>`.

- [ ] Checks: `poe lint-backend`, `poe typecheck-backend`, architecture tests, `poe coverage`.

### Task 2.9: Regenerate the client

- [ ] `poe generate-frontend-client`; `poe typecheck-frontend` passes. Record the generated function names for Phase 3.

---

## Phase 3: Frontend

All Svelte work through the `svelte-file-editor` subagent.

### Task 3.1: Helpers with tests (no Svelte)

**Files:** `frontend/src/lib/collections.ts`; `frontend/tests/collections.test.ts`.

- [ ] Pure helpers: `describeItemCount(n)` ("1 item", "12 items", "No items"); `describeAddResult(added, requested)` ("Added 3 items" / "3 items were already there"); a friendly message mapper for a 422 that names missing items. Tests first.

### Task 3.2: Collections page and navigation

**Files:** `frontend/src/routes/collections/+page.svelte`; the navigation component (find with `grep -rn "Settings" frontend/src/lib/components/*nav*`); `frontend/src/routes/+page.svelte` only if Home should link to it.

- [ ] Cards with name, description and count; **New collection** opens a `ResponsiveDialog` (name, optional description) and navigates to the new shelf; empty state invites the first shelf; loading honours the 300 ms rule; error state with retry; a Collections entry beside Items.

### Task 3.3: Shelf page

**Files:** `frontend/src/routes/collections/[id]/+page.svelte`; reuse the items page's list and grid rendering (extract a shared component from `frontend/src/routes/items/+page.svelte` rather than copying, if that is practical; otherwise state why in the report).

- [ ] The items list scoped with `collection=<id>`, with search, type and favourite filters, list and grid views, the Example badge; **Add items** (search-and-tick dialog, excluding items already on the shelf); per-item **Remove from collection**; rename and description edit; delete with a confirmation that says items are kept; focus returns to the trigger after dialogs; works at phone width.

### Task 3.4: "Add to collection" on the item page

**Files:** `frontend/src/routes/items/[id]/+page.svelte`.

- [ ] A **Add to collection** action (picker of existing shelves with a "New collection" shortcut) and the shelves the item is on, as links, with remove.

### Task 3.5: E2E

**Files:** `frontend/tests/e2e/collections.spec.ts`.

Run on the throwaway database (`poe e2e-db-up`, `poe e2e-migrate`, `npx playwright test tests/e2e/collections.spec.ts` from `frontend/`, then `poe e2e-db-down`). Each test removes its shelves and items; assert only on the data it created.

- [ ] Create a shelf; it appears in the list with "No items".
- [ ] Add an item from the item page; the shelf page shows it and the count updates.
- [ ] Add items from the shelf picker; items already on the shelf are not offered.
- [ ] Search and filter inside a shelf.
- [ ] Remove an item from the shelf; the item still exists.
- [ ] Delete a shelf; items remain; creating a shelf with the same name works.
- [ ] Delete an item that is on a shelf; the shelf count drops.
- [ ] Checks: `poe lint-frontend`, `poe typecheck-frontend`, `poe test-frontend`, then `poe test-e2e` for the whole suite. Read its output, not just its exit code.

**Definition of done (Phase 3):** all frontend checks green; the full e2e suite passes; walked through in a browser at phone width and desktop.

---

## Phase 4: Documentation

- [ ] `docs/DECISIONS.md`: entries for (1) collections as their own module, shelves not folders, not items; (2) membership by id with liveness checked on read, so item deletion needs no cleanup; (3) the two ports and the `?collection=` filter; (4) global slug uniqueness now, per owner later; (5) manual first, dynamic deferred; (6) ownership and visibility are stored but NOT enforced (single fixed actor), so enforcing them through `AuthorizationPort` on get, list, update, delete, the membership endpoints, and the read path behind `GET /node?collection=` (the `CollectionMembers` bridge and `ListNodes` would need to take the requesting principal, a port-signature change) is a hard precondition for shipping multi-user (an automated review flagged the missing owner checks as IDOR; they are deliberately absent until then).
- [ ] `docs/ARCHITECTURE.md`: add `collections/` to the module list.
- [ ] `backend/README.md`: a short "Collections" paragraph beside the Example packs one, naming the two bridges in `entrypoints/api/shared/`.
- [ ] `frontend/README.md`: the Collections pages and `lib/collections.ts`.
- [ ] Spec: update the API table for the `?item_id=` ruling; mark the spec and this plan implemented with a short "what changed" note.
- [ ] Record the follow-ups below on the board.

## Verification before finishing

- [ ] `poe lint`, `poe typecheck`, `poe test`, `poe coverage`, and the full `poe test-e2e` (read the output).
- [ ] Manual walk-through at phone width: create a shelf, add from both places, browse, remove, delete.
- [ ] `git status` shows only intended files; the user commits.

## Risks and how the plan handles them

| Risk | Handling |
|---|---|
| Cross-module coupling creeping in | Two ports, one per direction, plus architecture tests in both directions (Task 2.1). |
| A huge `IN (...)` list | Hidden behind `CollectionMembers`; tested with hundreds of ids; swap to a join in the adapter if shelves grow. |
| Dangling memberships | Liveness checked on every read and count (Tasks 1.3, 2.4, 2.5). |
| Two sources of truth for slug uniqueness | Use case checks, partial index is the backstop; tested both ways (Tasks 2.4, 2.6). |
| Items page duplicated for the shelf page | Extract a shared list component (Task 3.3). |

## Follow-ups (separate specs)

- Dynamic collections (#190): saved filters once search can filter on more than type, text and favourite.
- A `collections` section in example packs (pack format version bump), then the Koillection-style pack.
- Ordering within a shelf (a `position` on membership); bulk add from the items list.
- Sharing and enforcing visibility and permissions with RBAC; slug uniqueness per owner.
- A badge or filter for items by shelf on the items list.
