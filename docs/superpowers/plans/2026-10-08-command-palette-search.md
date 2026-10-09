# Search popup: grouped results across the app Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the `/` popup find items, collections, item types and pages in fixed-order groups, ranked best-first within each group.

**Architecture:** The backend gains one thing, a `q` text query on `GET /collection`. The frontend fans out to the existing list endpoints from a single `searchEverything(query)` function, filters item types and pages locally, ranks each group with one pure helper, and renders groups in the existing shadcn `Command` popup. No new endpoint, so a backend search endpoint can replace the fan-out later without UI changes.

**Tech Stack:** FastAPI, SQLAlchemy, pytest; SvelteKit 5 runes, bits-ui `Command`, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-08-command-palette-search-design.md` (builds on `2026-10-08-global-search-popup-design.md`).

## Global Constraints

- British English in copy, comments, docs. UI words: "collection", "item type", "page"; never node, edge, graph or shelf.
- Backend: Python 3.14, `mypy --strict` including tests, ruff, coverage floors (domain/application/shared_kernel 100%, adapters 80%). Modules `graph` and `collections` stay mutually independent (architecture tests), so collections gets its own small LIKE-escape helper rather than importing graph's.
- In-memory repositories alias stored objects; in-memory UoW does not roll back.
- Every `.svelte` / `.svelte.ts` edit goes through the `svelte:svelte-file-editor` subagent. Touch targets are at least 44 px. The 300 ms `delayedLoading` rule applies.
- Never `git add`/`commit`/`push`; the owner commits (one `git add -A`, because the pre-commit hooks lint the whole repo).
- Caps per group: Items 5, Collections 3, Item types 3, Pages 4. Query text is trimmed and capped at 200 characters (`normaliseQuery`).
- `lib/api/generated` is regenerated with `poe generate-frontend-client`, never hand-edited.

## Review Focus

- Text with LIKE wildcards (`%`, `_`, `\`) must match literally in the collections search, as it does for items.
- A blank or whitespace-only `q` on `GET /collection` returns the unfiltered list (the same as no `q`).
- `q` combined with `item_id` and paging: a page is never short only because non-matching collections sat between matches.
- One source failing (collections request errors) must not hide the other groups; "Nothing found" appears only when every source answered and all were empty.
- A slow earlier response must never overwrite a newer query's groups (stale-response guard across all sources).
- Group order never changes as sources answer at different speeds.

---

### Task 1: Collections `q` on the backend

**Files:**
- Modify: `backend/src/app/modules/collections/ports/collection_repository.py` (add `q` to `list`)
- Modify: `backend/src/app/modules/collections/adapters/persistence/collection_repository.py` (`list`, plus `_like_pattern` helper)
- Modify: `backend/src/app/modules/collections/adapters/persistence/in_memory_collection_repository.py` (`list`)
- Modify: `backend/src/app/modules/collections/application/list_collections.py` (`ListCollectionsQuery.q`, pass it on in `_page`)
- Modify: `backend/src/app/modules/collections/adapters/api/collection/router.py` (`q` query parameter)
- Test: `backend/tests/modules/collections/test_in_memory_collection_repository.py`, `backend/tests/modules/collections/adapters/test_sql_collection_repository.py` (integration), `backend/tests/modules/collections/application/test_list_collections.py`, `backend/tests/modules/collections/adapters/test_collection_router.py`

**Interfaces:**
- Consumes: the existing `CollectionRepository.list(*, after, limit)`.
- Produces: `CollectionRepository.list(*, after: uuid.UUID | None, limit: int, q: str | None = None)`; `ListCollectionsQuery(after, limit, item_id, q: str | None = None)`; `GET /collection?q=` (`Query(max_length=200)`; blank means unfiltered). Task 3 calls it as `listCollections({ query: { q, limit } })`.

- [ ] **Step 1: Write failing tests.** In-memory repository: `q` matches name or description case-insensitively as a substring; `%` and `_` match literally ("50%" does not match "500"); `None` and `""` return everything; combines with `after` and `limit`; deleted collections are excluded. Same cases against the SQL repository (marked integration). Use case: `q` plus `item_id` returns only matching collections that hold the item, and a page stays full (seed matches separated by non-matches, `limit` smaller than the gap). Router: `GET /collection?q=ta` returns the matching collections only, a whitespace-only `q` returns all, `q` over 200 characters answers 422.

- [ ] **Step 2: Run to confirm they fail.** `uv run pytest backend/tests/modules/collections -q` fails on the unexpected `q` argument.

- [ ] **Step 3: Implement.**

Port and in-memory adapter:

```python
async def list(
    self, *, after: uuid.UUID | None, limit: int, q: str | None = None
) -> list[Collection]:
    """Return up to `limit` live collections ordered by id, after `after`.

    A non-blank `q` keeps collections whose name or description contains it,
    ignoring case.
    """
    needle = (q or "").strip().casefold()
    live = sorted(
        (
            c
            for c in self._collections.values()
            if not c.is_deleted
            and (after is None or c.id > after)
            and (
                not needle
                or needle in c.name.casefold()
                or needle in (c.description or "").casefold()
            )
        ),
        key=lambda c: c.id,
    )
    return live[:limit]
