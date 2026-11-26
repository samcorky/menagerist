# Bulk Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Select several items in the Items list or a collection page and delete them, tag or untag them, add them to or remove them from a collection, or connect them all to one item, each as a single all-or-nothing request.

**Architecture:** Four batch commands on the backend, each one use case and one unit of work, so nothing half-applies. On the frontend, one selection controller plus one shared action bar, reached from the two pages that render item lists. Delete follows design §14: the request is deferred until the 5-second Undo window ends or the person navigates away.

**Tech Stack:** FastAPI, SQLAlchemy/Postgres, SvelteKit (Svelte 5 runes), shadcn-svelte, Playwright.

**Spec:** GitHub issue #499, DESIGN_GUIDELINES §7d and §14, and the decisions under "Decisions" below (they are this plan's calls; the person has agreed to none of them yet).

## Decisions (my calls, to confirm)

- **Select all means the rows loaded on screen**, capped at 200 per action. The count says so ("200 selected, the most one action takes"). Acting on a whole filtered result is a later change: it needs query-based commands.
- **The selection survives searches and filters within the page**, so a person can pick items from several searches and act on them together. The cap counts all selected items, hidden ones included. The bar shows how many selected items the current view hides (`12 selected, 5 not shown by this search`) and a Clear. Select all is a three-state checkbox in the bar that reflects the rows in view only: empty when none of them is selected, dashed (indeterminate) when some are, ticked when all are. Pressing it ticks every visible row unless all are already ticked, then it clears them. Hidden selections are never touched by it. Leaving the page, or switching collection, ends the selection, and so does Exit.
- **Every batch is all-or-nothing.** An unknown, deleted or inaccessible id fails the whole request with 422 `Unknown or deleted items: <ids>` (the wording `add_items_to_collection` already uses), and the page reloads the list. Duplicate ids are collapsed. An empty list is 422. More than 200 is 422.
- **Delete has no restore endpoint of its own.** Undo works by not sending the request until the 5 seconds pass, as §14 says; navigation sends it at once.
- **Connect reuses `POST /edge/batch`** with a new `reverse: bool = False`: when true, `source_id` is the shared node and each of `target_ids` is the source of its own edge into it ("these 12 stored in Box 3"). Existing callers are unaffected.
- **Scope of the first slice:** Items list and collection page, list and grid views. Search results and Home are out.

## Global Constraints

- Backend: dependency direction `entrypoints → adapters → application → domain`; every use case sets `access = ...` and implements `_handle`; commands depend on `UnitOfWork` and call `commit()`; each port keeps an in-memory sibling; strict mypy; layer coverage floors in AGENTS.md (domain and application 100%).
- Routes follow `docs/API_STYLE.md` (read it before naming the three new routes); run `poe dump-schema`, `poe lint-schema` and `poe generate-frontend-client`; never hand-edit `src/lib/api/generated/`.
- Frontend: Svelte 5 runes, `resolve()` for hrefs, collector-facing words only (never "node", "edge"), British English, native selects for fixed choices (design §15), reduced-motion respected.
- UI uses design §7d (explicit entry, count, Select all, an exit that does nothing, bottom action bar on phones) and §14 (Undo 5 seconds, navigation commits at once).
- Never stage or commit on the person's behalf; the commit steps below are for the person to run.

## Review Focus

- An id in the selection was deleted in another tab: the request fails with 422, the list reloads, the selection drops the missing rows, and nothing else was changed.
- Connecting a selection that includes the target item itself: refuse (422), do not create a self-connection.
- The search or filter changes while rows are selected: the selection stays, the bar says how many are out of view, and delete's toast counts them (`5 items deleted`), so nothing is acted on unseen. Switching collection or leaving the page ends the selection.
- Delete then Undo, delete then navigate away within 5 seconds, delete then close the tab: Undo sends nothing; navigation sends it once; closing the tab inside the window drops the pending delete, which is acceptable because the items are untouched; a test pins that Undo sends nothing.
- Offline: the action bar's buttons are disabled with the existing offline wording; no queued writes.
- A token whose grants lack write access gets 403 on every batch route, and the bar is not shown to read-only accounts.
- Example items in the selection are deletable like any other.

