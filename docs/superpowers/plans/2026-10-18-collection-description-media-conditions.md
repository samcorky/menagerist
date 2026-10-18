# "In collection", description, name and media conditions (phases 2b and 2c) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A search or smart collection can say "in (or not in) these collections", search words in the description or the name on their own, test for an empty or present description, and test whether an item has media (for "a signature with no photo"), with the collection page offering "Save as new, linked to this collection".

**Architecture:** Four new condition kinds in the phase 1 tree (additive, no version bump): `collection`, `description`, `name`, `media`. `description` and `name` are pure graph conditions. `collection` and `media` need data owned by other modules, so graph defines a small port for **external predicates** that `entrypoints/api/shared/bridges/` implements over the collections and media tables (an `EXISTS` subquery for SQL, a lookup for the in-memory evaluator). Graph never imports `collections` or `media`; neither imports graph.

**Tech Stack:** FastAPI, SQLAlchemy/Postgres, SvelteKit 5 runes, shadcn-svelte, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-14-smart-collections-advanced-search-design.md`, phases 2b and 2c. Conventions and rulings from earlier phases: the ledgers under `.superpowers/sdd/2026-10-14-*`, `2026-10-16-*`, and `docs/DECISIONS.md` (search, per-item fields, smart collections).

## Global Constraints

- Dependency direction `entrypoints → adapters → application → domain`; the `graph`, `collections` and `media` modules never import each other (architecture tests); `domain/` imports only the allow-listed stdlib modules; classes in `application/` are handlers or named `*Command/*Query/*Result/*Permission`.
- The Python evaluator is the reference semantics; the SQL compiler must agree on every scenario in `test_node_search.py` (runs on both adapters). Every port ships an in-memory implementation.
- The parser rejects unknown keys (smart collections task); every new condition kind and key set is added to the strict parser, the shared fixture `shared/contracts/query-shapes.json` (only cases both sides agree on) and the frontend decoder.
- The access scope is always applied last: a condition can never reveal another person's items, collections or media.
- Domain and application stay at 100% line and branch coverage. British English; no "node", "edge" or "graph" in user-visible text; Svelte files go through the `svelte:svelte-file-editor` agent; no agent runs `git add` or `git commit`; the user commits after each task.
- Model policy: Sonnet for pattern-following work, Opus for the whole-phase review.

## Review Focus

- **Collection scope:** `collection` naming another person's collection id (or a deleted or unknown one) is stale: it matches nothing, carries a warning, and never reveals membership; the same for smart collections referenced through it.
- **Cycles and depth:** a smart collection that references itself, directly or through other smart collections, is refused at save (400 naming the path); one that becomes cyclic later, or nests too deeply, degrades to "matches nothing" plus a warning, never recursion, a hang or a 500.
- **Negation scope:** `not in collection` and `media: none` match items regardless of other types (they are plain negations like other leaves); document the semantics and test them against both adapters.
- **Media:** only the caller's own media counts; thumbnails, soft-deleted or staged assets do not count as "has media"; `type: image` and `type: document` follow the asset content type; attachments on a field (attribute key) count as the item having media unless the condition says otherwise.
- **Text matching:** `description ~` and `name ~` match words case- and accent-insensitively like free text, treat `%` and `_` literally, and give identical results on both adapters.
- **Cost:** `EXISTS` subqueries stay indexable (attachments by `target_id`, memberships by `item_id`); no `IN (ids)` lists; timing at 100,000 items recorded in DECISIONS.

## Rulings made while planning

- **R25:** external data enters graph queries through an injected port of predicates, not through ids pre-resolved into lists and not through graph importing foreign tables. Cost if wrong: a second place that knows SQL shapes (the bridge); the alternative (`id = ANY(array)` of foreign ids) was rejected because "has no media" would ship a 90,000-element array.
- **R26:** "in collection" resolves manual collections by membership rows and smart collections by inlining their stored definition at query-preparation time (depth limit 3, visited set); references to collections not visible in the caller's scope are stale.
- **R27:** `media` counts attachments whose asset is ready (not staged or deleted) and, with `type`, whose content type starts with `image/` (image) or is not `image/` (document); an item's own attachments only, from any attribute key.
- **R28:** "Save as new, linked" produces `in collection <this>` AND the ad-hoc conditions; deleting the parent later makes the condition stale (it matches nothing, with a warning).

---

### Task 1: Description and name conditions

**Files:**
- Modify: `backend/src/app/modules/graph/domain/query.py` (new dataclasses `DescriptionCondition`, `NameCondition`; parser entries and strict key sets; `walk_conditions` unchanged)
- Modify: `backend/src/app/modules/graph/application/query_resolution.py` (operator and value checks)
- Modify: `adapters/persistence/{query_eval,query_sql,text_match,search_sql}.py`
- Modify: `shared/contracts/query-shapes.json`, `shared/README.md`
- Test: `backend/tests/modules/graph/domain/test_query.py`, `.../application/test_query_resolution.py`, `.../adapters/persistence/test_node_search.py` (scenarios on both adapters), `test_query_eval.py`, `tests/platform/test_text_search_index.py` if the prefilter is reused, shape contract tests

**Interfaces:**
- Produces: wire forms `{"kind": "description", "op": "~" | "empty" | "not_empty", "value"?: str}` and `{"kind": "name", "op": "~" | "=", "value": str}`; `DescriptionCondition(op, value)`, `NameCondition(op, value)`. `~` is word matching with the same folding as `text`; name `=` is a case- and accent-insensitive whole-name match; `empty`/`not_empty` treat NULL and empty or whitespace-only text as empty; values are 1 to 200 characters (`~`) with the usual NUL/surrogate rules.
- Consumes: `text_match` (`fold`, `like_pattern`), the existing description trigram index (`immutable_unaccent(description) ILIKE` served by it).

- [ ] **Step 1: Write failing tests**: parser (valid forms; missing value for `~`/`=`; value on `empty`; unknown op; unknown key; 201 characters; NUL), resolution (op/value shape), scenarios on both adapters (words in the description only, name only, accents and case, `%`/`_` literal, empty vs NULL vs whitespace description, `not` wrapping, a name match not matching the description and vice versa, other owners' items never returned, paging unchanged), EXPLAIN shows the trigram index for `description ~`.
- [ ] **Step 2: Run, expect failure.**
- [ ] **Step 3: Implement** parser, resolution, evaluator (reuse `text_match`), SQL (description: `immutable_unaccent(coalesce(description,'')) ILIKE`-style test guarded as the text leaf is, never NULL; name: sort-key-style folded comparison, indexable by the existing name trigram index where `~`).
- [ ] **Step 4: Shared fixture cases** both sides can agree on only after Task 4 teaches the frontend decoder; until then keep them backend-only and say so.
- [ ] **Step 5: lint-backend, typecheck-backend, test-backend, Postgres tests for search and indexes, architecture + cqrs; domain/application at 100%.**

**Checkpoint:** user may commit.

---

### Task 2: External predicates port and the media condition

**Files:**
- Create: `backend/src/app/modules/graph/ports/external_conditions.py` (`ExternalConditions` Protocol)
- Modify: `adapters/persistence/{node_repository,in_memory_node_repository,query_sql,query_eval,unit_of_work}.py` (accept an optional provider; none means external conditions match nothing and warn)
- Modify: `domain/query.py`, `application/query_resolution.py`, `application/prepare_query.py` (pass the provider through)
- Create: `backend/src/app/entrypoints/api/shared/bridges/media_conditions.py` (SQL `EXISTS` over `media_attachments` joined to `media_assets`, scoped to the owner), an in-memory counterpart for tests
- Modify: composition (where graph repositories are built for search: `build_graph_repos` and the graph dependencies) to supply the provider
- Test: scenarios on both adapters using the in-memory provider and a Postgres bridge test; architecture tests

**Interfaces:**
- Produces: `ExternalConditions` with `media_predicate(mode: "has" | "none", type: "image" | "document" | None, scope: AccessScope) -> ColumnElement[bool]` for SQL (typed as an opaque object in the port so graph does not import SQLAlchemy types it does not already use) and `media_matches(node_id, mode, type, scope) -> bool` for the evaluator; wire form `{"kind": "media", "mode": "has" | "none", "type"?: "image" | "document"}`; `MediaCondition(mode, type)`.
- Rules: R27; the provider checks the owner via the scope (never another person's attachments); with no provider configured the condition matches nothing and returns a warning.

- [ ] **Step 1: Failing tests**: parser (forms, unknown key, bad mode/type), both-adapter scenarios (has/none, image vs document, staged or deleted asset not counted, attachment on a field counts, another owner's attachment never counts, item with no attachments for `none`, `not` wrapping), Postgres bridge test with real rows, EXPLAIN shows an index lookup on `media_attachments.target_id`, architecture tests still pass (graph does not import media).
- [ ] **Step 2: Implement; thread the provider; add the bridge and its in-memory counterpart; record timing at 100,000 items.**
- [ ] **Step 3: lint, mypy, tests, Postgres tests, architecture + cqrs; domain/application at 100%.**

**Checkpoint:** user may commit.

---

### Task 3: The "in collection" condition

**Files:**
- Modify: `domain/query.py` (`CollectionCondition(mode: "any" | "none", ids: tuple[str, ...])`, parser, strict keys), `application/query_resolution.py`, `application/prepare_query.py` (expansion of smart references, cycle and depth checks), `ports/external_conditions.py` (add `collection_predicate`/`collection_matches`)
- Modify: both repositories' leaves; `entrypoints/api/shared/bridges/collection_conditions.py` (membership `EXISTS` over `collection_members`, with the collection visible in scope; smart definitions supplied to graph for inlining through a `CollectionDefinitions` read port)
- Modify: `modules/collections` definition checker path so a smart collection's own save passes its id for self-reference detection; `ValidateQuery` gains the optional `self_id`
- Test: scenarios on both adapters, bridge tests on Postgres, cross-user isolation additions, cycle and depth tests

**Interfaces:**
- Produces: wire form `{"kind": "collection", "mode": "any" | "none", "in": [collection_id, ...]}` (1 to 50 UUID strings); `any` means the item is on any listed collection; `none` means on none; a manual collection is its membership rows; a smart collection is its stored definition inlined (R26: depth limit 3, visited set); a collection that is missing, deleted or outside the caller's scope is stale (matches nothing, warning "That collection no longer exists" with its path), and never reveals whether it exists.
- Cycles: saving a smart collection whose definition (after inlining the others) reaches itself is a 400 naming the path; a cycle that appears later and any depth over the limit make the condition stale with a warning at read time.

- [ ] **Step 1: Failing tests**: parser; manual membership any/none; smart reference inlined (and its own stale parts propagate as warnings); self-reference and two-collection cycles refused at save; a later-created cycle degrades at read; depth 4 refused or degraded; another user's collection id never matches and reveals nothing (same result as a random id) through search, `GET /node?collection=`, counts and ETags; deleted parent turns the condition stale; the generated isolation test covers the new input.
- [ ] **Step 2: Implement; record timing at 100,000 items for a manual collection of 5,000 members and a smart reference.**
- [ ] **Step 3: lint, mypy, tests, Postgres tests, architecture + cqrs; domain/application at 100%.**

**Checkpoint:** user may commit.

---

### Task 4: Frontend model for the new conditions (plain TypeScript)

**Files:** `frontend/src/lib/query/{types,codec,operators,summary,builder,fields,tree,warnings}.ts`, `shared/contracts/query-shapes.json` (valid and invalid cases for all four kinds, now agreed by both sides), `frontend/src/lib/collections.ts` (a fetch of the collections usable as targets), tests

**Interfaces:**
- Produces: TypeScript types for the four conditions; decoder rules mirroring the server (exact key sets, bounds, UUID shape, at most 50 collection ids; never throws); chip wording ("Description contains 'signed'", "Name is 'Alien'", "Description is empty", "Has an image", "Has no media", "In Watchlist" / "Not in Watchlist" with the collection's name from a lookup, falling back to "a collection that no longer exists"); defaults and operator tables for the builder; `combineWithSaved`-style helper `linkedNarrow(parent, adhoc)` returning `in collection <parent>` AND the ad-hoc tree (limit-checked).
- Consumes: Task 1-3 wire forms; `fetchAllCollections` through the generated client.

- [ ] **Step 1: Failing tests** for each bullet, the shared fixture parity (both suites), limits, and the missing-collection wording.
- [ ] **Step 2: lint-frontend, typecheck-frontend, test-frontend.**

**Checkpoint:** user may commit.

---

### Task 5: Builder rows and the linked save (Svelte)

**Files:** (through the `svelte:svelte-file-editor` agent) `query-condition-row.svelte`, `query-value-input.svelte`, `query-builder.svelte`, `query-chips.svelte`, `narrowed-bar.svelte`, `src/routes/collections/[id]/+page.svelte`, `smart-conditions.svelte`

**Interfaces / behaviour:**
- Builder: new subjects "Description", "Name", "Media" and "In collection" in the field picker (a "Content" group), each with the right operators and value input: a text input for description and name, a has/none choice plus an optional type (any, image, document) for media, and a multi-select combobox of the person's collections (smart collections included, the collection being edited excluded) for "In collection" with an any/none toggle.
- Chips and warnings: the Task 4 wording; a stale collection reference shows the server warning on the row and chip.
- Collection page: the narrowing bar gains **Save as new, linked to this collection** (definition = `linkedNarrow`), on smart and manual pages alike, with a one-line explanation of the difference from "Save as new smart collection"; **Update this collection** stays a copy.
- Accessible names stable; design tokens only; British English; manual collection pages keep their search and type behaviour.

- [ ] **Step 1: Failing tests** (SSR and plain-function where the harness allows): rows render the right inputs per subject, the collection picker excludes the edited collection, the bar shows both save actions, linked save builds the right tree.
- [ ] **Step 2: Visual check** on the isolated e2e stack in light and dark, desktop and mobile; view the screenshots.
- [ ] **Step 3: lint-frontend, typecheck-frontend, test-frontend.**

**Checkpoint:** user may commit.

---

### Task 6: End-to-end test, documentation, full gates

**Files:** `frontend/tests/e2e/advanced-search.spec.ts` and `smart-collections.spec.ts` (additions), `docs/DECISIONS.md`, `docs/ARCHITECTURE.md`, `backend/README.md`, `shared/README.md`, the spec (phases 2b and 2c implemented)

- [ ] **Step 1: e2e** on the isolated stack only: a "needs attention" smart collection ("Signature with no photo" = type is Signature AND has no image) and one with "no ISBN" and "no description"; word search in the description alone; "In collection" filter on the items page; save-as-linked from a narrowed manual collection and from a smart one, see the new collection follow a change to its parent; a parent deleted turns the linked collection's condition stale with a warning; a cycle refused with a clear message; another user's collection id gives nothing. Run the new tests three times in a row.
- [ ] **Step 2: DECISIONS entry**: the four conditions, the external-predicates port and why (R25-R28), the cycle and depth rules, media semantics, negation semantics, index findings and timings, known limits.
- [ ] **Step 3: Full gates:** `uv run poe lint && uv run poe typecheck && uv run poe test && uv run poe coverage`; revert formatter changes to unrelated docs.
- [ ] **Step 4: Stop for review**, then a whole-phase review on the strongest model with the Review Focus list as its checklist.

**Checkpoint:** user may commit.

---

## Self-Review

**Spec coverage (2b and 2c).** `collection` condition with manual and smart references, cycles, depth, stale → Task 3; description `~`/`empty`/`not_empty` and name `~`/`=` → Task 1; media has/none with type → Task 2; additive format and strict parser → Tasks 1-4; builder rows → Task 5; "Save as new, linked" → Tasks 4-5; "no ISBN" needs nothing new (existing `empty`); e2e and docs → Task 6.

**Placeholders.** None intended. Tasks 2 and 3 name the port and rules exactly; the SQL shapes and wiring are left to the implementer reading `query_sql.py`, `unit_of_work.py` and the bridges, which are the patterns to follow.

**Type consistency.** The wire forms (`description`, `name`, `media`, `collection`) are defined once in Tasks 1-3 and used unchanged in Tasks 4-5; `ExternalConditions` gains `collection_*` in Task 3 beside the `media_*` methods from Task 2.