```

SQL adapter (own helper; collections must not import graph):

```python
_LIKE_ESCAPE = "\\"


def _like_pattern(q: str) -> str:
    """Return a contains-pattern for `q` with LIKE wildcards escaped."""
    escaped = q.replace(_LIKE_ESCAPE, _LIKE_ESCAPE * 2)
    escaped = escaped.replace("%", _LIKE_ESCAPE + "%").replace("_", _LIKE_ESCAPE + "_")
    return f"%{escaped}%"
```

and in `list`, after the `after` filter:

```python
needle = (q or "").strip()
if needle:
    pattern = _like_pattern(needle)
    stmt = stmt.where(
        CollectionModel.name.ilike(pattern, escape=_LIKE_ESCAPE)
        | CollectionModel.description.ilike(pattern, escape=_LIKE_ESCAPE)
    )
```

Use case: add `q: str | None = None` to `ListCollectionsQuery`; pass `q=query.q` to both `self._repos.collections.list(...)` calls in `_page`. Router: add `q: Annotated[str | None, Query(max_length=200, description="Keep collections whose name or description contains this text.")] = None` and pass `q=q` into `ListCollectionsQuery`.

- [ ] **Step 4: Run to confirm they pass.** `uv run pytest backend/tests/modules/collections -q`, then the integration test file (needs Docker): `uv run pytest backend/tests/modules/collections/adapters -q -m integration`.

- [ ] **Step 5: Gate.** `uv run poe lint-backend`, `uv run poe typecheck-backend`, `uv run poe coverage` (full), and the architecture tests stay green. Regenerate the client: `uv run poe generate-frontend-client`, then `uv run poe typecheck-frontend`. Add one line to the Collections section of `backend/README.md` naming the `q` parameter.

### Task 2: Ranking, page matching and caps (pure frontend logic)

**Files:**
- Create: `frontend/src/lib/palette-search.ts`
- Create: `frontend/tests/palette-search.test.ts`
- Modify: `frontend/src/lib/search-palette.ts` (`liveMessage` counts across groups)
- Modify: `frontend/tests/search-palette.test.ts`

**Interfaces:**
- Produces:
  - `GROUP_CAPS = { items: 5, collections: 3, itemTypes: 3, pages: 4 }`
  - `matchRank(name: string, query: string): 0 | 1 | 2 | 3` (0 exact, 1 name starts with, 2 a word in the name starts with, 3 anything else); comparison is case-insensitive and trims the query
  - `rankByName<T>(rows: T[], query: string, nameOf: (row: T) => string): T[]` (stable: ties keep input order)
  - `PAGES: { label: string; path: string; keywords: string[] }[]`: Home `/`, Items `/items`, Collections `/collections`, Explore `/explore`, Settings `/settings`, Item types `/settings/item-types`, Relationships `/settings/relationships` (keywords: connections), Saved fields `/settings/saved-fields`, Examples `/settings/examples`, Status `/status`
  - `matchPages(query: string): { label; path }[]` (label or keyword contains the query, ranked by `rankByName` on the label, capped at `GROUP_CAPS.pages`)
  - `matchItemTypes<T extends { label: string; slug: string }>(types: T[], query: string): T[]` (label or slug contains the query, ranked, capped)

- [ ] **Step 1: Write failing tests** for: rank order exact < prefix < word-prefix < other; stable ties; case and surrounding whitespace ignored; empty query yields no page or type matches; "connections" finds Relationships; caps respected; a query with regex characters (`(`, `*`) matches literally (no regex use).
- [ ] **Step 2: Run** `npm --prefix frontend run test -- palette-search` and see them fail.
- [ ] **Step 3: Implement** the module (plain functions, no regex built from user text; use `includes` and `startsWith` on lower-cased strings; word starts by splitting on non-letters/digits).
- [ ] **Step 4:** Extend `liveMessage` (existing helper in `search-palette.ts`) to take the per-group counts and say "6 results" or "No results" while still saying "Searching", the error text or the hint as before. Update its tests: counts sum across groups; one failed group yields "Some results could not be loaded" plus the count of the others.
- [ ] **Step 5: Run** `uv run poe test-frontend`, `uv run poe lint-frontend`, `uv run poe typecheck-frontend`.

### Task 3: `searchEverything` data function

**Files:**
- Create: `frontend/src/lib/palette-sources.ts`
- Create: `frontend/tests/palette-sources.test.ts`

**Interfaces:**
- Consumes: Task 1's `listCollections({ query: { q, limit } })`, the existing `listNodes({ query: { q, limit } })` and `listNodeTypes`, all imported through `$lib/api/client`; Task 2's helpers.
- Produces:

```ts
export type GroupKey = 'items' | 'collections' | 'itemTypes' | 'pages';
export type GroupState<T> =
	| { status: 'ok'; rows: T[] }
	| { status: 'error' };
export type Results = {
	items: GroupState<NodeResponse>;
	collections: GroupState<CollectionResponse>;
	itemTypes: GroupState<NodeTypeResponse>;
	pages: { label: string; path: string }[];
};
export function searchEverything(
	query: string,
	onUpdate: (partial: Partial<Results>) => void,
	isCurrent: () => boolean
): Promise<void>;
```

`searchEverything` normalises the query, starts the items and collections requests together (`limit` equal to each cap, items ranked with `rankByName` on `name`), loads the item type list once (module-level cached promise, reset on failure so the next open retries) and filters it with `matchItemTypes`, computes pages synchronously, and calls `onUpdate` as each source settles. It never calls `onUpdate` when `isCurrent()` is false (the stale-response guard the component supplies). One source rejecting or returning an error sets only its own group to `{ status: 'error' }`.

- [ ] **Step 1: Write failing tests** with the API client module mocked: all sources succeed (groups ranked and capped); collections rejects, the others still arrive and only collections is `error`; item types fetched once for two searches; item types retry after a failure; `isCurrent()` false suppresses every update; blank query makes no requests and returns empty groups.
- [ ] **Step 2:** Run to see them fail, implement, run to pass.
- [ ] **Step 3:** `uv run poe lint-frontend`, `uv run poe typecheck-frontend`, `uv run poe test-frontend`.

### Task 4: Grouped popup (svelte-file-editor)

**Files:**
- Modify: `frontend/src/lib/components/search-palette.svelte`
- Modify: `frontend/src/lib/search-palette.svelte.ts` only if the controller needs a field (it should not)
- Modify: `frontend/README.md` (palette paragraph), `docs/DECISIONS.md` (dated entry: fan-out now, endpoint later; item types filtered locally; collections `q`)

**Interfaces:**
- Consumes: `searchEverything`, `Results`, `GROUP_CAPS` and `liveMessage` from Tasks 2 and 3.

- [ ] **Step 1:** Replace the single `listNodes` call with `searchEverything(query, merge, () => seq === current)`; keep the 250 ms debounce, the stale-response sequence, the 300 ms spinner measured from request start, the highlight reset, and focus return rules (items-only behaviour from the first version, unchanged).
- [ ] **Step 2:** Render with `Command.Group` and a heading per non-empty group, in the order Items, Collections, Item types, Pages. A group in `error` shows one non-selectable line, "Couldn't search collections", with a retry button at least 44 px high that re-runs only that source. Rows: item (name, type label, match context, "Example" badge as now), collection (name, "N items"), item type (label, "Item type"), page (label, "Page"). The last row remains "See all results in Items" and appears when the query is non-blank.
- [ ] **Step 3:** Selecting: item `/items/<id>`, collection `/collections/<id>`, item type `/items?type=<slug>`, page its path; all through `resolve()`; close the popup and apply the existing focus rule.
- [ ] **Step 4:** "Nothing found" only when no source is loading, none errored and all groups are empty. The `aria-live` region uses the extended `liveMessage`. Arrow keys move through one flat list across groups; Enter, Esc unchanged.
- [ ] **Step 5:** Run the Svelte autofixer on the file, then `uv run poe format`, `uv run poe lint-frontend`, `uv run poe typecheck-frontend`, `uv run poe test-frontend`.

### Task 5: End-to-end and final gate

**Files:**
- Modify: `frontend/tests/e2e/search-palette.spec.ts`, `frontend/tests/e2e/layout.mobile.spec.ts`, `frontend/tests/e2e/helpers.ts` (a `makeCollection` helper only if none exists)

- [ ] **Step 1:** Add tests: a text shared by an item, a collection and an item type shows three groups in that order; choosing each lands on the right place (item page, collection page, `/items?type=<slug>` with the type filter set); a "Settings" search lists the Pages group and Enter goes there; a forced failure of the collections request (`page.route`) leaves the Items group usable and shows the collections retry row, and the retry works once the route is cleared; a phone-width run through the bottom-bar Search button with retry and rows at least 44 px high; Esc returns focus.
- [ ] **Step 2:** Run the new and changed specs on chromium and mobile (single-spec route: `uv run poe e2e-db-up`, `e2e-build`, `E2E_WORKERS=1 uv run poe e2e-migrate`, `npx playwright test <spec> --project=…`, `uv run poe e2e-db-down`).
- [ ] **Step 3:** Full gate: `uv run poe lint`, `uv run poe typecheck`, `uv run poe coverage`, `uv run poe test-frontend`, and the full `uv run poe test-e2e`; read totals from the final summary lines only.
- [ ] **Step 4:** Hand the owner a single commit message; the owner commits.