## File Structure

- Backend `graph/application/`: new `delete_nodes.py`, `tag_nodes.py`; modify `create_edges.py` (reverse).
- Backend `collections/application/`: new `remove_items_from_collection.py`.
- Backend adapters: routes and schemas in `graph/adapters/api/node/`, `graph/adapters/api/edge/`, `collections/adapters/api/collection/`; wiring in each module's `dependencies.py`.
- Frontend `src/lib/selection.svelte.ts` (state), `src/lib/deferred-delete.ts` (Undo window), `src/lib/components/selection-bar.svelte`, `bulk-tag-dialog.svelte`, `bulk-collection-dialog.svelte`, `bulk-connect-dialog.svelte`; modify `node-card.svelte`, `node-grid-card.svelte`, `routes/items/+page.svelte`, `routes/collections/[id]/+page.svelte`.

---

### Task 1: Delete several items in one request

**Files:**
- Create: `backend/src/app/modules/graph/application/delete_nodes.py`
- Modify: `graph/adapters/api/node/router.py`, `graph/adapters/api/node/schemas.py`, `graph/adapters/api/dependencies.py` (the module's wiring), `backend/tests/architecture/test_access_stances.py` (pin the new `Content` use case)
- Test: `backend/tests/modules/graph/application/test_delete_nodes.py`, plus a router test beside the existing node router tests

**Interfaces:**
- Produces: `DeleteNodesCommand(node_ids: list[uuid.UUID])`; `DeleteNodes(CommandHandler[GraphUnitOfWork, DeleteNodesCommand, None])` with `access = Content(GraphPermission.ITEM_WRITE)`; route `POST /node/batch-delete` (`operation_id="delete_nodes"`, 204, body `{"ids": [uuid]}`).

- [ ] **Step 1: Write the failing tests** in `test_delete_nodes.py`: deleting three items marks all three deleted in one commit; one unknown id raises `ValidationError("Unknown or deleted items: <id>")` and deletes none; an item another account owns (no write rights) fails the whole batch; duplicate ids delete once; empty list and 201 ids raise `ValidationError`.
- [ ] **Step 2: Run** `poe test-backend --mode agent -- backend/tests/modules/graph/application/test_delete_nodes.py` and confirm it fails (module missing).
- [ ] **Step 3: Implement `DeleteNodes`** by mirroring `delete_node.py`: load every id with `self.scope(actor)`, collect missing ids into one error, `assert_can_delete` on each, `soft_delete()` each, one `commit()`. Share the 200-id cap and the unknown-ids message through one small helper in `graph/application/` used by Tasks 1, 2 and 4 (name it `batch_ids.py`: `def check_batch_ids(ids: list[uuid.UUID]) -> list[uuid.UUID]`, returning the de-duplicated list or raising `ValidationError`).
- [ ] **Step 4: Add the route and schema** (`DeleteNodesRequest(ids: list[UUID])`), the dependency provider, the stance pin, and a router test for 204, 422 and 403.
- [ ] **Step 5: Run** the two test files and `poe test-backend-fast --mode agent`; expect PASS.
- [ ] **Step 6: Commit** (the person runs it): `feat(graph): delete several items in one request (#499)`.

### Task 2: Tag and untag several items in one request

**Files:** Create `graph/application/tag_nodes.py`; modify the node router, schemas and dependencies; test `backend/tests/modules/graph/application/test_tag_nodes.py` and a router test.

**Interfaces:**
- Consumes: `check_batch_ids` from Task 1.
- Produces: `TagNodesCommand(node_ids: list[uuid.UUID], add: list[str], remove: list[str])`; `TagNodes` with `Content(GraphPermission.ITEM_WRITE)`; route `POST /node/batch-tags` (`operation_id="tag_nodes"`, 200, returns `{"updated": int}`).

- [ ] **Step 1: Write failing tests:** adds a tag to three items; removes one; add and remove together; tags are normalised the way `_normalise_tags` does (trimmed, lowercased, de-duplicated); a tag already present is not duplicated and the item is not counted as updated; `add` and `remove` both empty is 422; one unknown id fails all and changes none.
- [ ] **Step 2: Run to confirm failure.**
- [ ] **Step 3: Implement `TagNodes`:** per node compute the new tag list (existing order kept, additions appended, removals filtered), save only nodes whose tags changed, one `commit()`. Reuse the node's own tag normalisation; do not re-implement it.
- [ ] **Step 4: Route, schema, wiring, stance pin, router test.**
- [ ] **Step 5: Run tests; expect PASS.**
- [ ] **Step 6: Commit:** `feat(graph): tag or untag several items in one request (#499)`.

### Task 3: Take several items off a collection in one request

**Files:** Create `collections/application/remove_items_from_collection.py`; modify the collection router, schemas and dependencies; test `backend/tests/modules/collections/application/test_remove_items_from_collection.py` and a router test.

**Interfaces:**
- Produces: `RemoveItemsFromCollectionCommand(collection_id: uuid.UUID, item_ids: list[uuid.UUID])`; route `POST /collection/{collection_id}/items/remove` (`operation_id="remove_items_from_collection"`, 204). It keeps `remove_item_from_collection`'s rules: removing an absent item is a no-op, and a smart collection refuses (the existing `_SMART` response).

- [ ] **Step 1: Write failing tests** modelled on `test_remove_item_from_collection.py`: removes several; an item not on it is skipped without error; a smart collection raises its existing error; an unknown collection raises not-found; over 200 ids is 422.
- [ ] **Step 2: Run to confirm failure.**
- [ ] **Step 3: Implement** with one unit of work and one commit; reuse the membership repository method the single-item use case calls, adding a bulk form to its port, in-memory adapter and Postgres adapter together.
- [ ] **Step 4: Route, schema, wiring, router test.**
- [ ] **Step 5: Run tests; expect PASS.**
- [ ] **Step 6: Commit:** `feat(collections): take several items off a collection in one request (#499)`.

### Task 4: Connect many items to one

**Files:** Modify `graph/application/create_edges.py`, the edge router and schemas (`CreateEdgesRequest`), and `backend/tests/modules/graph/application/test_create_edges.py`.

**Interfaces:**
- Produces: `CreateEdgesCommand.reverse: bool = False` and `CreateEdgesRequest.reverse: bool = False`. With `reverse=True`, `source_id` is the shared node and each `target_id` is the source of its own edge into it.

- [ ] **Step 1: Write failing tests:** with `reverse=True` and targets A, B, C, three edges run A→box, B→box, C→box; an existing edge of the same type in either direction is skipped and reported in `skipped`; `source_id` appearing in `target_ids` raises `ValidationError`; the default behaviour is unchanged (existing tests stay green).
- [ ] **Step 2: Run to confirm failure.**
- [ ] **Step 3: Implement** by swapping which id becomes `Edge.source_id` and `Edge.target_id` when `reverse` is true; the existing either-direction duplicate check already covers skipping.
- [ ] **Step 4: Update the route docstring and the schema example; add a router test.**
- [ ] **Step 5: Run tests; expect PASS.**
- [ ] **Step 6: Commit:** `feat(graph): connect many items to one in a single request (#499)`.

### Task 5: Schema and client

**Files:** `openapi.json`, `frontend/src/lib/api/generated/`.

- [ ] **Step 1:** Run `poe dump-schema`, `poe lint-schema --mode agent`, `poe generate-frontend-client`; expect the four operations (`delete_nodes`, `tag_nodes`, `remove_items_from_collection`, and the extended `create_edges`) in the generated client and no lint errors.
- [ ] **Step 2: Run** `poe coverage --mode agent`; expect the gate to pass.
- [ ] **Step 3: Commit:** `chore(api): regenerate the schema and client for bulk actions (#499)`.

### Task 6: Selection state

**Files:** Create `frontend/src/lib/selection.svelte.ts`; test `frontend/tests/selection.test.ts`.

**Interfaces:**
- Produces: `class Selection { active: boolean; ids: ReadonlySet<string>; count: number; atLimit: boolean; enter(): void; exit(): void; toggle(id: string): void; has(id: string): boolean; selectAll(visibleIds: string[]): void; deselectAll(visibleIds: string[]): void; hiddenCount(visibleIds: string[]): number; drop(ids: string[]): void }` with `SELECTION_LIMIT = 200`.

- [ ] **Step 1: Write failing tests:** `enter`/`exit` flip `active` and `exit` clears ids; `toggle` adds then removes; `selectAll` takes at most 200 and sets `atLimit`; `toggle` of a 201st id is refused; `hiddenCount` counts selected ids missing from the visible list; `selectAll` and `deselectAll` touch only the visible ids and leave hidden ones alone; `drop` removes the given ids (used after a 422 names missing items); `exit` does nothing else (no ids remain, no calls made).
- [ ] **Step 2: Run** `poe test-frontend --mode agent`; expect FAIL.
- [ ] **Step 3: Implement** as a small class with `$state` fields.
- [ ] **Step 4: Run; expect PASS.**
- [ ] **Step 5: Commit:** `feat(frontend): selection state for bulk actions (#499)`.

### Task 7: Selectable cards

**Files:** Modify `node-card.svelte`, `node-grid-card.svelte`; tests in their existing component tests (or a new `tests/node-card-selection.test.ts` beside them).

**Interfaces:**
- Consumes: nothing from Task 6 directly; the cards take props.
- Produces: new optional props `selectable?: boolean`, `selected?: boolean`, `onselect?: () => void`, `onlongpress?: () => void`.

- [ ] **Step 1: Write failing tests:** with `selectable`, the card shows a checkbox with the accessible name `Select <item name>`; clicking the card calls `onselect` and does not navigate; without `selectable` the card is the same link as today; a 500 ms touch hold calls `onlongpress` once and the following click does not navigate; the checkbox is at least 44 px to tap.
- [ ] **Step 2: Run; expect FAIL.**
- [ ] **Step 3: Implement** the checkbox (existing `ui/checkbox`), the click interception and the long-press timer. The long-press must not fire while the page scrolls. Keep arrow-key navigation working in select mode and add Space to toggle.
- [ ] **Step 4: Run; expect PASS. Then** `poe typecheck-frontend --mode agent`.
- [ ] **Step 5: Commit:** `feat(frontend): let item cards be selected (#499)`.

### Task 8: Selection bar and delete with Undo

**Files:** Create `selection-bar.svelte`, `frontend/src/lib/deferred-delete.ts`; tests `tests/deferred-delete.test.ts`, `tests/selection-bar.test.ts`.

**Interfaces:**
- Produces: `deferDelete(ids: string[], send: () => Promise<void>, options?: { windowMs?: number }): { undo(): void; flush(): Promise<void> }` (sends after `windowMs`, default 5000, unless undone; `flush` sends at once and is what navigation calls). `SelectionBar` props: `count`, `hidden` (selected but not in view), `limit`, `visibleSelected`, `visibleTotal`, `ontogglevisible`, `onclear` (drops every selection, hidden included, and stays in select mode), `onexit`, and snippet slots for the page's actions; it is fixed above the bottom navigation on phones and a bar above the list on desktop.

- [ ] **Step 1: Write failing tests:** `deferDelete` sends once after 5000 ms; `undo()` before then sends nothing; `flush()` sends at once and the timer then sends nothing more; a failed send reports the error to the caller. The bar shows `N selected`, plus `, M not shown by this search` when `hidden > 0`, a Select all checkbox that is `unchecked`, `indeterminate` or `checked` as the visible rows are none, some or all selected (it has the accessible name `Select all` and `aria-checked="mixed"` when some are), `Clear`, and an exit button that calls only `onexit`; at the limit the count reads `200 selected, the most one action takes`; with the app offline the action buttons are disabled with the existing offline wording.
- [ ] **Step 2: Run; expect FAIL.**
- [ ] **Step 3: Implement** both. The toast copy is `N items deleted` with an Undo action lasting 5 seconds (§14). Navigation (`beforeNavigate`) calls `flush`.
- [ ] **Step 4: Run; expect PASS.**
- [ ] **Step 5: Commit:** `feat(frontend): selection bar and deferred bulk delete (#499)`.

### Task 9: Tag, collection and connect dialogs

**Files:** Create `bulk-tag-dialog.svelte`, `bulk-collection-dialog.svelte`, `bulk-connect-dialog.svelte`; tests beside each.

**Interfaces:**
- Consumes: the generated client (`tagNodes`, `addItemsToCollection`, `removeItemsFromCollection`, `createEdges`) and the existing `query-item-picker.svelte` and relationship type picker.
- Produces: each dialog takes `ids: string[]`, `open`, `ondone(result)`; all use `responsive-dialog` so they become sheets on phones.

- [ ] **Step 1: Write failing tests:** the tag dialog sends `{ ids, add, remove }` and shows `Tagged N items`; the collection dialog adds to a chosen collection, and on a collection page offers `Remove from <collection>`; the connect dialog needs a relationship type and one target item, excludes selected items from the picker, and sends `reverse: true`; each shows the 422 message and keeps the selection on failure; each disables its primary button while sending.
- [ ] **Step 2: Run; expect FAIL.**
- [ ] **Step 3: Implement** the three dialogs; for failures use `networkAwareError` as the other pages do.
- [ ] **Step 4: Run; expect PASS.**
- [ ] **Step 5: Commit:** `feat(frontend): tag, collect and connect several items at once (#499)`.

### Task 10: Wire the two pages

**Files:** Modify `routes/items/+page.svelte`, `routes/collections/[id]/+page.svelte`; add `Select` to each toolbar; e2e `frontend/tests/e2e/bulk-selection.spec.ts` (desktop) and `bulk-selection.mobile.spec.ts`.

- [ ] **Step 1: Write failing e2e tests:** Select reveals checkboxes and a count; Select all selects the loaded rows; exit changes nothing; delete three items shows the Undo toast, Undo keeps them, and letting it lapse removes them; tag two items and see the tag on both; add three to a collection; on the collection page remove two; connect four items to a box through `Stored in` and see each on the box's page; on a phone, long-press enters selection and the bar sits above the bottom navigation without overlapping it (use `box()`'s settle wait from `layout.mobile.spec.ts`); selecting two items, changing the search, selecting one more shows `3 selected, 2 not shown by this search`, and one action then acts on all three.
- [ ] **Step 2: Run** `poe test-e2e --mode agent` for the new spec; expect FAIL.
- [ ] **Step 3: Implement the wiring:** one `Selection` per page, selection kept across search and filter changes, ended when the page unmounts or the collection changes, `drop` for ids a 422 names as missing, cards given the selection props, the bar and dialogs mounted, delete through `deferDelete` with the pending ids hidden from the list until Undo or the send lands.
- [ ] **Step 4: Run e2e, the frontend unit tests, lint and typecheck; expect PASS.**
- [ ] **Step 5: Commit:** `feat(frontend): select and act on several items in lists (#499)`.

### Task 11: Docs and screenshots

**Files:** Modify `frontend/DESIGN_GUIDELINES.md` §7d (record what shipped: the 200 cap, Select all means loaded rows, the actions and where they appear), the shipped-features list in `README.md` if it carries one, and the PR description with Playwright screenshots (list view, grid view, phone bar).

- [ ] **Step 1:** Update §7d; check links with the repository's documentation checks.
- [ ] **Step 2:** Capture the screenshots with Playwright and attach them to the PR (the project expects them for new UI).
- [ ] **Step 3: Commit:** `docs: record how bulk selection works (#499)`.

---

## Self-review

- **Spec coverage:** every action in the issue has a backend task (1–4) and a dialog or bar action (8–9); explicit entry, count, Select all and a do-nothing exit are in Tasks 6 and 8; the bottom bar and long-press in Tasks 7–8; Undo in Task 8; one request per action in Tasks 1–4.
- **Not covered, on purpose:** acting on a whole filtered result, search results and Home, and restoring deletes after the window.
- **Type consistency:** `check_batch_ids`, `Selection`, `SELECTION_LIMIT` and `deferDelete` are named once and consumed by name in later tasks.
- **Proportion:** tests and signatures are given, bodies are not.
