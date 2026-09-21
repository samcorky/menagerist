# WI-1 to WI-4: Bug fixes in the field-type work

> Part of the field-types spec. Read `00-INDEX.md` and `01-context-and-conventions.md` first (skip the second if this is that file).
> **Depends on:** None. WI-1 is extended by WI-15; WI-4 introduces the `opaque` kind that WI-14 relies on.
> "WI-n" refers to `wi-*.md` files listed in `00-INDEX.md`; "open question N" refers to `open-questions.md`.


All confirmed by reading the code and running a throwaway vitest probe against `rowsToAttributes` plus `@cfworker/json-schema`.

## WI-1 — Clearing a Choice or Date field blocks saving

**Problem.** `ChoiceInput` ("— select —") calls `onChange('')`, and `DateInput` calls `onChange('')` when the date is deselected. `rowsToAttributes` passes the empty string through for string-typed props. Both validators then reject it: the client (`Instance does not match any of [...]`, `String does not match format "date"`) and the backend (`jsonschema` with `FORMAT_CHECKER`). This happens even on optional fields.

**Spec.** In `rowsToAttributes` (`frontend/src/lib/components/attributes-editor.svelte`, module script), omit a top-level value when it is `''` and the property is a string with `enum` or `format: 'date'`, exactly as empty numbers are already omitted. Keep `''` for plain text and longtext (an empty string is a legitimate value there), **except** for a text property that carries a `pattern` (see WI-15): an empty string fails any anchored pattern, so a cleared optional field must be omitted instead.

**Acceptance.**
- Clearing a choice or date on an optional field saves successfully, and the key is absent from the payload.
- A required choice or date left empty produces the "required" signal (see WI-6), not an enum/format error.

**Tests** (`frontend/tests/attributes-editor.test.ts`): choice `''` omitted; date `''` omitted; text `''` kept.

## WI-2 — Blank cells in group rows

**Problem.** `GroupInput.addRow` seeds every cell with `''`. In `coerceScalar`, `Number('')` is `0`, so a blank number cell is saved as `0` (top-level numbers correctly omit blanks). A blank date cell is sent as `''` and fails format validation, which blocks the whole save.

**Spec.** In the group branch of `rowsToAttributes`, drop cells whose value is `''` when the sub-property is number, date or enum. Text sub-fields keep `''`. Decide whether a boolean cell that was never touched should be omitted or `false`, and document the decision. If a group row ends up with no keys at all, keep it as `{}`, because the user added the row deliberately.

**Acceptance.** A recipe row with a name and a blank quantity saves as `{name: 'Flour'}` (no `qty: 0`). A blank date cell does not block saving.

**Tests:** extend the existing type-coercion tests for group rows (blank number, blank date, blank text).

## WI-3 — `GroupView` shows dates a day early in negative UTC offsets

**Problem.** `GroupView.formatValue` uses `new Date(val)`. A `YYYY-MM-DD` string is parsed as UTC midnight, so it renders as the previous day in the Americas. `DateView` already avoids this with `new Date(value + 'T00:00:00')`.

**Spec.** Extract one shared helper (for example `formatIsoDate(value, style)` in `$lib`) that parses `YYYY-MM-DD` as a local date, and use it in both `DateView` and `GroupView`. Keep each caller's existing month style (long in `DateView`, short in `GroupView`). Never use `new Date('YYYY-MM-DD')` for display.

**Tests:** helper unit test run with `TZ=America/Los_Angeles` (or a fake timezone) asserting the day does not shift.

## WI-4 — Unrecognised schema properties are silently rewritten (minor)

**Problem.** Two related symptoms, both caused by `fromSchema` returning `null` or a lossy result:
- `text.fromSchema` rejects any string with a `format` (for example `email`). `propertyToField` then falls back to kind `text`, and `toSchema` drops the `format` on the next save.
- `group.fromSchema` does not guard sub-properties. It reads `items.properties` unconditionally (throws for an array of strings), and an API-authored enum sub-property maps to kind `choice` whose `toSchema` is called with `options: []`, producing `enum: []`.

**Spec (proposal).** Round-trip unrecognised properties losslessly:
- Add an `opaque` kind (not user-selectable) whose `EditorField` carries the raw property, for example an optional `raw?: JsonSchemaProperty`. Its `toSchema` returns the raw property untouched, with only the `title` updated if edited.
- `propertyToField` and `group.fromSchema` produce `opaque` when no descriptor matches (or the explicit `kind` from WI-14 is unknown), or when a sub-property's descriptor has `canBeSubField === false`.
- The editor shows opaque fields with a small "custom" badge and no kind dropdown. The attributes editor renders them with a plain text input (existing fallback).
- `group.fromSchema` must return `null` unless `prop.items.type === 'object'`.

**Acceptance.** A schema containing `{type:'string', format:'email'}` and an enum sub-property in a group survives open-edit-save byte-for-byte (apart from user edits).

**Tests:** round-trip tests in `tests/field-types.test.ts` for both cases.
