# CSV re-import by key, and connecting rows to other items by name

Issues: #556 (re-import by key column), then #555 (connect by name), as a two-layer stack. Parent: #238.

## Intent

A collector keeps a spreadsheet, such as an autograph list, and imports it more than once: after adding rows, in parts, or with a better mapping. Running it again must never create anything twice or undo a decision they made in the app. And a row often names other things, like who signed it and where it was got, which should become connections to real items rather than text.

The sheet behind this design (abridged):

```
ID,Who,On What,Location,Category,In Person,Where,When,Known For,Character/Role
5,Dave Prowse,Photo,Miscellaneous Folder,Star Wars,Yes,Autographica,01/10/2012,Star Wars,Darth Vader
30,Rick Astley,Photo,Celebrities Folder,Miscellaneous,No,eBay,01/12/2018,Singer-Songwriter,
31,Rick Astley,Photo,Celebrities Folder,Miscellaneous,No,Wrote to him,01/02/2019,Singer-Songwriter,
```

`ID` is the key. `Who` and `Where` name a person and an event. Names repeat across rows and carry stray spaces (`eBay `).

## Goals

- Pick a key column; a second run recognises rows already imported and creates only new ones.
- Imports can be paged: several files, or a sheet that only grows, feed the same set of links.
- A column can connect each row's item to another item, found by name, created when missing.
- A re-import adds connections a recognised row is missing.

## Non-goals

