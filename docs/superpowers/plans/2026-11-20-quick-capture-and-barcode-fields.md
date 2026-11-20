# Quick-capture fields (#606) and barcode-capable fields (#605) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an item type mark simple fields to appear in quick capture (#606), and mark text fields as taking barcodes so a scan lands in the right field on capture, new-item and edit screens (#605).

**Architecture:** Two new boolean members in a field's `x-menagerist` metadata, `capture` and `barcode`, so they travel with types, presets and exports. A shared "field flags" row in the type editor shows the switches that apply to the field's kind. Quick capture reuses `AttributesEditor` filtered to the flagged keys, rather than building a second form. A scan button in `AttributesEditor` fills one barcode field.

**Tech Stack:** SvelteKit/Svelte 5 runes, Vitest, Playwright, FastAPI/pytest.

**Spec:** GitHub issues #606 and #605 and the decisions recorded below. There is no separate spec document.

## Decisions (from the grilling)

- Quick-capture kinds: every one-line kind, which is text, number, boolean, choice, multichoice, date, partialdate, rating, money, quantity, duration, url, email, phone and timezone. Group, list, checklist, longtext, cron and opaque are excluded.
- Editor UI: one switch per field, in a shared flags row in the type editor only (not on per-item extra fields).
- No limit on how many fields can be flagged. Required fields need no special treatment, because `required` is advisory and never blocks a save.
- The flagged fields render after Item type and before the Barcode block. The real sheet order is Photo, Name, Type, then Barcode. The answer "after type, before photo" assumed the photo came last, so its intent is kept: after the type.
- "Use full form" carries the entered values over.
- Barcode-capable kinds: text only.
- Flagged barcode fields win. When a type has none, the label guess (`suggestScanField`) is the fallback.
- In capture, a scan fills the barcode field in place when that field is shown, and the "Save in" picker appears only when it is not.
- A per-field scan button appears on both the new-item and edit forms.
- Delivery: stacked PRs with `gh stack`, part A (#606) as the base and part B (#605) on top. Each layer keeps its own tests, including end-to-end tests, green.

## Global Constraints

- British English in copy and comments. Collector-facing terms only, so say "field" and "item type", never "property" or "node".
- Never `git add` or `git commit`: the user commits. Where a task ends, stop and report.
- Verification per layer: `poe test-frontend --mode agent`, `poe typecheck-frontend --mode agent`, `poe lint-frontend --mode agent`, plus targeted Playwright specs. The backend layer also needs `poe typecheck-backend --mode agent` and `poe coverage --mode agent`.
- Never hand-edit `src/lib/api/generated/`. No schema change is expected, because the metadata lives inside the JSON Schema blob.

## Review Focus

1. **Type changed after typing values in capture.** The fields switch to the new type's flagged fields and the old values are dropped, but a scanned code stays. Test in Task A4.
2. **A flagged field that is later archived, or changed to an ineligible kind** (text → longtext). It does not appear in capture, and in the editor the switch is hidden for the ineligible kind. Tests in Tasks A2 and A3.
3. **A type with nothing flagged.** The capture sheet is unchanged from today, with no "Details" heading and no empty box. Test in Task A4.
4. **Flagged fields inside a section.** They appear flat, in the type's display order. Test in Task A3.
5. **Non-string values carried to the full form** (a rating number, a yes/no). They arrive on the new-item form with the right type. Test in Task A5.

---

## Part A: #606, quick-capture fields (branch `feat/606-quick-capture-fields`)

### Task A1: Accept `capture` and `barcode` as boolean field metadata (backend)

Both flags go in now so part B needs no backend layer.

**Files:**
- Modify: `backend/src/app/modules/graph/application/schema_meta.py:16`
- Test: `backend/tests/modules/graph/application/test_schema_meta.py`

- [ ] **Step 1:** Write a failing test, `test_capture_and_barcode_must_be_booleans`. It is parametrised over `"capture"` and `"barcode"`. A property with `{"x-menagerist": {member: "yes"}}` raises `InvalidSchemaError` with a message ending `/{member} must be a boolean`, and `True` passes. Follow the pattern the existing `multiline` shape test uses.
- [ ] **Step 2:** Run `poe test-backend --mode agent -- backend/tests/modules/graph/application/test_schema_meta.py`. Expect FAIL.
- [ ] **Step 3:** Extend `_PROPERTY_BOOL_MEMBERS` to `("archived", "search", "suggest", "multiline", "capture", "barcode")`.
- [ ] **Step 4:** Rerun the test. Expect PASS.

### Task A2: The field-flags model and the type-editor switch

**Files:**
- Create: `frontend/src/lib/field-flags.ts`
- Create: `frontend/src/lib/components/field-flags.svelte`
- Modify: `frontend/src/lib/prop-meta.ts` (add `capture?: boolean; barcode?: boolean;` to `PropertyMeta`, each with a one-line doc comment)
- Modify: `frontend/src/lib/components/field-kind-row.svelte` (new prop `showFlags = false`; when it is true, render `<FieldFlags {field} onChange={onFieldChange} />` after the Required checkbox)
- Modify: `frontend/src/lib/components/schema-editor.svelte:428` (pass `showFlags`)
- Test: `frontend/tests/field-flags.test.ts`

**Interfaces:**
- Produces:
  ```ts
  export type FieldFlag = { member: 'capture' | 'barcode'; label: string; kinds: ReadonlySet<string> };
  export const FIELD_FLAGS: readonly FieldFlag[];           // part A: only the capture flag
  export const QUICK_CAPTURE_KINDS: ReadonlySet<string>;    // the 15 kinds in Decisions
  export function flagsFor(kind: string): FieldFlag[];       // the flags whose kinds include `kind`
  export function setFlag(field: EditorField, member: FieldFlag['member'], on: boolean): EditorField;
  ```
  `setFlag` with `on` false removes the member rather than writing `false`, so schemas stay clean.
- Copy: the capture switch label is `Show in quick capture`.

- [ ] **Step 1:** Write failing tests:
  - `flagsFor('text')` and `flagsFor('rating')` contain the capture flag.
  - `flagsFor('longtext')`, `flagsFor('group')` and `flagsFor('list')` are empty.
  - `setFlag(field, 'capture', true).meta?.capture === true`.
  - `setFlag(on, 'capture', false).meta` has no `capture` key.
  - A round trip through `propertyFromField`/`fieldFromProperty` keeps `capture: true`.
- [ ] **Step 2:** Run `poe test-frontend --mode agent -- field-flags`. Expect FAIL.
- [ ] **Step 3:** Implement `field-flags.ts`. Then implement `field-flags.svelte`, a checkbox per `flagsFor(field.kind)` styled like the Required checkbox, and wire it into `FieldKindRow`/`SchemaEditor`.
- [ ] **Step 4:** Rerun the test. Expect PASS. Then run `poe typecheck-frontend --mode agent`.

### Task A3: Which fields a type captures, and showing only those in `AttributesEditor`

**Files:**
- Create: `frontend/src/lib/quick-capture.ts`
- Modify: `frontend/src/lib/components/attributes-editor.svelte`
- Test: `frontend/tests/quick-capture.test.ts`, `frontend/tests/attributes-editor.test.ts`

**Interfaces:**
- Produces:
  ```ts
  /** Keys of the type's fields flagged for quick capture, eligible by kind and not archived, in display order (sections flattened). */
  export function captureFieldKeys(schema: AttributesSchema | null): string[];
  ```
  `AttributesEditor` gains the prop `only?: readonly string[]`. When it is set:
  - Render just those keys of `schema`, flat, in the given order.
  - Omit the "Details" label, the section headings, the extra-field block and the add-field UI.
  - Leave everything else (validation, touched state, server errors) unchanged.

- [ ] **Step 1:** Write failing tests in `quick-capture.test.ts`:
  - `captureFieldKeys(null)` is `[]`.
  - A schema with flagged `isbn` (text), unflagged `notes` and flagged `blurb` (longtext) gives `['isbn']`.
  - A flagged field marked `archived` is excluded.
  - Flagged fields inside a section come out in display order.
- [ ] **Step 2:** Write a failing test in `attributes-editor.test.ts`: with `only={['isbn']}`, the `isbn` input renders, other fields do not, and there is no "Details" label.
- [ ] **Step 3:** Run both files. Expect FAIL.
- [ ] **Step 4:** Implement `captureFieldKeys`, reusing `schemaToItems` and `isSection` as `scan-field.ts` does. Implement the `only` branch in the editor's markup around line 386.
- [ ] **Step 5:** Rerun both files. Expect PASS.

### Task A4: Quick capture shows and saves the flagged fields

**Files:**
- Modify: `frontend/src/lib/components/capture-sheet.svelte`
- Test: `frontend/tests/e2e/quick-capture.spec.ts`

**Interfaces:**
- Consumes: `captureFieldKeys` and `AttributesEditor`'s `only` prop (A3).
- Behaviour:
  - Load the types once a type is selected, not only after a scan: the `$effect` at line 37 keys on `selectedType !== null || code !== null`.
  - Keep `rows: AttributeRow[]` state, and reset it to `[]` whenever `selectedType` changes.
  - Render `<AttributesEditor bind:rows schema={typeSchema} only={captureKeys} />` after the Item type block, and only when `captureKeys.length > 0`.
  - `save()` sends `attributes: { ...rowsToAttributes(rows, typeSchema), ...barcode?.attributes }`. The barcode still wins for its own key and still sends `extra_schema`.
  - `resetState()` clears `rows`.

- [ ] **Step 1:** Write failing end-to-end tests in `quick-capture.spec.ts`:
  - `shows the type's quick-capture fields and saves them`: create a type with fields `ISBN` (text) and `Notes` (text), then flag `ISBN` with the "Show in quick capture" switch in the type editor. Open quick capture and choose the type. Expect an `ISBN` input and no `Notes` input. Fill both the name and ISBN, save, then open the item and see the ISBN value.
  - `a type with no quick-capture fields shows no extra inputs`: choose an unflagged type and expect no "Details" text in the dialog.
  - `changing the type drops values typed for the old one`: fill ISBN, switch to an unflagged type, switch back, and the ISBN input is empty.
- [ ] **Step 2:** Run `npx playwright test tests/e2e/quick-capture.spec.ts` from `frontend/`. Expect FAIL.
- [ ] **Step 3:** Implement the behaviour above.
- [ ] **Step 4:** Rerun the spec. Expect PASS. Also run `type-picker.spec.ts` and `barcode-scan.spec.ts`, which must stay green.

### Task A5: "Use full form" carries the values over

**Files:**
- Modify: `frontend/src/lib/capture.svelte.ts` (`PendingCapture.barcode` → `details: { attributes: Record<string, unknown>; extraSchema: AttributesSchema | null } | null`, holding the typed values merged with any scanned code)
- Modify: `frontend/src/lib/components/capture-sheet.svelte` (`openFullForm` builds `details` the same way `save()` builds its body; one helper is shared by both)
- Modify: `frontend/src/routes/items/new/+page.svelte:121-127` (replace the hand-built string rows with `attributesToRows(details.attributes, mergeAttributeSchemas(typeSchema, details.extraSchema))`)
- Test: `frontend/tests/e2e/quick-capture.spec.ts`

- [ ] **Step 1:** Write a failing end-to-end test, `the full form keeps quick-capture values`. Flag a text field `ISBN` and a rating field `Score` on a type. In capture, fill both, then click "Use full form →". The new-item form shows the ISBN value and the chosen rating.
- [ ] **Step 2:** Run it. Expect FAIL.
- [ ] **Step 3:** Implement the change. Update any unit test or mock that builds a `PendingCapture` with `barcode`.
- [ ] **Step 4:** Rerun it, plus `barcode-scan.spec.ts`, which covers the scan handoff. Expect PASS.

### Task A6: Gate part A

- [ ] Run `poe test-frontend`, `poe lint-frontend` and `poe typecheck-frontend` (`--mode agent`), plus `poe typecheck-backend --mode agent` and `poe coverage --mode agent`.
- [ ] Hand over to the user to commit. Then run `gh stack init` and `gh stack submit` for the base layer, with a PR that closes #606.

---

## Part B: #605, barcode-capable fields (branch `feat/605-barcode-fields`, stacked on A)

### Task B1: The "Takes barcodes" switch and the flagged-first field choice

**Files:**
- Modify: `frontend/src/lib/field-flags.ts` (add `{ member: 'barcode', label: 'Takes barcodes', kinds: new Set(['text']) }`)
- Modify: `frontend/src/lib/barcode/scan-field.ts`
- Test: `frontend/tests/field-flags.test.ts`, `frontend/tests/barcode-scan-field.test.ts`

**Interfaces:**
- Produces:
  ```ts
  /** Text fields flagged `barcode`, non-archived, in display order. */
  export function barcodeFields(schema: AttributesSchema | null): ScanField[];
  /** Fields offered for a scan: the flagged ones when any exist, otherwise every text field (today's `scanFields`). */
  export function scanTargets(schema: AttributesSchema | null): ScanField[];
  /** The field chosen before the person picks: the first flagged field, else the label guess, else null. */
  export function defaultScanField(schema: AttributesSchema | null): string | null;
  ```
  `suggestScanField` stays as the label-guess fallback that `defaultScanField` calls.

- [ ] **Step 1:** Write failing tests:
  - `flagsFor('text')` now has two flags, and `flagsFor('number')` has only capture.
  - `barcodeFields` returns flagged text fields only.
  - `scanTargets` returns only the flagged fields when some are flagged, and every text field otherwise.
  - `defaultScanField` prefers a flagged `Shop code` over an unflagged `ISBN`, and falls back to `ISBN` by label when nothing is flagged.
- [ ] **Step 2:** Run both files. Expect FAIL.
- [ ] **Step 3:** Implement the switch and the functions.
- [ ] **Step 4:** Rerun both files. Expect PASS.

### Task B2: A scan button beside barcode fields in the item form

**Files:**
- Modify: `frontend/src/lib/components/attributes-editor.svelte` (in `fieldEntry`, when `readPropMeta(prop).barcode === true` and the kind is text, put an icon button with `aria-label="Scan barcode into {label}"` beside the input; it opens one shared `BarcodeScanner`, and `onDetected` sets that key's value through the setter the `InputWidget` `onChange` uses)
- Test: `frontend/tests/attributes-editor.test.ts`, `frontend/tests/e2e/barcode-scan.spec.ts`

- [ ] **Step 1:** Write a failing unit test: a flagged text field renders the "Scan barcode into ISBN" button, and an unflagged one does not.
- [ ] **Step 2:** Write a failing end-to-end test, `scans into a barcode field on the edit page`. Use the existing camera/detector stub in `barcode-scan.spec.ts`. On an item whose type flags `ISBN`, enter edit, press the scan button, and the ISBN input holds the stubbed code. Save, and the value persists. Add a matching test for `/items/new`.
- [ ] **Step 3:** Run them. Expect FAIL.
- [ ] **Step 4:** Implement.
- [ ] **Step 5:** Rerun them. Expect PASS.

Because quick capture renders through `AttributesEditor`, a flagged field shown in capture now gets its own scan button too.

### Task B3: The capture sheet's scan uses the declaration

**Files:**
- Modify: `frontend/src/lib/components/capture-sheet.svelte`
- Test: `frontend/tests/e2e/barcode-scan.spec.ts`

**Behaviour:**
- `codeFields = scanTargets(typeSchema)`, and `codeField` defaults to `defaultScanField(typeSchema) ?? NEW_BARCODE_DETAIL`.
- When a code is scanned and `codeField` is in `captureKeys`, write the code into that row (replacing any typed value), clear `code`, and do not show the Barcode/"Save in" block.
- Otherwise, keep today's block and picker unchanged. The "new Barcode detail" fallback stays.

- [ ] **Step 1:** Write failing end-to-end tests:
  - `a scan fills the visible barcode field`: on a type whose `ISBN` is flagged both capture and barcode, scan from the sheet, and the ISBN input holds the code with no "Save in" select shown.
  - `a flagged field is chosen over a label match`: a type has a flagged `Shop code` and an unflagged `ISBN`, neither shown in capture. After a scan, "Save in" defaults to `Shop code`.
- [ ] **Step 2:** Run them. Expect FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Rerun them, plus the existing barcode and quick-capture specs. Expect PASS.

### Task B4: Gate part B

- [ ] Run `poe test-frontend`, `poe lint-frontend` and `poe typecheck-frontend` (`--mode agent`). There are no backend changes in this layer.
- [ ] Hand over to the user to commit. Then run `gh stack add` and `gh stack submit`, with a PR that closes #605.
