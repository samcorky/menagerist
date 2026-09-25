# WI-25: Ordered list and checklist field types

> Part of the field-types spec. Read `00-INDEX.md` and `01-context-and-conventions.md` first.
> **Status:** implemented. Promoted from `further-field-types.md`'s "Ordered list" row on direct request; "Checklist" was not in that file's original candidate list and was added the same session, also on direct request.

## Ordered list (`list`)

An ordered array of plain free-text strings, each editable, addable, removable and reorderable (up/down), with a display-only "Show as" choice between numbered (`1.`, `2.`, ...) and bulleted (`•`), default numbered. Matches `further-field-types.md`'s "Ordered list kind (candidate)" section as proposed, with no changes:

```json
"instructions": {
  "title": "Instructions",
  "type": "array",
  "items": { "type": "string" },
  "x-menagerist": { "kind": "list", "display": "numbered" }
}
```

- `canBeSubField: false`, not highlightable, searchable (default true — the existing recursive scalar scan for attribute search already walks into arrays generically, no schema change needed).
- Matched only by an explicit `x-menagerist.kind: "list"` (shape alone, a plain string array, is not distinctive — a future `multi-choice` kind could use the same shape).
- Item order needs no `x-menagerist.columns`-style bookkeeping (unlike `group`): JSONB preserves a JSON array's element order, it only reorders an *object's* keys.
- `attribute-rows.ts`: a schema-defined list value hydrates as `AttributeRow.value: string[]` (no stringifying needed, unlike quantity's object value). Write-back drops a blank/whitespace-only item and omits the key entirely if every item was blank.
- Files: `field-types/list/{list.ts, ListInput.svelte, ListView.svelte}`.

## Checklist (`checklist`)

Added mid-session when the owner asked about list "styles" and specifically wanted a checklist. **Not a `list` display variant** — a checklist item's tick is real per-item data that gets persisted, whereas `list`'s numbered/bulleted choice is purely cosmetic and never changes what's stored (`further-field-types.md`'s own explicit design constraint for `list`'s `display` option). That meant it needed its own kind, with its own stored shape:

```json
"packing_list": {
  "title": "Packing list",
  "type": "array",
  "items": {
    "type": "object",
    "properties": {
      "text": { "title": "Text", "type": "string" },
      "done": { "title": "Done", "type": "boolean" }
    }
  },
  "x-menagerist": { "kind": "checklist" }
}
```

- Same editing affordances as `list` (add/remove/reorder), plus a real checkbox per row bound to `done`. A done item's text is struck through in both the edit and read views.
- `canBeSubField: false`, not highlightable. No `displayOptions` — nothing to choose "Show as" between.
- Matched only by an explicit `x-menagerist.kind: "checklist"`. This one shape collision is real and immediate, not hypothetical: a checklist's raw stored value (`array of {text, done} objects`) is structurally identical to what a `group`/Table field's rows already look like, and also to `attribute-rows.ts`'s generic `isGroupValue` detection (any array of plain objects, used as the catch-all for an untyped/unknown key's array-of-objects value). `attributesToRows` therefore checks the schema's declared `checklist` kind *before* falling through to that generic group/json path — get the order wrong and a checklist's `done: true/false` silently becomes the string `''`/`'false'` (traced through `coerceGroupRow`'s scalar coercion, which only handles string cells) instead of a real boolean. A test locks this in (`attributes-editor.test.ts`, "does not confuse a checklist with a plain group").
- `attribute-rows.ts`: hydrates to `AttributeRow.value: ChecklistRow[]` (`{text: string; done: boolean}`, exported type) — `done` stays a real boolean throughout, unlike `boolean`'s own flat field (which stores `'true'`/`'false'` as strings because it has no array-item context to carry a real JS value through the row-editing layer). Write-back drops a row whose `text` is blank (its tick goes with it) and omits the key if every row was blank.
- Search: `done` (a boolean) is never matched by the existing scan (which already excludes booleans/nulls, matching only strings/numbers); `text` is matched like any string. No backend change needed.
- Files: `field-types/checklist/{checklist.ts, ChecklistInput.svelte, ChecklistView.svelte}`.

## Not done

- No third rendering style beyond numbered/bulleted for `list` (e.g. lettered) — explicitly deferred by the owner ("keep to numbered/bulleted/checklist for now"), consistent with this spec's general bias against speculative generality.
- Neither kind is a group sub-field, matches `list`'s original "probably not" open question; not reconsidered for `checklist` either.
- No live/interactive toggle of a checklist item's tick from the item's read-only view mode — ticking only happens in the edit form, same as every other field in this codebase (nothing here supports mutating data from view mode without opening the editor).
- No component tests (no component-testing infrastructure in this repo, by standing decision) — neither widget pair has been tried in a running browser yet.

**Checks run:** `poe lint-frontend`, `poe typecheck-frontend` (0 errors, 2 pre-existing unrelated a11y warnings) clean; `npx vitest run` 294/294 pass. No backend changes were needed for either kind.