- Changing values on items already imported (#234, moved to v0.2026.12.1). The preview only says which recognised rows have changed in the file.
- Reporting or deleting items whose row is missing from a file. With paging, a missing row means nothing.
- Choosing a row range inside the app; large files are #552.
- Filling the other item's fields from the row (`Known For`), or values on the connection (`Character/Role`): #695.
- Several names in one cell.

## Anti-goals

- A re-import that overwrites something the person edited.
- A re-import that brings back an item or connection the person deleted, unless they ask for it.
- A preview that differs from what applying does.

## Decisions

### Re-import (#556)

- **Source identity.** A CSV import's source is its item type and key field, for example `csv:autograph:id`, not the file. Two sheets whose keys mean different things are kept apart by keeping their key column as different details (different keys, so different sources).
- **The key column** must be mapped to a field of the type or kept as a detail (#572). The selector offers only those columns. It is optional; without it, an import works as today.
- **Key values** are trimmed; case counts.
- **First run** with a key column already records links, so the second recognises its rows. Imports made before this ships recorded nothing (the CSV import passes empty `BundleExtras` today); their items are still found by the key field's value as hand-made items, and linked then. No backfill.
- **A recognised row** (a link whose item is live) is planned `unchanged`, "Already imported", and names the item it matched. If the link's field hashes differ from the row's, it is also flagged as changed in the file; nothing is written.
- **A hand-made item** whose key field has the row's key is linked, not changed (existing pipeline behaviour).
- **An item deleted after import** (a link whose item is gone) is not created again. It is planned `unchanged` with "You deleted this after importing it", and created only if the request lists its key in `restore`.
- **An empty key cell** skips the row: `ambiguous`, "No key".
- **Two rows with one key**, or a key matching two items, stay `ambiguous` with their reasons (existing behaviour); the preview now shows them.

### Connect by name (#555)

- **Per connection column:** a relationship type, the item type of the other item, which end the row's item is, and what to do with no match: create it (default) or skip.
- **Lookup** is by name within that item type only, trimmed and case-insensitive.
- **Several matches:** the connection is skipped as `ambiguous` with the reason; the row's item is still imported.
- **No match, create:** a bare item with just the name, created once per file and reused by every row naming it.
- **Empty cell:** no connection.
- **Duplicates:** an identical connection (same type, same two items, same direction) is never made again.
- **On re-import** a recognised row still gets connections it is missing. Each connection the import makes is recorded as a source link (`EntityKind.CONNECTION`), so one the person deleted stays deleted, with the same `restore` choice.
- **A connection's link key** is the row key, the column and the other item's name *as written in the file*, trimmed and case-folded, joined with `\x1f`. File values do not change when the person renames an item, so a rename does not resurrect a deleted connection. The `restore` list takes these keys as well as row keys.
- **Without a key column** connections are still made, but none is recorded, so a second run could repeat them only where `connection_exists` does not catch it (it does for identical connections). Recording needs a row key.

## Approaches

### Re-import

1. **Wire the CSV import into the keyed pipeline (chosen).** `plan_bundle` already handles `BundleSource`, source links, `linked`/`matched` and ambiguous keys, and no source uses it yet, so it can be shaped to these decisions without breaking another importer.
2. Match on the key field's value alone, with no links. Rejected: it cannot tell a deleted item from a new row, and loses the item once its key field is edited.
3. A store just for CSV imports. Rejected: duplicates the source links of #233.

### Connect by name

1. **Connections inside the bundle (chosen).** The import emits bundle connections whose other end is a *name* in an item type rather than a bundle ref; planning resolves it to an existing item or to a bare bundle item, and the preview and apply follow from one plan. This needs pipeline work (below); it is not free.
2. A separate step after import that connects items directly. Rejected: the preview could not show the connections or the items to create, and an import would stop being one plan.

## The shape of the work

### Backend

- `ItemImportRequest` gains `key_field: str | None` and `restore: tuple[str, ...]`; #555 adds `connections: tuple[ConnectionColumn, ...]` (column, relationship type, other item type, row end, on missing).
- `build_item_bundle` sets `Bundle.source` and each item's `source_key` when `key_field` is given, and emits connection bundle entries for #555.
- `PlanItemImport` and `ImportItems` build one `BundleExtras` with the source link repository and owner, shared between planning and applying inside one unit of work, so links are saved with what they record.
- Pipeline: a link to a gone item becomes "deleted after import" unless restored; an empty key is ambiguous; a recognised row reports which fields changed (from `changed_fields`).
- **Named connection ends.** `BundleConnection` gains an alternative end: `(type_ref, name)` instead of a bundle ref. `build_item_bundle` stays pure and synchronous and emits these; the planner resolves them through the graph (a case-insensitive name lookup within the type, which `find_items_by_field` lacks: its `name` match is exact today), creating one bare bundle item per distinct missing name. Resolved ids travel in `BundleExtras` as `linked`/`matched` do.
- **Duplicate connections are found while planning**, with `connection_exists` and within the file, and planned `unchanged`, so the preview matches apply. Neither planner nor applier calls it today.
- **Limits.** `Bundle` gains `connection_limit` beside `item_limit`; the CSV import sets it to `MAX_IMPORT_ROWS × MAX_CONNECTION_COLUMNS`, with `MAX_CONNECTION_COLUMNS = 5`. Created other items count towards `item_limit`.
- **No ledger or undo for CSV imports.** They have none today and this does not add them; source links are the record.
- `PlannedEntity` gains optional `matched` (id and name of the item a row was recognised as) and `changed` (field keys); connection entries may be `AMBIGUOUS`.

### API

- Request fields above, with examples (`poe lint-schema`).
- The plan response says, per recognised row, which item it matched and whether it changed in the file.

### Import page

- "Recognise rows already imported by" selector, listing mapped fields and kept details.
- Per column, a "Connect" option alongside field and keep, with the relationship type, other item type and create-or-skip.
- Preview summary: new, already imported (with the matched item), changed in the file, deleted after import (a tick per row and "bring back all"), skipped with reasons; for #555, items to create and connections to make.

### Tests

- Application tests for every decision above, against the in-memory adapters (100% application coverage).
- e2e: import the autograph sample keyed by `ID`; import again with more rows and `Where` connected; delete one item and one connection, re-import, see both stay deleted, then bring one back.

## Left to the builder

- How connection plan entries are keyed and labelled.
- The exact preview copy beyond the reasons above.
- `restore` travels in both the plan and the apply request, as the mapping does, so they agree.
- Confirming that a kept detail works as the key: `ids_with_attribute_value` reads item attributes, where extra details' values also live.
- Inner whitespace and Unicode normalisation of keys and names (NFC, collapse runs of spaces is a sensible default).
