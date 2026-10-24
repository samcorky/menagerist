# Smart collections and advanced search

Status: phase 1, 1b and 2 implemented (`docs/superpowers/plans/2026-10-14-query-engine-advanced-search.md`, `docs/superpowers/plans/2026-10-16-smart-collections.md`); 2b, 2c and 3 implemented (phase 3 on 2026-10-24, see DECISIONS); 4 backend implemented on 2026-10-24 (pack format 6; *Still to try* and the new *No poster yet* are smart; *Running low* became smart on 2026-10-24 via a field `ref`; *Games for two* stays manual, see DECISIONS).

## Goal

Let people ask precise questions of their items ("games for two under 45 minutes", "parts running low", "films rated 4+ I haven't watched in a year"), save a question as a **smart collection** whose members are always current, and build these questions in a visual filter builder. A JQL-style text syntax is a planned later addition (not a copy of JQL); the design must not need migrating to add it.

## Decisions taken in brainstorming

| Topic | Decision |
|---|---|
| Expressiveness | Full: AND / OR / NOT groups and connection conditions, built in phases |
| Engine | A typed condition tree compiled to SQL (no external search engine, no query-string params) |
| UI | Visual builder first; typed syntax later, as a parser/printer over the same tree |
| Sorting | By name, created, updated or any field of a type, stored with the query |
| Field scope | A field condition always names its item type (`Film → Rating ≥ 4`); OR groups may mix types |
| Naming | "Smart collection" in the UI |
| Stale conditions | A condition on an archived or deleted field matches nothing and is reported in `warnings`; it is never silently dropped |

## Query model

The tree is the only stored form. It is versioned JSON.

```json
{
  "v": 1,
  "where": { "op": "and", "children": [ ... ] },
  "sort": [{ "by": "field", "type": "games-game", "key": "play_time", "dir": "asc" }]
}
```

A **group** is `{op: "and" | "or" | "not", children: [...]}`. A child is a group or a condition. `not` has exactly one child.

Conditions (leaf nodes):

| Kind | Shape | Notes |
|---|---|---|
| `text` | `{q}` | Today's `q` behaviour: name, description and searchable attribute values |
| `type` | `{in: [slug]}` | |
| `favourite` | `{value}` | |
| `tag` | `{mode: any \| all \| none, tags: []}` | |
| `date` | `{on: created \| updated, op, value}` | Value may be relative (see below) |
| `field` | `{type, key, sub_key?, op, value}` | Operators come from the field type |
| `connection` | `{mode: exists \| none \| to, relationship?, direction?, item?, where?}` | One hop; `where` is a nested group applied to the item at the far end |

Operators are named in the JQL spirit: `=`, `!=`, `~` (contains), `>`, `>=`, `<`, `<=`, `between`, `in`, `is empty`, `is not empty`, and `has` (multi-choice, checklist). Each field type declares which it supports.

### Values

A condition value is one of:

- **Literal**: typed to the field kind (number, duration in seconds, money amount and currency, ISO partial date, choice value, boolean).
- **Relative date**: `{"rel": "-30d"}`, `-1y` and so on, evaluated at read time so a saved query does not go stale.
- **Field reference**: `{"ref": "reorder_at"}`, another field of the **same kind on the same item type**. This is what lets "Running low" be written as `in_stock <= ref(reorder_at)`.

### Semantics worth fixing now

- **Partial dates** compare at the precision stored: `year = 1984` matches `1984` and any `1984-xx`; `year between 1980 and 1989` is inclusive on the year.
- **Repeating field groups**: `{key, sub_key}` matches when any row satisfies the condition (the repository already supports this for counts and listing).
- **Missing values**: an item without the field fails every operator except `is empty` and `!=`.
- **Stale conditions**: evaluated as false; the response lists them under `warnings` with the condition path so the UI can mark them. Under `not` this inverts to true, which is flagged the same way.
- **Money** compares amounts only when the currencies match; a differing currency does not match (a currency-aware comparison is future work).
- **Limits**: depth ≤ 4, ≤ 50 conditions, nested connection `where` one level deep, value length capped.

## Architecture

Dependency direction is unchanged (`entrypoints → adapters → application → domain`).

- `graph/domain/query.py`: the tree types and structural validation (no framework imports). Validation against the live item types (does this field exist, is the operator allowed, does the `ref` kind match) is an application service in `graph/application/`.
- `graph/ports/node_repository.py`: separate `search` and `search_count` methods take a resolved query and a cursor, beside `list` and `count`. `list` and `count` keep their plain-filter contract, so `GET /node` is unchanged and the keyset paging (by sort values) does not touch the id-ordered list. `attribute_search_exclusions` keeps its current meaning for `text` conditions.
- `graph/adapters/persistence/node_repository.py` compiles the tree to a SQLAlchemy `WHERE` and `ORDER BY`. `in_memory_node_repository.py` evaluates the same tree in Python.
- `collections` stays independent of `graph`. A dynamic collection stores `definition` (opaque JSON). Validation and member resolution go through a new `collections` port, implemented in `entrypoints/api/shared/` over the graph use cases, the same bridge pattern as `ItemLookup` and `CollectionMembers`. `GET /node?collection=<id>` resolves a smart collection by passing its query to `ListNodes` instead of an `ids` list.
- The access scope is always combined with the query last, so a saved query cannot reach another person's items.

