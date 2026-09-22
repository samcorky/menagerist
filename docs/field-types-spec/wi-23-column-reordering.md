# WI-23: Manual reordering of table (group) columns

> Part of the field-types spec. Read `00-INDEX.md` and `01-context-and-conventions.md` first (skip the second if this is that file).
> **Depends on:** the group column-order fix (session of 2026-09-22: `x-menagerist.columns` on a group property, `field-types/group/columns.ts`'s `orderedColumns`). Without it, reordering client-side would not survive a save (JSONB does not keep nested object key order).
> "WI-n" refers to `wi-*.md` files listed in `00-INDEX.md`; "open question N" refers to `open-questions.md`.


**Problem.** A table (`group` kind) field's sub-fields (columns) can only be added or removed in `GroupExtras.svelte`, never reordered. The order is whatever they were added in; fixing them once wrong means removing and re-adding every column after the one that's misplaced.

**Now unblocked.** Column order is written explicitly (`x-menagerist.columns`) and read by `orderedColumns()`, used by `GroupInput`, `GroupView` and `fromSchema`. Reordering `field.subFields` client-side and saving now correctly reorders the table, so the only missing piece is the control itself.

**Spec.**
- In `GroupExtras.svelte`, add Up/Down icon buttons (Lucide `ChevronUp`/`ChevronDown`) to each sub-field row, next to the existing kind select and remove button. Mirror the pattern already used for reordering highlighted fields in `schema-editor.svelte` (`moveHighlight`): disable Up on the first row and Down on the last, swap the sub-field with its neighbour in `field.subFields` on click, call `onChange`.
- No backend change and no new metadata: `toSchema` already writes `columns` from the current in-memory `subFields` order (this is exactly what the column-order fix added), so a reorder that gets saved produces the new order automatically.
- Keyboard: the buttons are ordinary `<button>` elements, so Tab/Enter/Space already work; no extra handling needed.

**Acceptance.**
- Moving a column up or down changes its position in the table's header and in every row of the data-entry and read-mode widgets.
- Saving the item type and reloading it keeps the new order (exercises the column-order fix and this control together).
- The first row cannot move up; the last cannot move down (buttons disabled, not hidden, so the row count stays visually stable).

**Tests.** Unit: a small reorder helper (swap by index, no-op at the ends) if extracted, or drive it through `GroupExtras`'s exported logic if kept inline. No new backend tests needed — `columns` round-trips are already covered by the column-order fix's tests. No component tests (decided elsewhere in this spec); check the buttons once in a browser.
