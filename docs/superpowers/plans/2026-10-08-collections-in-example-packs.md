# Collections in example packs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let example packs ship collections (named lists of the pack's own items), installed and cleanly removed like every other pack entity, so the examples can show the collection feature and a Koillection-style collector pack becomes possible.

**Architecture:** The pack format gains an optional `collections` section (format version 2; version 1 packs still parse). `examples` gets a third target port it owns, `CollectionTarget`, implemented in `entrypoints/api/shared/example_targets.py` by calling the real collections use cases. Install adds a step after connections; removal runs collections before items. The keep rules extend naturally: an edited collection is kept, and an example item that sits in any collection that survives (the user's own, or an edited example one) counts as user data and is kept.

**Tech Stack:** Python 3.14, FastAPI, pytest, testcontainers; SvelteKit/Svelte 5, Vitest, Playwright.

**Specs:** `docs/superpowers/specs/2026-10-06-example-packs-design.md`, `docs/superpowers/specs/2026-10-07-collections-design.md`. Prior plans: `2026-10-06-example-packs.md` (Phases 0-5, follow-ups), `2026-10-07-collections.md`.

## Global Constraints

- `examples` must not import `collections` or `graph` (architecture tests); the new port is owned by `examples`, the adapter lives in `entrypoints/api/shared/example_targets.py`.
- Soft delete everywhere; the application owns every constraint; DB indexes are backstops.
- Pack files are package data in `backend/src/app/modules/examples/packs/`; format `menagerist-example-pack`; refs are lowercase ASCII `^[a-z0-9][a-z0-9-]*$`; parsing is strict (unknown or missing keys are errors).
- British English, fictional content only (no real people, companies or shops), small and finished with a few deliberate blanks, UK flavour.
- Coverage floors: domain 100%, application 100%, shared_kernel 100%, adapters 80%, platform 70%. `mypy --strict` including tests; ruff; mccabe at most 8; unique test file basenames; no `__init__.py` under `backend/tests`.
- All `.svelte` work goes through the `svelte-file-editor` subagent. User-visible words: "collection"; never node, edge, graph, shelf.
- Never commit, stage or push; the user commits.
- Run `poe coverage` (full backend gate), `poe lint`, `poe typecheck`, `poe test-frontend` at the end; the e2e suite is `poe test-e2e` (parallel, builds the frontend first).

## Rulings made while planning

- **Format version:** `version: 2` allows the `collections` section; `version: 1` still parses and has none. A v1 pack file need not change unless it gains collections. The index stays version 1.
- **Collection slug and clashes:** a pack collection has no `slug`; the collections module derives it from the name (with `-2`, `-3` suffixes), so it can never clash with the user's own collections. Names need not be unique.
- **Pack collection fields:** `ref`, `name`, optional `description`, `items` (list of item refs, at least one, no duplicates, every ref must exist in the pack).
- **Content hash of a collection:** name, description and the sorted member item ids as stored. So renaming it, changing the description, or adding/removing any item makes it "edited" and it is kept on removal.
- **Removal order:** connection, collection, item, item type, relationship type, preset. Collections go before items so members stop counting as in use.
- **Item user-data rule:** an example item that is a member of any live collection when its turn comes is kept with the reason "has your connections or files" (the existing user-data reason, now also covering collections; the user-facing wording is unchanged). Pack collections that were removed no longer count.
- **Collection removal** is the collections module's soft delete; memberships stay (collections already ignore them).
- **Counts:** `PackCounts` and the API's `PackCountsResponse` gain `collections`; the UI adds "N collections" to its summaries.
- **Example marker:** the "Example" badge also marks example collections (collections list and collection page header); `GET /example/entities` gains `collection_ids`.

## Review Focus

- Removing a pack when the user added their own item to an example collection: the collection is kept (edited) and so are all its example members. Pin in Task 2 and Task 3.
- Removing a pack when the user put an example item on THEIR OWN collection: the item is kept, the example collection (unedited) is removed. Pin in Task 3 (Postgres) and the e2e.
- Reinstall after removal creates the collections again, with fresh slugs even if a kept collection holds the old slug. Pin in Task 3.
- A failed install part-way (for example a collection step fails) rolls back everything created, including collections. Pin in Task 2.
- A pack with a collection naming an unknown item ref, duplicate refs, or an empty `items` list is rejected at parse time. Pin in Task 1.
- Loading a v1 pack, a v2 pack without `collections`, and a v2 pack with them all work. Pin in Task 1.

---

## Phase 1: Backend

### Task 1: Pack format and domain

**Files:** `backend/src/app/modules/examples/domain/{pack,installation,removal}.py`; `.../adapters/platform/pack_parser.py`; tests under `backend/tests/modules/examples/`.

**Interfaces:**
- Produces `PackCollection(ref, name, description, item_refs: tuple[str, ...])`; `ExamplePack.collections: tuple[PackCollection, ...]` (default empty); `PackCounts.collections: int`; `EntityKind.COLLECTION`; `REMOVAL_ORDER` with `COLLECTION` between `CONNECTION` and `ITEM`; parser accepts `version` 1 or 2 and the optional `collections` section only on v2.

- [ ] **Tests first:** parse a v2 pack with collections; v1 pack unchanged; `collections` on a v1 file is an error; unknown key in a collection is an error; missing `items`, empty `items`, duplicate item ref in one collection, unknown item ref, duplicate collection ref, blank name are all `InvalidPackError`; `counts` includes collections; the installed-entity hashing/`EntityKind` value `collection` round-trips through the persistence mapping (JSONB `entities`).
- [ ] Update the contract tests in `backend/tests/modules/examples/application/test_shipped_packs.py` so existing assertions about counts and "every item type has items" still hold, and add: every collection's item refs resolve, collection names are unique within a pack, British spelling check covers collection text.
- [ ] Frontend's `frontend/tests/example-packs.test.ts` reads the same packs: make sure it tolerates the new section (and, if it counts entities, includes collections).

### Task 2: Ports, install step and removal

**Files:** `.../ports/pack_targets.py` (new `CollectionTarget`), `.../adapters/platform/` (in-memory fake if the module ships one for targets; otherwise the test `conftest.py` fake), `.../application/{install_example_pack,uninstall_example_pack,removal}.py`; tests.

**Interfaces:**

```python
class CollectionTarget(Protocol):
    async def create_collection(self, spec: PackCollection, *, item_ids: Sequence[uuid.UUID]) -> Created: ...
    async def inspect(self, collection_id: uuid.UUID) -> Inspection | None: ...   # content: name, description, sorted member ids
    async def remove(self, collection_id: uuid.UUID) -> RemoveResult: ...
```

- [ ] `InstallExamplePack` and `UninstallExamplePack` take the third target; install adds a "collections" step after connections (resolve each `item_ref` through the run's `item_ids`, create, record with content hash, persist immediately); `settle_installation` removes in `REMOVAL_ORDER` and uses the existing `decide_removal` truth table (edited > user data > in use). `GraphTarget.inspect` for items is already how item user data is reported; the adapter (Task 3) extends it.
- [ ] **Tests first (in-memory World in `tests/modules/examples/conftest.py`):** install creates collections with the right members and counts; a failing collection step rolls back everything (assert `created` and removal calls); uninstall removes unedited collections before items; an edited collection (renamed, description changed, member added or removed) is kept with reason `edited`, and its example items are kept because they are members of a surviving collection (fake the item inspection accordingly); reinstall after removal works; install result and uninstall result counts include collections.
- [ ] Update the API schemas and dependency wiring for `InstallExamplePack`/`UninstallExamplePack` (the router passes the new target) and `PackCountsResponse` (`collections`).

### Task 3: Bridge to the collections module

**Files:** `backend/src/app/entrypoints/api/shared/example_targets.py`; `backend/src/app/modules/examples/application/list_example_entities.py` + its schema/router; integration tests under `backend/tests/entrypoints/api/shared/`.

- [ ] Implement `CollectionTarget` over the real collections use cases (`CreateCollection` with name/description and derived slug, `AddItemsToCollection`, `GetCollection`/membership read for inspect content, `DeleteCollection`). Content for hashing: name, description, sorted member ids as UUID strings. `remove` of a missing collection is `ALREADY_GONE`.
- [ ] Extend the graph target's item inspection so `has_user_data` is also true when the item is a member of any live collection (use the collections side's "collections holding this item" query; no import of `collections` inside `examples` or `graph`).
- [ ] `GET /example/entities` also returns `collection_ids` (owned, still-live example collections).
- [ ] **Tests (Postgres, `@pytest.mark.integration`):** end to end through the real use cases: install a pack that has collections; the collection exists with the right members; uninstall removes it and items; user edits the collection then uninstall keeps it and its items; user adds an example item to their own collection then uninstall keeps that item and removes the example collection; reinstall; the `entities` endpoint lists collection ids.
- [ ] Run the architecture tests; `poe coverage`.

## Phase 2: Frontend

### Task 4: UI

**Files:** `frontend/src/lib/examples.ts` (+ tests), the Collections list and collection page (Svelte), generated client regeneration, `frontend/tests/e2e/examples.spec.ts`.

- [ ] `describeCounts` includes collections (singular/plural; fixed order after items); `describeRemoval` unchanged. Tests first.
- [ ] "Example" badge on example collections: collections list cards and the collection page header, using the same id set helper (`loadExampleIds` gains `collections`). Svelte work via `svelte-file-editor`.
- [ ] e2e: install a pack that ships collections (the Task 5 packs): the Collections page lists them with the badge; opening one shows its items; removing the pack removes them; editing one (rename) then removing keeps it and its items.
- [ ] `poe lint-frontend`, `poe typecheck-frontend`, `poe test-frontend`, `npm run build` via `poe test-e2e`.

## Phase 3: Content (after the owner approves the tables)

### Task 5: Author the collections and the board games pack

**Files:** `backend/src/app/modules/examples/packs/{music,recipes,movies,parts}.json` (add `collections`, set `version` to 2), new `games.json`, `index.json`.

Owner decisions (2026-10-08): the new pack is **Board games** (pack id `games`, slug prefix `games-`), not toy figures; the movies collection is called **To rewatch** (not Favourites: items already have a favourite flag). The tables below are the agreed content; the author may adjust small wording but not the structure, and must keep every item/connection count as stated.

**Collections added to existing packs (each uses only items already in the pack):**

| Pack | Collection | Description | Members |
|---|---|---|---|
| music | Records | The records on the shelf. | Night Drive, Paper Lanterns, Salt Marsh Sessions, Thirteen Bells |
| music | The Lamplighter nights | Gigs at the Lamplighter and the venue itself. | The Lamplighter, The Velvet Static at the Lamplighter, Marguerite Odell at the Lamplighter |
| movies | To rewatch | Films worth another look. | Cold Harbour, The Night Bus Sessions |
| movies | Poster wall | Framed and unframed. | Cold Harbour poster, Quiet Hours poster |
| recipes | Bakes | Pies, scones and parkin. | Cheese and onion pie, Leek and cheddar scones, Parkin |
| recipes | Cupboard staples | The ingredients that are always in. | Plain flour, Mature cheddar, Black treacle |
| parts | Running low | Parts to reorder soon. | LM317 voltage regulator, 10-turn trimmer potentiometer, 470 µF electrolytic capacitor |
| parts | Pico reaction game build | The assembly and what it uses. | Pico reaction game, Raspberry Pi Pico 2 W, Red LED 5 mm, Green LED 5 mm, Tactile push button 6 mm, Half-size breadboard |

(Use the packs' exact item names; check them against each pack file. Collections do not need descriptions to be long: one short sentence.)

**New pack `games` (Board games), 20 items, ~30 connections, 4 collections, fictional UK flavour:**

- Item types: `games-game` (Game: min and max players as numbers, play time as a duration shown in words, year as a partial date, mechanics as a multi-choice from Co-operative, Dice, Worker placement, Set collection, Bluffing, Deck building, weight as a choice Light / Medium / Heavy, rating, condition as a choice New / Good / Worn, price paid as money in GBP, a "complete?" checklist of box / rulebook / tokens / cards or dice, notes), `games-publisher` (website, notes), `games-person` (role: designer or friend), `games-night` (date as a partial date, notes).
- Relationship types: *published by* (game to publisher), *designed by* (game to person), *expansion of* (game to game), *played at* (game to night, carrying `winner` as text), *came to* (person to night).
- Games (10): Lantern Harbour (co-op, 1-4 players, 45 min, 2021, Medium, rated 5, 34.99, complete), Tea Clipper Race (dice and set collection, 2-5, 60 min, 2019, Medium, rated 4), Ministry of Mild Mischief (bluffing, 3-8, 30 min, 2022, Light, rated 4), Cobbled Streets (worker placement, 2-4, 90 min, 2018, Heavy, rated 5, rulebook missing from the checklist as a deliberate gap), Cobbled Streets: The Canal Expansion (expansion; not played yet, no rating), Pocket Orchard (set collection, 2 players, 20 min, 2020, Light, rated 4), Thornfield Heist (co-op, 2-5, 75 min, 2023, Medium, not rated yet), Slow Parcel Panic (dice, 2-6, 15 min, 2017, Light, no rating, not played), and two wishlist games not owned: Gilded Moth and Saltmarsh Express (no condition, no price, a note saying why wanted).
- Publishers (3): Brindle & Finch Games, Marrow Lane Press, Dovetail Tabletop (invented websites on the `.example` domain). People (5): designers Elspeth Marlow, Tomasz Reeve, Ottoline Pryce; friends Kit Alderman and Nell Brightwater. Game nights (2): Autumn game night (October 2025) and Boxing Day marathon (December 2025). Total items: 10 + 3 + 5 + 2 = 20.
- Connections: published by (10, one per game); designed by (7, some games share a designer; the wishlist games have none); expansion of (1); played at (6, with a `winner`: Lantern Harbour is co-op so its winner is 'Everyone'); came to (5: the friends to the nights). Total about 29.
- Collections (4): **Wishlist** (Gilded Moth, Saltmarsh Express), **Games for two** (Pocket Orchard, Lantern Harbour), **Family game night** (Slow Parcel Panic, Tea Clipper Race, Ministry of Mild Mischief, Lantern Harbour), **Still to try** (Slow Parcel Panic, Cobbled Streets: The Canal Expansion, Thornfield Heist). Lantern Harbour and Slow Parcel Panic each sit in two collections on purpose.
- Add the pack to `index.json` with a description. Author with a readable table first (as for the other packs), generate with the same discipline (schemas mirror what the editor produces; verify against the frontend field-type registry via `frontend/tests/example-packs.test.ts`), keep refs ASCII.

- [ ] Add the eight collections above and set those four packs to `version` 2; author the `games` pack; contract tests (backend `test_shipped_packs.py`, frontend `example-packs.test.ts`) pass for every pack; an independent reviewer reads the new pack.

## Phase 4: Documentation

- [ ] `docs/DECISIONS.md` entry (collections in packs, removal rules above), `backend/README.md` "Writing an example pack" (the `collections` section, version 2, the ref rules), `docs/superpowers/specs/2026-10-06-example-packs-design.md` status note, tick off the follow-up in `2026-10-06-example-packs.md`.

## Verification before finishing

- [ ] `poe lint`, `poe typecheck`, `poe coverage`, `poe test-frontend`, `poe test-e2e` (read the totals).
- [ ] Walk through in a browser at desktop and phone width: install each pack, open its collections, edit one, remove the pack.
