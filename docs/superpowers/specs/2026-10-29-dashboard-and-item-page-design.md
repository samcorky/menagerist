# Collector dashboard and wide item page

Date: 2026-10-29. Status: approved in conversation (mockups reviewed on the preview link); tweakable later. Builds on the app shell spec.

## Intent

Home should tell a collector what their collection looks like and what needs doing, with numbers they can trust. Today it loads only 12 items (the item list has no newest-first order), so "Recently added" and "Missing details" are computed from the oldest 12 and are wrong in a large library. The item page uses a narrow single column on big screens.

## Goals

- Home: greeting and primary actions; tiles (Items with "added in the last 30 days", Collections with how many are smart, Item types, Favourites, share of items with a photo); **Newly added** (true newest, with covers); **Tidy up** (counts for No photo, No description, Not in any collection, No item type), each opening the Items page with exactly that filter; **Collections** (biggest first); **By item type** (biggest first); **Pick up where you left off** (recently edited).
- Every number comes from a server count or a server-sorted list, never from a partly loaded list; where the server stops counting (1,000) the figure reads "1,000+".
- Every block is a collapsible section that remembers its state. Each block loads and fails independently with a retry.
- Item page: from 1024px a cover column (sticky) and a details column; from 1400px a third side-panel column (connections, collections, tags, dates). Below 1024px today's single column, cover on top.

## Non-goals

- No total-value or other money aggregates (no server aggregate exists; a partial sum would be wrong).
- No backend or API changes.
- The first-run empty state, the examples banner and the item-types nudge keep working as today.

## Anti-goals

- No count that is quietly computed from a partial list.
- No dashboard block that blocks the others from showing while it loads or after it fails.
- Phones keep the bottom bar and 44px rows; nothing is dropped, only reflowed.

## Decisions

1. **Queries.** One module (`src/lib/dashboard.ts`) defines the saved queries as `Query` values (newest: sort created desc; edited: sort updated desc; month: created `>=` `{rel:'-30d'}`; photo: media `has`; tidy-up rows). Their filter links use the Items page's existing `?f=` token, so the dashboard count and the Items page list agree.
2. **Counts.** One request, `POST /api/v1/node/search/counts`, returns exact counts for every dashboard query (items, favourites, last 30 days, with a photo, and the tidy-up rows); it reuses the search parser so each number agrees with the list its link opens. Tidy-up conditions that need a list of ids ("Not in any collection", "No item type") are shown only when the list fits the query language's limit of 50 ids (collections; item types in use); otherwise the row is left out rather than shown wrong.
3. **Loaders.** `src/lib/dashboard-sources.ts` has one loader per block returning `{status:'ok', …} | {status:'error'}`, mirroring `palette-sources.ts`.
4. **Only the item types in use.** Item types are shared across the instance, so the global list would skew the numbers. `GET /api/v1/node/count/types` returns your items per type in one grouped query (types with no items of yours do not appear; untyped is a `type: null` row), so the Item types tile and the By item type block need no per-type requests and have no type cap. "No item type" is asked as "type is none of the types in use". See `docs/DECISIONS.md`, "Counting many searches and items per type".
5. **Item page columns.** CSS grid (`lg:grid-cols-[18rem_minmax(0,1fr)]`, `2xl:grid-cols-[18rem_minmax(0,1fr)_20rem]`); the cover column is `sticky`; sections use `CollapsibleSection`; on a phone the side-panel sections follow the details with Connections open and the rest folded.

## Order of work

1. Pure query/format module and tests. 2. Loaders and tests. 3. Home page and e2e (accuracy with more than 12 items). 4. Item page layout and e2e. 5. Docs, final gates, review.
