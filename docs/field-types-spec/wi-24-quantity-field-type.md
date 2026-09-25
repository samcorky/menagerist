# WI-24: Quantity field kind (number + unit)

> Part of the field-types spec. Read `00-INDEX.md` and `01-context-and-conventions.md` first (skip the second if this is that file).
> **Depends on:** WI-14 (`x-menagerist.kind`), WI-1 (empty-value omission pattern), WI-20 (readable keys for the two nested properties, if it ends up as an object). Shares a prerequisite with the candidate `location` kind (`further-field-types.md`): the attributes editor's rows currently stringify everything, so an object-shaped value needs the same lossless round-trip fix either kind can land first and unblock the other.
> "WI-n" refers to `wi-*.md` files listed in `00-INDEX.md`; "open question N" refers to `open-questions.md`.


**Motivating case.** A recipe's ingredient table wants "Flour — 200 g", "Sugar — 1 cup": a number and a short unit, entered and displayed together, sortable by the number. Also fits weight, dimensions, duration and page count generally (`further-field-types.md`'s "Measurement" row, promoted here as a scheduled item and renamed to match the general shape rather than one use case).

**Stored as** a small object, the same pattern as the candidate `location` kind:

```json
"weight": {
  "title": "Weight",
  "type": "object",
  "properties": {
    "value": { "type": "number" },
    "unit": { "type": "string" }
  },
  "x-menagerist": { "kind": "quantity" }
}
```

A value is `{"value": 180, "unit": "g"}`. Both parts are independently optional (a bare number with no unit, or a unit note with no number, are both legitimate half-filled states); an empty object is valid and must be omitted rather than saved, same as WI-1's rule for empty scalars and the `location` kind's own empty-object rule.

**Unit input (v1: free text).** A plain text input next to the number, not a fixed list — "g", "cups", "minutes", "pages" all need to fit without pre-registering every possible unit. A "Show as" display option (WI-11 pattern) offering a short curated preset list (mass, length, time) is worth adding once there's a concrete need for it; not in v1. If it lands, it's a natural fit for a `choice_list` preset (WI-19c) rather than a hardcoded list in this kind.

**Sub-field use (the motivating case) — implemented later, not in v1.** The whole point of the ingredients example is "amount" as one quantity column instead of two (`quantity`, `unit`), but a group *cell* was typed `Record<string, string>` — a plain string per cell, not an object — so nesting a quantity inside a table needed cell-level object values, a second layer on top of the top-level-field prerequisite this item already needed. Implemented as `canBeSubField: false` in the v1 session; a follow-up session widened `GroupRow` to `Record<string, string | Record<string, string>>`, added the shared `coerceObjectValue`/`coerceGroupRow` helpers in `attribute-rows.ts`, and flipped both `quantity` and `choice` to `canBeSubField: true` (choice needed its own options editor in `GroupExtras.svelte`, not just the type flag). See `docs/DECISIONS.md`'s "Quantity and choice as table sub-fields" entry.

**Prerequisite (done as part of this item).** `AttributeRow.value` (the shared row type the attributes editor uses for every field, schema-defined or custom) widened to `string | GroupRow[] | GroupRow`; `attributesToRows` takes an optional `schema` so a key the schema defines as `type: 'object'` hydrates as an editable flat row instead of falling into the generic read-only-JSON branch; `rowsToAttributes` gained the matching write-back branch (coerce sub-properties, omit the whole key when every sub-value is blank). This is exactly the fix `location` (`further-field-types.md`) was waiting on too.

**In the app.**
- **Entering:** a number input and a short text input side by side, sharing one field row. Placeholder text on the unit input, no validation beyond "is a string" — this is deliberately loose in v1.
- **Viewing:** `"{value} {unit}"` when both are present ("180 g"); just the value or just the unit when only one is set; `—` when the whole field is empty (unset, matching every other empty-field convention in this spec).
- **Highlights (WI-16):** highlightable; `formatSummary` renders the same `"{value} {unit}"` text.
- **Search (WI-17):** the `unit` string is nested one level inside an object, not a bare top-level string value — check whether the current search implementation recurses into an object value or only scans top-level scalars and group rows before assuming this is free; if it does not, this kind needs the same extension WI-17 would need for `location`'s `label`.
- **Sorting/filtering by value:** out of scope for v1 (no smart group or sort control reads into a quantity's `value` yet); noted as a natural follow-up once a concrete need appears, not built speculatively.

**Backend:** nothing new beyond registering the kind conceptually — no port, no new validation keyword. Plain JSON in the existing `attributes`/`attributes_schema` column, same as `location`.

**Acceptance.**
- A quantity field round-trips `{value, unit}` through `toSchema`/`fromSchema` unchanged.
- Entering only a number, or only a unit, saves that partial value; entering neither omits the key entirely.
- Group (table) sub-field use is out of scope for v1 (see above); `canBeSubField: false`.

**Tests.** Unit: `toSchema`/`fromSchema` round-trip (both parts, value-only, unit-only, explicit-kind-only matching); the empty/partial-value omission in `attributesToRows`/`rowsToAttributes`; `formatSummary` output for each of the three non-empty states. Contract fixture: add a quantity example (for instance a "Weight" field) to `example-node-type-schema.json`, matching how `my_rating` and `tracklist` already serve that role for their kinds.
