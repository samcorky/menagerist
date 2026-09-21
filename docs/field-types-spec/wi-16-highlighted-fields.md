# WI-16: Highlighted fields on cards

> Part of the field-types spec. Read `00-INDEX.md` and `01-context-and-conventions.md` first (skip the second if this is that file).
> **Depends on:** WI-14 and WI-8 (normalisation); WI-20 first is recommended.
> "WI-n" refers to `wi-*.md` files listed in `00-INDEX.md`; "open question N" refers to `open-questions.md`.


**Goal.** Let a node type choose which of its fields are *highlighted*, so their values appear wherever a compact summary of an item is shown. Example: a Movie type highlights Director and its star rating, so the movie card shows them without opening the item.

**Decision: display only.** Highlighting affects presentation and nothing else. It does not change search (all attribute values are searchable, see WI-17), validation, layout or how values are stored.

**Current state (verified).**
- The collection list card shows the name, one line of description and a type badge; the grid card shows the cover image, name and type label. Neither shows any attribute.
- The relationship target picker on the item page filters and shows `name + type` only.
- `NodeResponse` already includes `attributes`, and the collection page already loads node types with their schemas. So this is a frontend feature with **no API change**.

**Storage.** One ordered list at the schema root, inside `x-menagerist` (WI-14), using objects (like the layout) so options can be added later without a format change:

```json
"x-menagerist": {
  "version": 1,
  "highlights": { "card": [ { "key": "director" }, { "key": "my_rating" } ] }
}
```

- Order is display order. Maximum of 3 entries (a constant, enforced by the editor and by `normaliseHighlights`).
- Other surfaces derive from the same list in v1 instead of having their own configuration (progressive disclosure): the relationship picker appends the first highlighted value (for example "Alien · Ridley Scott"), and relationship rows on the item page show the first two. Explicit per-surface lists (`highlights.picker`, and later others) are reserved but not implemented.
- Shown counts per surface are constants in one place (proposal: grid card 2, list card 3, picker 1, relationship row 2).

**Scope.** Highlights are scoped to the **item type**: one ordered list in that type's schema (`x-menagerist.highlights.card`), shared by every user and every item of that type. They are not per item, per user or per view. Per-item overlay fields (WI-19d) cannot be highlighted, and items with no type have none. The relationship type has its own list for connection details (WI-22).

**Eligibility and rendering.** Each descriptor declares whether it can be highlighted and how it renders compactly.
- `highlightable?: boolean` (default `false`). Built-ins: text, number, boolean, date, choice and rating are `true`; longtext, group and opaque are `false` in v1.
- `SummaryWidget?: Component<{ value: unknown; prop: JsonSchemaProperty; size: 'sm' | 'md' }>`. Rating reuses the star view at a compact size; choice renders as a small badge; date uses the shared date formatter from WI-3; boolean shows a labelled chip only when true; text and number render as truncated text. Without a `SummaryWidget` the value is formatted as plain text.
- Empty values are skipped entirely (no blank label or placeholder).

**Truncation and hierarchy.** Highlighted values follow the guidelines: single line with an ellipsis on cards, full value on hover or tap (§7c), long text is never shown on a card, and the cover image and title keep visual priority (§3.2, so the grid card shows at most two).

**One shared renderer.** Add `node-summary.svelte` (inputs: node, its node type, surface, size), used by the list card, grid card, relationship picker and relationship rows. All limits, ordering and formatting live there, so every surface stays consistent.

**Editor UX.**
- Each eligible field in the schema editor gets a "Show on card" toggle (a pin or star icon). When the limit is reached the other toggles are disabled with a short hint.
- Highlighted fields can be reordered (the same interaction as WI-13 when that lands; move up/down buttons until then).
- Optional: a live card preview at the top of the editor using sample values.

**Interactions.**
- WI-8: archiving or deleting a field removes it from `highlights`. `normaliseHighlights(highlights, properties)` drops dangling keys, archived properties, non-highlightable kinds, duplicates and anything over the limit, and runs wherever `normalise` runs for layout.
- WI-10: changing a field to a non-highlightable kind removes it from the list (with a note in the editor).
- WI-14: `schema-meta` gains `highlights(schema)` and `withHighlights(schema, list)`; the backend module needs no accessor because nothing in the backend depends on highlights.
- Backend: node-type and edge-type save validate the *shape* only, in the shared schema-check helper (`backend-surface.md`): keys exist, are not archived, are unique, and there are at most 3.
- Edge types: connection details get their own highlight list on the relationship type, and can be shown and edited on the item page. See WI-22.

**Acceptance.**
- Highlighting a rating and a text field on a type makes both appear on that type's list and grid cards, in the chosen order, and not on other types' cards.
- A node with an empty highlighted field shows no blank slot.
- Archiving a highlighted field removes it from cards immediately and from the stored list on the next save.
- Highlighting changes nothing in search results or validation.

**Tests.** `normaliseHighlights` (dangling, archived, over-limit, duplicates, non-highlightable); `node-summary` with each kind, empty values and each size; `SummaryWidget` for rating, choice, boolean, date; shared contract fixture containing `highlights`; end-to-end: highlight a rating, see the stars on the card.