### Field-type operator contract

The backend has no field-type descriptors of its own, so its operator table is keyed by field kind (`KIND_OPERATORS` in `field_kinds.py`); the frontend registry declares the matching operators and a filter-input widget. A fixture in `shared/` (operator table per kind) is read by both test suites so the two cannot drift, like the existing `searchable` contract.

## Performance

- Migration: GIN (`jsonb_path_ops`) indexes on `nodes.attributes` and `nodes.tags`; an immutable `unaccent` wrapper plus a `pg_trgm` GIN index for name and description; edges already index `source_id`, `target_id` and `type`.
- Field comparisons are guarded by `jsonb_typeof` before any cast, so a bad value never errors a whole query.
- Connection conditions compile to `EXISTS` / `NOT EXISTS` subqueries.
- **Keyset paging** moves from `id` to `(sort value, id)`, nulls last. The cursor is opaque and encodes both. Sorting on an arbitrary field cannot be indexed generally; measure it with realistic data and add expression indexes per hot field only if needed.
- A smart collection's count is a `count` query. Its ETag uses `updated_at` and that count.
- Dynamic collections no longer pass `IN (ids)`, which removes the 32 767-parameter ceiling noted in DECISIONS.md for manual collections.

## API

- `POST /node/search`: body `{query, limit, cursor}`; response `{items, total, next_cursor, warnings}`. POST because the body is a tree.
- Collections: `kind` may be `dynamic` with a `definition`; create and update validate it. Adding or removing items on a smart collection returns 409. `item_count` is computed.
- Errors follow the existing RFC 9457 mapping: an invalid tree is a 400 naming the path of the first bad condition; a malformed body is 422.

## Frontend

- Items page: a **Filters** control opens the builder (a sheet on mobile). Rows are `field / operator / value`, with **Add condition** and **Add group (all / any)**; active filters show as chips. Operators and value inputs adapt to the field type, reusing the field-type registry.
- The tree is carried in the URL (base64url) so a search can be shared and survives reload.
- **Save as smart collection** from a search; a smart collection's page shows its conditions and an **Edit conditions** action. Existing collection UI (cards, grid and list, search box, Examples filter) is reused.
- UI copy follows the design guidelines: "smart collection", "condition", "match all / any". Node, edge and graph never appear.

## Testing

- Domain and application stay at 100%: tree validation, each operator, relative-date resolution, stale-condition warnings.
- A **contract test** runs one table of cases against both the in-memory and the SQLAlchemy repositories (integration-marked for the latter), so the Python evaluator and the SQL compiler cannot disagree.
- Router tests for `/node/search` and smart-collection CRUD; architecture tests unchanged and must still pass.
- Frontend unit tests for the builder state and operator contract; e2e for build, save, open, edit and the stale-condition warning.

## Phases

