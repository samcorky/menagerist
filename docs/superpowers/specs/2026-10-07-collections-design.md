# Collections (manual shelves)

**Status:** implemented (2026-10-07). Changes from this spec are listed at the end. Implementation plan: `docs/superpowers/plans/2026-10-07-collections.md`.
**Scope:** backend (new `collections` module, one migration, a membership filter on the item list), frontend (Collections page, shelf page, "Add to collection" on the item page), docs. Tracks #265 (domain model) and #191 (manual collections).
**Out of scope:** dynamic collections (#190), ordering within a shelf, bulk select on the items list, sharing and permission enforcement, a `collections` section in example packs (a follow-up once this lands).

## What a collection is

A **named shelf**: "My vinyl", "Funkos", "To watch". It is a first-class entity, not an item. It refers to items by id and never owns them. An item can be on any number of shelves. Deleting a shelf never deletes or changes items. Users see the word *collection*; the words node, edge and graph never appear.

## Decisions taken in conversation

| Question | Decision |
|---|---|
| What is it to a person? | A named shelf, not a folder items live in. |
| First build | Manual shelves only. The model leaves room for a dynamic kind, which ships later (#190) once search can filter on more than type, text and favourite. |
| Ordering | A shelf is a set. It shows items the way the items page does. Membership records `added_at`. Hand ordering can be added later without breaking anything. |
| Adding items | From the item page ("Add to collection") and from the shelf page ("Add items" search-and-tick picker). No bulk select on the items list yet. |
| Where it lives | A new `collections` module (see below), not inside `graph`. |
| Slug | Each collection has a slug for future pretty links: immutable, derived from the name, globally unique among live collections. |
| Ownership | `owner_id` and `visibility` are stored and routed through `AuthorizationPort` but not enforced, like today's permissions. Multi-user comes later. |

## Domain

```
Collection(Identifiable, SoftDeletable):
    name: str                 # 1 to 120 characters after trimming
    slug: Slug                # shared_kernel Slug; immutable
    description: str | None
    kind: CollectionKind      # MANUAL only; DYNAMIC reserved
    owner_id: uuid.UUID
    visibility: Visibility    # PRIVATE only for now

Membership (frozen value, no id, no soft delete):
    collection_id, item_id, added_at
```

- Names need not be unique; two shelves may both be called "Favourites". Slugs are unique.
- The slug is derived from the name with `slugify` when none is given, with `-2`, `-3` appended when taken. It never changes on rename, so a link never breaks.
- Rules live in the domain and use cases. Database indexes are backstops only.

## Persistence

- `collections`: the entity above, plus a partial unique index on `slug WHERE deleted_at IS NULL` (so a deleted shelf's slug can be reused, as for type slugs).
- `collection_members`: `(collection_id, item_id)` primary key, `added_at`. Backstop for the use case's "not already on this shelf" check.
- One migration. Soft delete of a collection keeps its membership rows; they are ignored while it is deleted.

## Module boundaries

`collections` never imports `graph`. As with `examples`:

- It owns a port for what it needs from the item side: `ItemLookup` (do these ids exist as live items? return their names for display). An adapter in `entrypoints/api/shared/` calls the real graph use cases.
- `graph` owns a port for what it needs from the collection side: `CollectionMembers` (the item ids on a collection). An adapter in `entrypoints/api/shared/` implements it from the `collections` repository. This follows the existing `ChoiceListSource` pattern.
- An architecture test asserts `collections` is independent of `graph` and `presets`, mirroring the rule for `examples`.

## API

All under `/api/v1/collection`; each use case takes `actor`.

| Endpoint | Purpose |
|---|---|
| `POST /collection` | Create (name, optional description, optional slug). 201 with the collection. |
| `GET /collection` | List live collections with item counts. `?item_id=<id>` lists only the shelves holding that item. |
| `GET /collection/{id}` | One collection. |
| `PATCH /collection/{id}` | Rename or change the description (ETag/If-Match like other entities). The slug cannot change. |
| `DELETE /collection/{id}` | Soft delete. Items are untouched. |
| `PUT /collection/{id}/item` | Add one or many items (body: item ids). Idempotent for items already on the shelf. Unknown or deleted items are a validation error naming them. |
| `DELETE /collection/{id}/item/{item_id}` | Remove an item from the shelf. |

Item list: `GET /api/v1/node?collection=<id>` restricts the list to that shelf's items and combines with the existing `type`, `q` and `favourite` filters and keyset paging. An unknown collection id is a 404.

## Frontend

- **Collections page** (`/collections`): cards for each shelf with name, description and count; create from a small dialog; empty state invites making the first shelf.
- **Shelf page** (`/collections/[id]`): the items list scoped to the shelf, reusing the items page's list and grid views, search and filters, plus an **Add items** picker (search, tick, confirm), per-item **Remove from collection**, rename and delete (confirmation says items are kept).
- **Item page**: an **Add to collection** action and the shelves the item is on, as links.
- **Navigation**: a Collections entry beside Items.
- Standard patterns: `resolve()` hrefs, `delayedLoading`, toasts, `ResponsiveDialog`, no graph terminology, focus returned after dialogs.

## Errors

Domain errors subclass the shared-kernel bases, so the global handlers give the right status: invalid name or slug (400), unknown collection (404), unknown or deleted item (400 naming the ids), slug conflict on an explicit slug (409). Requests that fail Pydantic validation (name over 120 characters, more than 500 ids, malformed id, unknown fields) are 422.

## Testing

- **Domain:** name validation, slug derivation, rename leaves the slug alone, soft delete.
- **Application (in-memory adapters):** create with and without slug, slug suffixing, add idempotent, add rejects unknown items, remove, delete keeps items, membership lookup, counts exclude deleted items.
- **Persistence (integration):** partial unique slug index, membership primary key, soft-deleted slug reuse.
- **Router:** each endpoint and error mapping; `?collection=` combined with `q`, `type`, `favourite` and paging.
- **Architecture:** the independence rule above.
- **Frontend:** vitest for any helpers; e2e for create a shelf, add from the item page, add from the shelf picker, filter inside a shelf, remove an item, delete a shelf (items remain), and slug reuse after deletion.

## Risks

- **Large shelves.** The `?collection=` filter passes member ids to the item query. A few thousand ids is fine; if shelves grow far beyond that, switch the adapter to a join. The port hides this.
- **Dangling members.** A deleted item stays in `collection_members`. Reads and counts check liveness, so it is ignored, not an error.
- **Slug uniqueness across owners.** Global for now; making it per owner when multi-user arrives is an index and use-case change in one place.

## Follow-ups (not part of this spec)

Dynamic collections (#190); a `collections` section in example packs and the Koillection-style pack; ordering within a shelf; bulk add from the items list; sharing and permission enforcement; sorting shelves.

## What changed during implementation

- Domain validation errors are 400, not 422 (the application's existing mapping); Pydantic failures stay 422.
- `GET /collection?item_id=<id>` replaced `GET /collection/membership`; the list has no `Total-Count` header.
- Adding or removing items bumps the collection's `updated_at`, and the ETag also includes the live item count (and the HTTP validator rules were fixed in the shared conditional-request helper).
- `PATCH` can clear the description with a blank string.
- Add accepts at most 500 ids per request.
- The collection page does not share its list code with the items page, and it has search, the list and grid views and the Examples filter but no type filter yet.
- Ownership enforcement (including the read path behind `?collection=`) is a recorded precondition for multi-user.
