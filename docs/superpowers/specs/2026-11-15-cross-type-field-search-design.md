# Cross-type field search, wishlist status and acquisitions (#241, #349)

## Intent

Collectors want to track things they don't own yet (#241) and record how and when they got each item (#349). The owner's constraint is that neither becomes special machinery: both should be ordinary content (saved fields, example-pack content, smart collections) on top of general engine features.

The one engine gap is that a search condition can't reach "the same field on every item type". Saved fields are copied into each type with that type's own key, and a field condition names one type plus one key. So "everything I want", "bought in 2022" and #346's "what is missing" can't be written once. This design closes that gap in a general way and then delivers #241 and #349 as content.

## Goals

- A field condition that matches **any item, of any type, with a field of key K and kind T** whose value satisfies the operator (the "loose" form).
- A field condition that matches **any item with a field copied from saved field P** (the "strict" form, by provenance).
- New item types are covered automatically, with no edit to stored searches.
- #241 as content: a "Status" saved field (Owned, Wanted) and a "Wanted" smart collection that uses the loose form.
- #349 as content: an "Acquisition" repeating table saved field, filterable across types ("bought in 2022", "price over 100").

## Non-goals

- Sorting by a cross-type field. Sort keys stay per type.
- Comparing a cross-type field with another field (`ref`).
- A "Wanted" row on Home. Home's rows are hard-coded searches, so adding one would be wishlist-specific code. The general follow-up is "show any collection on Home" (new issue).
- Totals such as "spent this year" (#134, aggregates).
- #346 set completion. It reuses this work but is designed separately.

## Anti-goals

- Any code that knows the words "wanted", "owned" or "acquisition".
- A new stored column or table for status.
- Matching on a field's visible name. A rename would silently drop a type out of a stored search.

## Approaches considered

1. **Content only:** one condition per type, ORed. No code, but it silently misses types added later. Rejected.
2. **A "wanted" tag:** works across types today, but it isn't a proper status. It doesn't show on cards as a field value, and "owned" just means the tag is missing. Rejected.
3. **General cross-type field conditions, by key + kind and by provenance.** **Chosen** by the owner. The loose form matches on key + kind rather than visible name (my call: survives renames, matches how search already addresses fields, and saved-field copies normally get the same key because keys are slugged from the title).

## Design

### Query language (`graph/domain/query.py`, `shared/contracts/query-shapes.json`)

Today a field condition names exactly one of `type` (a type's field) or `field_kind` (a field in an item's own `extra_schema` overlay, DECISIONS 2026-10-16).

- **Widen `field_kind` without `type`** to mean "key K of kind T on *any* item: a type field or the item's own field". This replaces the overlay-only meaning (alpha, no compatibility needed). It is additive in shape, so there is no `v` bump.
- **Allow `sub_key` with `field_kind`.** The kind is then the column's kind. It matches type table fields only, because overlays have no table columns (R16 stands for overlays).
- **Add `origin`** (a saved field id) as a third way to address a field: `{"kind": "field", "origin": "<preset id>", "op": ..., "value": ...}`, optionally with `sub_key`. Exactly one of `type`, `field_kind` or `origin` is set. `key` is required with `type` and `field_kind` and refused with `origin`.
- `ref` values stay refused with `field_kind` and `origin`.

### Resolution: expand into conditions the engine already runs

In `prepare_query`, after parsing and before `resolve_fields`, a new pure application-layer pass (sibling of `expand_collections`) rewrites each cross-type condition into an `or` group over the schemas already loaded there:

- **`field_kind`:** one typed leaf `{type: slug, key: K, sub_key?, op, value}` for every live type whose schema has non-archived property K (or column K.sub_key) with explicit kind T. Without `sub_key`, also one per-item overlay leaf (the existing overlay predicate, kept as an internal form).
- **`origin`:** one typed leaf for every non-archived property (or column) in any type whose `x-menagerist.origin.preset` equals the id. Several properties in one type (a field group, or applied twice) each get a leaf. Type fields only: a copy in an item's own overlay has a key that varies per item, so it can't be a single SQL test. Those copies are still found by the `field_kind` form, because their key is slugged from the same title.
- **No match:** the condition becomes a group that matches nothing, with no warning, as for R15. It isn't stale, because a type added later may match.
- **Kind check:** operators and values are validated once against T (`field_kind`) or the kind of each matched property (`origin`). An `origin` whose copies disagree on kind (a kind change on one type) keeps only leaves whose kind accepts the operator and value.

The expanded leaves then go through the existing `resolve_fields`, SQL compilation (`query_sql.py`) and in-memory evaluation (`query_eval.py`) unchanged. The scoped `!=`/`not_in` semantics carry over per leaf, so "Status != Wanted" never returns items with no Status field. Expansion runs on every query, so a stored smart collection picks up new types without being re-saved. Smart collections nested through `expand_collections` must be expanded too (order the passes so expanded collection bodies are also rewritten).

The overlay leaf needs an internal representation once `field_kind` on the public shape means "any". The builder may choose a private flag or a distinct internal condition type. It must not be expressible in the parsed JSON.

### Frontend search builder (`lib/query/fields.ts`, `components/query-*.svelte`)

- The "Per-item fields" group becomes **"Any item type"**. It lists every key + kind found across type schemas (client-side, from the loaded types) merged with `GET /node/item-fields`, one row per key + kind, labelled with the most common title and a count of the types and items that have it. The chip label changes to match.
- A **"Saved fields"** group lists the owner's `field` presets (from `GET /preset`). Choosing one writes an `origin` condition. Its operator/value input uses the saved field's own kind and, for choice fields, its options. Table saved fields offer their columns as `sub_key`.
- Copy follows design §24 (no node/graph wording).

### Content

- **Catalogue entry `field-status`:** a `field` preset "Status", choice with options Owned and Wanted. My call: no default value, and an unset status reads as owned in copy, so existing items need no backfill. It's filterable as "Status is Wanted".
- **Catalogue entry `field-acquisition`:** a `field` preset "Acquisition", a table (group) with columns Date (partial date), Price (money), Source (text), How (choice: Bought, Gift, Inherited, Traded) and Notes (long text). Repeating, so a resale or second purchase is a new row. **My call:** it replaces the existing single-row `group-purchase-details` field group, since alpha allows renaming outright. If removal is unwanted, keep both.
- **Example packs:** add Status and Acquisition to the example item types where they fit. Ship a "Wanted" smart collection: `{"kind": "field", "field_kind": "choice", "key": "status", "op": "=", "value": "Wanted"}`. The loose form is used, so it works on the user's own types that never came from the pack.
- **Cards and item page:** Status and the latest acquisition show through the existing highlight settings. Check that a table field highlights sensibly (latest row) and fix it generally if not. That is a general table-highlight improvement, not acquisition code.

### Docs

- `docs/DECISIONS.md`: update the 2026-10-16 entry (the widened `field_kind` meaning) and add "Cross-type field conditions expand at resolution".
- `docs/field-types.md` / search docs: describe the two new ways of addressing a field.
- `shared/contracts/query-shapes.json`: cases for both forms, `sub_key`, the no-match case and scoped `!=`.

## Constraints

- Backend layering: the expansion pass is application-layer and pure over loaded schemas. No adapter change is expected beyond the internal overlay leaf. `graph` must not import `presets` (the origin is a string in the schema).
- Coverage floors (100% domain/application). Shared contract cases must pass in both Postgres and in-memory adapters.
- Pack portability: an `origin` in a pack's smart collection is written as `{"$preset": ref}` and resolved by the existing `resolve_preset_refs`.

## Left to the builder

- The internal overlay-leaf representation.
- The exact builder layout, within design §15/§24.
- Whether the expansion pass is folded into `expand_collections` or runs beside it.
- Which example item types get Status and Acquisition.