1. **Query engine and advanced search.** Domain tree, validation, SQL compiler and in-memory evaluator, migration (indexes), `POST /node/search`, sorting and cursors, builder UI. Includes field references, relative dates and repeating-group rows. No connection conditions yet.
1b. **Per-item field conditions (implemented 2026-10-16).** Items can carry their own typed fields (the `extra_schema` overlay). Phase 1 resolves field conditions against the item type's schema only, so per-item fields are reachable by text search but not by field conditions. Phase 1b adds a field condition addressed by key and kind rather than by type (an additive change to the query format, no version bump), a backend read that lists the per-item fields in use with their kinds and counts, and a "Per-item fields" group in the builder. The condition is scoped to the item's own overlay, so `attributes[key]` is unambiguous even when another type has the same key (see DECISIONS, 2026-10-16). Per-item fields with an explicit kind are now filterable; "Promote to type" is still useful to share a field across items.
2. **Smart collections (implemented 2026-10-17).** `kind=dynamic`, definition validation port, resolution through `GET /node?collection=`, save-as, edit, and the collection page changes. Also built: a capped count with an automatic exact count (`GET /collection/{id}/count`), editable per-owner slugs and slug URLs, and ad-hoc narrowing of a smart collection's page (save as new, update after confirmation). Not built: **Save as new, linked to this collection** (needs 2b). See DECISIONS, 2026-10-17.
2b. **"In collection" condition.** A `collection` condition (`{in: [collection_id], mode: any | none}`) so a search or smart collection can include or exclude the members of other collections. A manual collection resolves to its item ids; a smart collection resolves to its own query, inlined with a depth limit and cycle detection (a smart collection may not reference itself, directly or indirectly). A deleted collection is a stale condition: it matches nothing and carries a warning. It is an additive change to the query format (no version bump). `graph` and `collections` still never import each other: resolution goes through a bridge in `entrypoints/api/shared/`. The collection page also gains **Save as new, linked to this collection** (`in collection <this>` AND the ad-hoc conditions), for smart and manual collections alike. Bulk actions on results stay future.
2c. **Description and media conditions.** Two small conditions for "needs attention" collections, such as a book with no ISBN, a signature with no photo or an item with no description. The first is `{kind: "description", op: "~" | "empty" | "not_empty", value?}` on the item's own description: `~` finds words in the description alone (same case- and accent-insensitive matching as free text, served by the existing trigram index), and a matching `{kind: "name", op: "~" | "=", value}` does the same for the name, so neither has to be a free-text search that also scans the other fields. The second is `{kind: "media", mode: "has" | "none", type?: "image" | "document"}`, resolved through a bridge in `entrypoints/api/shared/` over the media module's attachments (an `EXISTS` check against the attachments table; `graph` and `media` still never import each other). Both are additive changes to the query format (no version bump) and need both adapters, the shared fixtures and builder rows. A missing field value ("no ISBN") needs nothing new: it is the existing `empty` operator on a typed field.
3. **Connection conditions (implemented 2026-10-24).** `exists`, `none`, `to`, and the nested far-end `where`, in the engine, both repositories and the builder. Built as `{kind: "connection", mode: exists | none | to, relationship?, direction?, item?, where?}`; the rulings and measurements are in DECISIONS, 2026-10-24.
4. **Example packs.** Pack format bump so a pack can ship smart collections. Convert *Running low*, *Games for two* and *Still to try* from hand-built lists, and add one or two connection-based ones (*Films to rewatch*).

Each phase gets its own implementation plan; this spec is the shared model.

## Out of scope

**Future (planned or likely, and the design leaves room):**

- The JQL-style text syntax (see below).
- Aggregates (totals, averages), e.g. "total spent on records".
- Counting connections, e.g. "used in 2 or more assemblies".
- Multi-hop connection chains, e.g. "records by artists whose gigs I attended".
- Relevance ranking, and an external search engine behind the same repository port if scanning ever proves too slow.
- Currency-aware money comparison.
- Bulk actions on results. (The "in collection" condition is phase 2b.)

**Rejected for now:**

- GraphQL. It does not provide the filter semantics (operators, relative dates, field references, stale conditions, SQL compilation), its input types cannot express a mixed recursive condition tree without a JSON scalar, and it would add a second API style and a runtime dependency beside the OpenAPI client, RFC 9457 errors and ETag handling. It could be revisited for connection-heavy reads; the query tree and repository port do not depend on the transport.

## Future: the current user as an operand (`currentUser()`)

Idea (requested 2026-10-15): link a user account to an item, typically of a person-like type, so a query can say "Pictures of me" or "Films I have watched" without naming the item. In the planned text syntax this reads like `currentUser()`.

- **Link:** an account may point at one item ("this is me"), stored by id with no foreign key and checked when read, the way collection membership is (`graph` and `identity` never import each other). A small bridge in `entrypoints/api/shared/` resolves actor to item id. A profile screen would offer a "This is me" item picker.
- **Operand:** a new operand form (for example `{"me": true}`, printed as `currentUser()`) resolved at execution time for the acting user, beside the literal, relative-date and field-reference operands. It belongs in the query format as an additive change, so no version bump.
- **Where it applies:** connection conditions (phase 3), such as "connected to currentUser() via *Photographed*", which gives "Pictures of me". It could also drive an "added by me" condition on the item owner, which is a separate and simpler addition for shared households.
- **Smart collections:** a saved query containing `currentUser()` is evaluated per viewer, so the same smart collection shows each person their own results. Anything cached or ETag-tagged for such a collection must vary by user (reads are already scoped by owner).
- **Unlinked accounts and deleted items:** if the account has no link, or the linked item was deleted, the condition matches nothing and returns a warning ("Link your account to an item to use this"), consistent with stale-field behaviour; it never silently matches everything.
- **Open questions:** one linked item per account, or one per item type (the same person as both a *Person* and a *Reader*)? Who may see which account is linked to which item once sharing exists (multi-user stage 2)? Does an administrator link accounts on other people's behalf?
- **Depends on:** phase 3 (connection conditions) for the main use, and the account and sharing model in the multi-user work.

## Future: the text syntax

A parser and printer converting text such as `type = games-game AND play_time <= 45m AND weight IN (light, medium)` to and from the tree. Because operators and structure already mirror that grammar and the tree is the only stored form, it adds no migration, and saved collections would show their text form for free.
