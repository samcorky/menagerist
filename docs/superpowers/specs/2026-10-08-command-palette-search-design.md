# Search popup: grouped results across the app

**Status:** design agreed in conversation on 2026-10-08, awaiting written-spec review.
**Builds on:** `2026-10-08-global-search-popup-design.md` (the items-only popup, built and committed).
**Scope:** backend: a text query on collections. Frontend: the popup searches items, collections, item types and pages.

## Purpose

`/` should find anything in the app from one box: items, collections, item types, and the pages and settings screens. The job is **finding and jumping**. Running actions (add an item, install examples, change theme) is out of scope here and stays a later addition to the same list.

## Behaviour

- **Groups, in a fixed order:** Items, Collections, Item types, Pages. A group with no matches is not shown.
- **Ranking:** best match first *within* each group. The order is: exact name, name starts with the text, a word in the name starts with the text, then anything else the source matched (description, attribute values). Ties keep the source's own order. There is no mixed ranking across groups.
- **Caps per group:** Items 5, Collections 3, Item types 3, Pages 4. A group shows only its best few; the last row stays "See all results in Items" (`/items?q=...`).
- **Sources:**
  - Items and collections come from their list endpoints with `q` and a small `limit`, requested in parallel after the existing debounce. Collections need the new backend `q` (below).
  - Item types have no `q` and are few, so the popup loads the list once when it first opens (cached for the session of the page) and filters it locally by label and slug, with the same ranking.
  - Pages are matched locally, with no request, against a static list of destinations (Home, Items, Collections, Explore, Settings, Item types, Relationships, Saved fields, Examples, Status), each with a label and a few keywords (for example "Relationships" also matches "connections").
- **Selecting a result:** opens it. An item opens its page, a collection its page, an item type shows that type's items (`/items?type=<slug>`, which the items page already reads), a page its route. Enter, arrow keys, Esc and focus return behave as in the items-only popup.
- **Independent failure:** each source reports its own loading and error state. A failing group shows a short "Couldn't search collections. Try again" row; the other groups still show. The popup shows "Nothing found" only when every source answered and all were empty.
- **Loading:** the 300 ms spinner rule applies to the popup as a whole. Results from a faster source appear as they arrive and do not jump around once shown (groups keep their fixed order).
- **Empty query:** unchanged (the hint).
- **Words in the UI:** "collection", "item type", "page"; never node, edge, graph or shelf.

## Backend

- `GET /collection` takes `q`, a case-insensitive "contains" match on name and description, with the same wildcard escaping and trimming as the items and item types endpoints. It composes with the existing `limit` (1..100) and paging.
- The collections listing is not conditional (only a single collection is), so there is no validator to adjust.
- `q` is a new field on `ListCollectionsQuery` and on the `CollectionRepository.list` port, implemented in both the SQLAlchemy and in-memory repositories. Combining `q` with the existing `item_id` filter keeps its "page is never short" loop.
- No other backend change, no new endpoint.

## Frontend structure

- `lib/palette-search.ts` (pure): ranks a list by the order above, matches the static page list, and owns the caps. Unit tested.
- `lib/palette-sources.ts`: one function, `searchEverything(query)`, which fans out and returns the groups with their per-source state. The popup only ever calls this, so a single backend search endpoint can replace the fan-out later without UI changes.
- `search-palette.svelte`: renders groups with `Command.Group` and a heading per group; keeps its current states, live region and focus handling, extending the screen-reader message to count results across groups.
- The first version keeps the popup's keyboard model: one flat list of rows, arrow keys move across groups.

## Decisions

- Fan-out on the client now; a backend search endpoint (true cross-group ranking, one request) is deferred until there is a need for "best match overall" or the number of searchable things grows.
- Collections are the only new backend work.
- Actions, recents and a mode prefix (`>`) are deferred; the row model leaves room for a row that runs a function instead of navigating.

## Testing

- Unit: ranking order and ties; page matching (labels and keywords, case, empty text); the live-region message across groups; the caps.
- Backend: collections `q` (name, description, case, wildcard characters, trimming, paging, combined with `item_id`), with the usual in-memory and Postgres coverage.
- E2E: a text that matches an item, a collection and an item type shows three groups in order; choosing each opens the right page (an item type lands on the items list filtered to that type); a failing source (forced request failure) leaves the other groups usable; a phone-width run through the bottom-bar Search button; Esc returns focus.
