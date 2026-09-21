# WI-13: Drag-and-drop layout editor (stretch)

> Part of the field-types spec. Read `00-INDEX.md` and `01-context-and-conventions.md` first (skip the second if this is that file).
> **Depends on:** WI-8 (layout must skip archived) and WI-14 (`layout`); benefits from WI-11. Stretch.
> "WI-n" refers to `wi-*.md` files listed in `00-INDEX.md`; "open question N" refers to `open-questions.md`.


**Prior art (borrowed idea 3 of 3).** JSON Forms describes layout with a small vocabulary: vertical layout (default), horizontal layout (fields side by side), group (labelled box) and categorization (tabs or a stepper). This item adopts that vocabulary for the layout tree (`x-layout` today, `x-menagerist.layout` after WI-14), and adds drag-and-drop editing on top. Layout stays inside the single schema (no separate UI schema).

**Why it is a stretch.** Nothing else depends on it, and the current flat list plus sections already works. Do it after WI-8 and only if the schema editor is still the bottleneck for users. It must not make the editor feel like configuring a database; the default experience stays "add a field, it appears at the bottom".

## Current model (verified in `frontend/src/lib/layout.ts`)

```ts
type LayoutFieldItem   = { key: string };
type LayoutSectionItem = { id: string; section: string; collapsed?: boolean; items: LayoutFieldItem[] };
type XLayout = (LayoutFieldItem | LayoutSectionItem)[];
```

It is an array (JSONB does not preserve object key order), depth 1, discriminated by `'section' in item`. `normalise()` drops dangling keys, appends unplaced keys and drops empty sections. `orderedKeys()` flattens one level. `schema-editor.svelte` (`schemaToItems` / `itemsToSchema`) and `attributes-editor.svelte` both walk this shape, as does the read-mode item page.

## Proposed layout vocabulary

All additions are backward compatible: existing schemas keep rendering identically.

| JSON Forms concept | Layout node | Behaviour |
|---|---|---|
| Vertical layout | the default top-level list | Fields stacked. Unchanged. |
| Group | existing `{ id, section, collapsed?, items }` | Labelled, optionally collapsed box. Unchanged, but `items` may now contain rows. |
| Horizontal layout | new `{ id, row: true, items: LayoutFieldItem[] }` | Fields side by side. Wraps to a single column on narrow screens (mobile friendly is a stated frontend goal). Fields only, 2 to 4 per row. |
| Categorization | new `{ id, tabs: { id, label, items }[] }` | Tabs (the shadcn-svelte Tabs component). Top level only. Each tab holds fields, sections and rows. |

Nesting limit: tabs at the top level; a tab or section contains fields, rows, and (tabs only) sections; rows contain fields only. Maximum depth 3. Enforce it in the editor and in `normalise`, which should flatten anything deeper rather than throw.

Explicitly out of scope: JSON Forms rules (show, hide, enable, disable based on other fields). Reserve nothing for them yet; see the note in `considered-not-adopted.md` on when to revisit.

## Editor behaviour

- Each field, section, row and tab gets a drag handle. Dropping is allowed between items and into containers.
- To make a row: an "Add row" button creates an empty row that fields can be dragged into (dragging one field beside another to auto-create a row is a further nicety, not required).
- Keyboard and touch are required, not optional: every item has "Move up / Move down" and "Move to…" (section, row, tab) actions so reordering never depends on dragging. Long-press or handle-only dragging on touch, and screen-reader announcements for moves.
- A preview toggle showing the attributes editor as it will render is desirable but optional.

## Architecture

- Keep all tree manipulation in pure functions in `layout.ts` (or a sibling module): `insertNode`, `removeNode`, `moveNode(tree, from, to)`, `validateDepth`. Unit test them exhaustively. The drag-and-drop library is only a thin adapter that calls them.
- Choose the library after a short spike. Requirements: Svelte 5 compatible, works with touch and keyboard, nested containers, small footprint, no fight with shadcn-svelte or bits-ui. Candidates to evaluate include `svelte-dnd-action`, `@dnd-kit-svelte/*` and Atlassian's `pragmatic-drag-and-drop`; check current Svelte 5 support before committing. Record the choice in `docs/DECISIONS.md`.
- Generalise `EditorItem` in `schema-editor.svelte` from `EditorField | EditorSection` to a recursive tree, and make `schemaToItems` / `itemsToSchema` recursive.
- Make `normalise`, `orderedKeys` and `isSectionItem`-style guards recursive, and add `isRowItem` / `isTabsItem`. `orderedKeys` is used to compute "Additional details" rows in `attributes-editor.svelte`; if it stops flattening deeper nodes, every field inside a row or tab will also appear as a custom field. Add a test for exactly this.
- Renderers: `attributes-editor.svelte` and the read-mode block on `frontend/src/routes/collection/[id]/+page.svelte` both need row and tabs rendering. Prefer one shared layout-renderer component with a snippet for the leaf field so edit and read mode cannot drift.
- Empty containers: today `normalise` and `itemsToSchema` drop empty sections, so a new section disappears if saved before anything is dragged in. Persist empty containers in the schema, and have only the render path hide them (for example a `keepEmpty` option on `normalise`, on for the editor and off for rendering).
- WI-8 interplay: archived fields are removed from the layout and skipped by `normalise`.
- Backend: the layout is opaque to the backend today (`jsonschema` ignores unknown keywords). Optional: validate its structure on node-type save and raise `InvalidSchemaError`, so malformed layouts from API clients cannot break rendering. Decide in review.

## Acceptance

- Reorder a field by dragging, and by keyboard, in the schema editor; the order persists and the attributes editor and read mode reflect it.
- Move a field into and out of a section, a row and a tab.
- A row renders side by side on desktop and stacks on a phone width.
- Existing schemas (flat lists and depth-1 sections) render and re-save unchanged.
- Fields inside rows and tabs never show up as duplicates under "Additional details".
- Layout with dangling keys, unplaced keys or too much nesting normalises without errors.

## Tests

- Pure tree functions: insert, remove, move across containers, depth limit, moving into itself (rejected), moving a container with children.
- `normalise` and `orderedKeys`: recursive cases, dangling and unplaced keys, archived keys, `keepEmpty`.
- Editor round-trip: `schemaToItems(itemsToSchema(x))` is stable for rows and tabs.
- Component tests for row and tabs rendering; DnD gestures themselves only where the chosen library makes that practical (the pure functions carry the coverage).
