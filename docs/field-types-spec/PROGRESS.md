# Progress

Update at the end of every session. Read this first.

| Item | Status | Branch | Notes for the next session |
|---|---|---|---|
| WI-1 to WI-4 bug fixes | done, committed (138e7d5) | feature/initial-implementation | See "WI-1 to WI-4 session notes" below. |
| WI-14 metadata namespace | done, committed (093bca3) | feature/initial-implementation | See "WI-14 session notes" below. |
| WI-20 readable field keys | done, committed (ce327e2) | feature/initial-implementation | See "WI-20 session notes" below. |
| WI-5 rating | done, committed (c5a85f4) | feature/initial-implementation | See "WI-5 session notes" below. |
| WI-6 advisory required | done, committed (ada4dea) | feature/initial-implementation | See "WI-6 session notes" below. |
| WI-7 changed-keys validation | done, committed (14c4b53) | feature/initial-implementation | See "WI-7 session notes" below. |
| WI-8 archive fields | done, committed (4d93625) | feature/initial-implementation | See "WI-8 session notes" below. |
| WI-9 purge and usage | done, committed (a479871) | feature/initial-implementation | See "WI-9 session notes" below. |
| WI-10 kind changes and option warnings | done, committed (602cfe4) | feature/initial-implementation | See "WI-10 session notes" below. |
| WI-11 display options | done, committed (2668afd) | feature/initial-implementation | See "WI-11 session notes" below. |
| WI-12 rank matching (optional) | done, committed (92db277) | feature/initial-implementation | See "WI-12 session notes" below. |
| WI-15 text constraints | done, committed (26fdaca) | feature/initial-implementation | See "WI-15 session notes" below. |
| WI-16 highlighted fields | done, committed (44c01dc) | feature/initial-implementation | See "WI-16 session notes" below. |
| WI-17 attribute search | done, committed (06b605b) | feature/initial-implementation | See "WI-17 session notes" below. |
| WI-18 per-item custom fields | 18a done, committed (d9dbdc6); 18b and 18c todo | feature/initial-implementation | See "WI-18a session notes" below. 18b and 18c wait for the WI-19d overlay. |
| WI-19 presets | 19a done, awaiting user review and commit; 19b and 19c todo | feature/initial-implementation | See "WI-19a session notes" below. |
| WI-19d per-item schema overlay | done, committed (e1a17b8) | feature/initial-implementation | See "WI-19d session notes" below. |
| WI-21 value suggestions | todo | | |
| WI-22 connection details | 22a done, committed (66417f1); 22b done, committed (5706c51) | feature/initial-implementation | See "WI-22a session notes" below. |
| WI-13 drag-and-drop layout (stretch) | todo | | |
| WI-23 table column reordering | done, awaiting user review and commit | feature/initial-implementation | See "WI-23/WI-24 session notes" below. |
| WI-24 quantity field type | done, awaiting user review and commit | feature/initial-implementation | See "WI-23/WI-24 session notes" below. |
| Rating colour option + highlight-drop toast (open questions 6, 65) | done, all frontend checks green, not committed | feature/initial-implementation | Rating gained a `display: 'amber'\|'accent'` option (`field-types/rating/colour.ts`); `schema-editor.svelte`'s `handleFieldRowChange` now toasts when a kind change drops a highlight pin instead of doing so silently. See `docs/DECISIONS.md`. |
| Field-row overflow menu, invalid-field ring, overlay badge (open questions 73, 74, 75) | done, all frontend checks green, not committed | feature/initial-implementation | First use of a `dropdown-menu` component in the app (scaffolded via shadcn-svelte, `bits-ui` underneath, no new dependency). See `docs/DECISIONS.md`. |
| Quantity/choice as table sub-fields; usage/purge on group sub-keys | done, all backend and frontend checks green, not committed | feature/initial-implementation | See "Quantity/choice sub-fields and group sub-key usage checks" session notes below. |
| WI-25 ordered list (`list`) and checklist (`checklist`) field types | done, all frontend checks green, not committed | feature/initial-implementation | See "WI-25" session notes below. Also fixed in the same session: quantity's read-mode display showed only the unit (see `docs/DECISIONS.md`). |
| Weak ETags fix two-press save (open question 76) | done, backend checks green, not committed | feature/initial-implementation | Root cause confirmed from the owner's live Network-tab evidence: nginx gzip-compresses `/api/` responses and something in the proxy chain weakens a strong ETag on the way out when that happens. `etag_from_entity` now emits weak ETags itself so this is a no-op; `ConditionalRequest`'s comparisons also tolerate a weak/strong mismatch either way. See `docs/DECISIONS.md`. |

## WI-1 to WI-4 session notes

**Status:** implemented, all checks green, committed as 138e7d5.

**Done**
- WI-1: empty choice or date omitted from the payload (`rowsToAttributes`).
- WI-2: blank number, date and choice cells dropped from group rows; blank text kept as `''`; untouched boolean cells stay `false` (a checkbox has no unset state); a row with no keys stays `{}`.
- WI-3: `formatIsoDate` parses `YYYY-MM-DD` as a local date; used by `DateView` (long) and `GroupView` (short).
- WI-4: `opaque` kind (not user-selectable) round-trips unrecognised properties; group and top-level fallbacks use it; "custom" badge replaces the kind dropdown; `group.fromSchema` returns `null` unless `items.type === 'object'`.

**Left:** nothing in WI-1 to WI-4. The `pattern` exception in WI-1 (empty optional text with a pattern is omitted) belongs to WI-15 and is not implemented.

**Files touched** (all under `frontend/` unless noted)
- `src/lib/components/attributes-editor.svelte`, `schema-editor.svelte`
- `src/lib/field-types/`: `date/DateView.svelte`, `group/GroupView.svelte`, `group/GroupExtras.svelte`, `group/group.ts`, `registry.ts` (`selectable`), `index.ts`, new `opaque/opaque.ts`
- `src/lib/schema-types.ts` (`raw?` on `EditorField` and `EditorSubField`), new `src/lib/format-date.ts`
- `tests/attributes-editor.test.ts`, `tests/field-types.test.ts`, new `tests/format-date.test.ts`
- `docs/DECISIONS.md` (opaque kind and boolean cells), this file

**Checks run:** `poe lint-frontend` pass (prettier and eslint clean); `poe typecheck-frontend` 0 errors, 2 existing img-alt warnings (`capture-sheet.svelte`, `collection/new/+page.svelte`); `poe test-frontend` 80 tests in 9 files pass. Backend checks not run (no backend changes).

**Next session must know**
- `@cfworker/json-schema` was missing from `node_modules`; `npm ci` fixed it (environmental).
- `.svelte` edits go through the `svelte-file-editor` subagent. The Svelte MCP server timed out this session, so the autofixer was not run.
- `propertyToField` and `fieldToProperty` live in the `<script module>` of `schema-editor.svelte`, not in a `.ts` file.
- WI-14 should send an unknown explicit `kind` to `opaque`, and keep `raw` lossless when fields move under `x-menagerist`.
- The `x-multiline` / `x-layout` / root `required` handling touched here is replaced by WI-14; do not extend it.
- Files show as staged in `git status`; I did not stage them.

## WI-14 session notes

**Status:** implemented, all checks green, committed as 093bca3. Next item: WI-20 (readable field keys).

**Done**
- Frontend: new `src/lib/schema-meta.ts` (`readSchemaMeta`, `readPropMeta`, `withSchemaMeta`, `withPropMeta`, `META_VERSION`); `layout` and `required` now live in root `x-menagerist`; `x-multiline` replaced by `kind: 'longtext'`; every property written by the editor carries `kind`; `display`, `archived` and unknown members are preserved through `EditorField.meta`.
- `registry.ts`: `descriptorForProp` reads an explicit `kind` first (must still match the shape), then infers from standard keywords. New `fieldFromProperty` / `propertyFromField` are the single conversion path (also used by `group.ts` for sub-fields). Unknown kinds, kind/shape mismatches and unmatched shapes become `opaque`.
- Backend: new `application/schema_meta.py` (`required_keys`, `archived_keys`, `validation_schema`, `check_meta_shape`). `validate_attributes` now strips the root `required` and archived properties before validating; create/update node type and edge type reject wrongly typed `x-menagerist` members with `InvalidSchemaError`.
- Docs: `docs/field-types.md` (new namespace section, longtext row, registry lookup) and a `docs/DECISIONS.md` entry.

**Left:** nothing in WI-14. Only `version`, `layout`, `required`, `kind`, `display`, `archived`, `search`, `suggest`, `config` are typed; `highlights` (WI-16) is preserved as an unknown member until then.

**Files touched**
- Frontend: `src/lib/schema-meta.ts` (new), `schema-types.ts`, `layout.ts` (comment), `field-types/registry.ts`, `index.ts`, `text/text.ts`, `longtext/longtext.ts`, `group/group.ts`; `components/schema-editor.svelte`, `attributes-editor.svelte`, `routes/collection/[id]/+page.svelte`
- Frontend tests: `field-types.test.ts`, `attributes-editor.test.ts`, `registry.test.ts`, `layout.test.ts`, new `schema-meta.test.ts` (includes the "only the accessor reads `x-*`" check and the example-schema fixture round-trip)
- Backend: `application/schema_meta.py` (new), `_validate_attributes.py`, `create_node_type.py`, `update_node_type.py`, `create_edge_type.py`, `update_edge_type.py`; tests `test_schema_meta.py` (new), `test_validate_attributes.py`, `test_create_node_type.py`
- Docs: `docs/field-types.md`, `docs/DECISIONS.md`, this file, `open-questions.md`

**Checks run:** `poe lint-frontend` pass; `poe typecheck-frontend` 0 errors (2 existing img-alt warnings); `poe test-frontend` 101 tests in 10 files pass; `poe lint-backend` pass; `poe typecheck-backend` no issues; `poe test-backend` 499 pass; `poe coverage` all targets met (application 100%).

**Next session must know**
- Backend behaviour change: a root `required` array is now ignored by `validate_attributes` (advisory, decided with WI-14). WI-6 should reuse `required_keys` and rely on this; the remaining WI-6 work is mostly frontend (never block saving, "missing information" signal) plus the DECISIONS entry for soft required. WI-8 can reuse `archived_keys`; the backend already ignores archived properties when validating.
- Changing a field's kind in the schema editor keeps the old `meta` (for example `display`). WI-10 (kind changes) and WI-11 (display options) should reset or validate it.
- The `x-menagerist.layout` type is still `XLayout` (fields and sections); rows and tabs come with WI-13. The example fixture uses them, but the fixture test only checks properties.
- Old-format schemas lose layout, long-text rendering and required markers until re-saved (accepted, no migration).
- `uv sync --all-groups` in the repo root removes the backend dev dependencies. Use `uv sync --all-packages --group dev` (`poe sync-backend`) to repair; I had to do this once.
- The Svelte MCP autofixer worked this session and found nothing.

## WI-20 session notes

**Status:** implemented, all frontend checks green, committed as ce327e2 (includes the `package.json` cache flags and `.eslintcache` ignore). Next item: WI-5 (rating). Also in this working tree, from the user's request: `frontend/package.json` script caching flags and `.eslintcache` in `frontend/.gitignore`.

**Done**
- New `src/lib/field-key.ts`: `generateFieldKey(title, taken)` (NFKD ASCII slug, underscores, 40-character cap, `field` fallback, `_2`/`_3` uniqueness case-insensitive, avoids `Object.prototype` member names such as `constructor`) and `resolvePendingKeys`.
- New fields (top-level, in sections, and group sub-fields) are created with a placeholder key and `keyPending: true`; the real key is derived from the label while serialising and frozen once saved (saving closes the editor and reopening re-reads stored keys). Saved fields never change key.
- `schema-editor.svelte`: keys resolved across the whole schema (archived fields included); `properties` built with `Object.fromEntries` (safe for `__proto__`); `schemaToItems`, `itemsToSchema` and the item types are now exported for tests.
- Docs: `docs/DECISIONS.md` entry; `docs/field-types.md` "Field keys" note.

**Left (deferred on purpose)**
- The "adopt an existing custom detail" prompt when a new key matches a custom detail name: needs the WI-18c custom-names query. Do it in WI-18c.
- Integration tests with underscore keys (search, usage, purge): belong to WI-9 and WI-17.
- `key in schema.properties` and `props[key]` lookups in the attributes editor and item page still see inherited names for API-authored keys such as `constructor`; generated keys avoid them.

**Files touched:** `frontend/src/lib/field-key.ts` (new), `schema-types.ts`, `field-types/group/group.ts`, `components/schema-editor.svelte`, `field-types/group/GroupExtras.svelte`; tests `field-key.test.ts` (new), `schema-editor-keys.test.ts` (new); docs as above; `frontend/package.json`, `frontend/.gitignore`.

**Checks run:** `poe lint-frontend` pass; `poe typecheck-frontend` 0 errors (2 existing warnings); `poe test-frontend` 124 tests in 12 files pass. Backend unchanged, backend checks not run.

**Next session must know**
- WI-5, WI-18 and WI-19 must create fields through the editor's pending-key path (`keyPending: true`) or call `generateFieldKey` against the target schema, so keys stay readable and unique.
- The ESLint `no-control-regex` rule rejects `\x00` in regexes; the generator uses `[\u0080-\uffff]` to strip non-ASCII.

## WI-5 session notes

**Status:** implemented, frontend checks green, committed as c5a85f4. Next item: WI-6 (advisory required).

**Done**
- `field-types/rating/`: `rating.ts` (kind `rating`, stored as `type: number` with `minimum: 1`, `maximum: 5`, `multipleOf: 1` plus `kind`), `RatingInput.svelte` (radiogroup, hover preview, click sets, click on current clears, roving tabindex and arrow keys) and `RatingView.svelte`.
- `fromSchema` matches only an explicit `kind: 'rating'`, so the registration-order rule in the spec no longer applies (WI-14). It is registered after `number` for the dropdown order only.
- `canBeSubField: true`: WI-2 has landed, so a blank rating cell in a group row is omitted (tested).
- `JsonSchemaProperty`'s number variant gained optional `minimum`, `maximum`, `multipleOf`.
- Docs: `docs/field-types.md` row and `docs/DECISIONS.md` entry.

**Left:** star count is fixed at 5 (configurable in WI-11). `GroupView` still prints a rating sub-field as a bare number; give it stars if wanted. Widget behaviour (hover, keys) is not covered by component tests (decided: no component tests in this change); check it manually in the browser once.

**Files touched:** `src/lib/field-types/rating/{rating.ts,RatingInput.svelte,RatingView.svelte}` (new), `field-types/index.ts`, `schema-types.ts`; tests `field-types.test.ts`, `attributes-editor.test.ts`; `docs/field-types.md`, `docs/DECISIONS.md`.

**Checks run:** `poe lint-frontend` pass; `poe typecheck-frontend` 0 errors (2 existing warnings); `poe test-frontend` 132 tests in 12 files pass. Backend unchanged.

**Next session must know**
- The radiogroup `div` has `tabindex="-1"` instead of the reference's `svelte-ignore` comment (silences the a11y warning); a click on the gap between stars can focus the `div`.
- The example fixture's `my_rating` now round-trips through the real rating descriptor.

## WI-6 session notes

**Status:** implemented, all checks green, committed as ada4dea. Next item: WI-7 (changed-keys validation).

**Done**
- Most of WI-6 already landed with WI-14: the editor writes `x-menagerist.required` (never a root `required`), the asterisk reads it, and the backend `validate_attributes` strips the root `required`.
- New here: `validationSchema()` in `schema-meta.ts` drops a standard root `required` before the attributes editor's client validator runs, so an API-authored schema cannot make required block a save. Wired into `attributes-editor.svelte`.
- Confirmed the "Confirm before implementing" question (also closed as Q1): Save is disabled only while saving or loading (`collection/[id]`), or for an empty name (`collection/new`); client `fieldErrors` never gate it.
- Tests: backend `CreateNode` with a missing required attribute succeeds; frontend `validationSchema` unit tests, and the schema editor emits no root `required`. `docs/DECISIONS.md` entry added.

**Left:** WI-1's acceptance line "a required empty choice or date produces the required signal" now means only the asterisk: there is no error. A "recommended" highlight or the "items missing information" group (guidelines §16a and §18) is not built; the asterisk is always shown, red, whether or not the field is filled. Decide if that needs a softer style.

**Files touched:** `frontend/src/lib/schema-meta.ts`, `components/attributes-editor.svelte`; tests `schema-meta.test.ts`, `schema-editor-keys.test.ts`, backend `test_create_node.py`; `docs/DECISIONS.md`.

**Checks run:** `poe lint-frontend` pass; `poe typecheck-frontend` 0 errors (2 existing warnings); `poe test-frontend` 134 tests pass; `poe lint-backend` pass; `poe typecheck-backend` clean; `poe test-backend` 501 pass.

**Next session must know:** WI-7 also edits `_validate_attributes.py`; apply its changed-keys logic on top of `validation_schema`.

## WI-7 session notes

**Status:** implemented, all backend checks green, committed as 14c4b53. Next item: WI-8 (archive fields).

**Done**
- `validate_attributes(schema, attributes, *, previous=None)`: with `previous` set (updates), errors under a top-level key whose value equals the stored value are dropped; root-level errors are kept; `previous=None` (create) is unchanged. Values compare as canonical JSON (type-strict), which the spec did not ask for but avoids `1 == True` hiding a change.
- `UpdateNode` passes `node.attributes` and `UpdateEdge` passes `edge.attributes` as `previous`. Create paths untouched. No port, adapter or API change; no frontend change (the editor already maps server errors onto fields).
- Tests: unchanged invalid key ignored, changed invalid key errors, changed valid key passes, group deep equality, `True` vs `1`, root-level errors kept, create validates everything; use-case tests for `UpdateNode` and `UpdateEdge`. `docs/DECISIONS.md` entry added.

**Left:** nothing. Note that comparison is per top-level key, so an edit anywhere inside a group re-validates the whole group.

**Files touched:** `backend/src/app/modules/graph/application/_validate_attributes.py`, `update_node.py`, `update_edge.py`; tests `test_validate_attributes.py`, `test_update_node.py`, `test_update_edge.py`; `docs/DECISIONS.md`.

**Checks run:** `poe lint-backend` pass; `poe typecheck-backend` clean; `poe test-backend` 510 pass; `poe coverage` all targets met (application 100%). Frontend unchanged, frontend checks not run.

**Next session must know:** WI-8 builds on `archived_keys` / `validation_schema` in `schema_meta.py`; the backend already ignores archived properties when validating, so WI-8 is mostly the editor UI (archive instead of delete, "Removed fields", restore) plus hiding archived fields from forms and "Additional details".

## WI-8 session notes

**Status:** implemented, all frontend checks green, committed as 4d93625. Next item: WI-9 (purge and usage). It is backend plus a UI; read `wi-09-purge-and-usage.md`, `backend-surface.md` and testing rows I-x first.

**Done**
- Schema editor: removing a saved field (top-level, in a section, or a whole section) archives it (`x-menagerist.archived`) instead of deleting; unsaved fields are removed outright. A 5-second Undo toast restores the earlier editor state. A collapsed "Removed fields (N)" list has a Restore action that re-adds the field at the end of the layout.
- `schemaToArchived()` and `itemsToSchema(items, baseMeta, archived)`: archived fields stay in `properties`, out of `layout` and `required`, and keep occupying their keys (a new same-titled field gets `_2`).
- `normalise()` skips archived properties (even if the saved layout lists them); the attributes editor and the item page exclude archived keys from "Additional details"; `validationSchema()` also drops archived properties. Backend already ignored them (WI-14).
- New helpers: `src/lib/field-archive.ts` (`archiveField`, `restoreField`), `archivedKeys()` in `schema-meta.ts`.
- Docs: `docs/DECISIONS.md` entry, `docs/field-types.md` section, `frontend/DESIGN_GUIDELINES.md` §14 note (Undo for removing a field; confirmation only for permanent deletion).

**Left:** the removal, Undo and Restore flow has not been checked in a browser (no component tests, by decision); try it once in the categories and relationships settings pages. A restored field returns at the end of the layout, not its old position (Q in the spec; default kept). The "archive-then-purge" DECISIONS entry is completed by WI-9. The read-only item page shows archived data nowhere, which is intended.

**Files touched:** frontend `src/lib/layout.ts`, `schema-meta.ts`, `field-archive.ts` (new), `components/schema-editor.svelte`, `components/attributes-editor.svelte`, `routes/collection/[id]/+page.svelte`; tests `layout.test.ts`, `schema-meta.test.ts`, `schema-editor-keys.test.ts` (one WI-20 test updated), `field-archive.test.ts` (new); docs as above.

**Checks run:** `poe lint-frontend` pass; `poe typecheck-frontend` 0 errors (2 existing warnings); `poe test-frontend` 146 tests in 13 files pass. Backend unchanged.

**Next session must know**
- `schemaToItems` no longer returns archived fields; callers that build a schema from items must pass `schemaToArchived(schema)` as the third argument to `itemsToSchema`, or archived fields are lost.
- WI-9's purge should reuse `archivedKeys` and only be offered for archived fields.

## WI-9 session notes

**Status:** implemented, all backend and frontend checks green, committed as a479871. Next item: WI-10 (kind changes and option warnings).

**Done**
- Backend: `NodeRepository` and `EdgeRepository` gained `count_with_attribute(type_slug, key)` and `list_with_attribute(type_slug, key, *, after, limit)` (SQLAlchemy via JSONB `has_key`, and in-memory siblings). New use cases `CountNodeTypeAttributeUsage`, `CountEdgeTypeAttributeUsage`, `PurgeNodeTypeAttribute`, `PurgeEdgeTypeAttribute`. The purge pages 100 at a time, removes the key and saves each item through the unit of work, so ETags change. Routes: `GET /node-type/{id}/attribute/{key}/usage`, `DELETE /node-type/{id}/attribute/{key}` and the `/edge-type` equivalents; shared response models in `adapters/api/attribute_schemas.py`. No permission checks (decided; recorded in DECISIONS).
- Frontend: `SchemaEditor` takes `typeId` and `typeKind`; in the edit forms of the categories and relationships pages the "Removed fields" list shows "Used by N items/connections" and "Delete data permanently" with an inline confirmation repeating the count. A count of 0 just removes the field from the list. Copy helpers in `src/lib/field-usage.ts`.
- Regenerated the API client with `poe generate-frontend-client` (generated code is gitignored).
- Tests: use-case unit tests (usage, purge, paging, not found, ETag/`updated_at`), in-memory repository tests, router tests for both type kinds, two `@pytest.mark.integration` JSONB tests, `field-usage.test.ts`. `docs/DECISIONS.md` and `docs/field-types.md` updated.

**Spec differences:** `EdgeRepository` had no `count`, `clear_type` or type filter as the spec assumed, so both repositories got dedicated `count_with_attribute` and `list_with_attribute` instead of a `has_attribute` filter on `list`. The optional `value=` argument (WI-10) is not added yet. Mypy needs `builtins.list[...]` in the new signatures because each repository has a method named `list`.

**Left:** the purge UI has not been tried in a browser. The purge takes effect immediately while the property leaves the schema only when the form is saved (cancelling the form after a purge leaves an archived field with no data). Keys containing `/` cannot be addressed by these routes. No frontend component tests (decided).

**Files touched:** backend `ports/{node,edge}_repository.py`, `adapters/persistence/{node,edge,in_memory_node,in_memory_edge}_repository.py`, new `application/{count,purge}_{node,edge}_type_attribute*.py`, `adapters/api/{dependencies.py,attribute_schemas.py,node_type/router.py,edge_type/router.py}`; frontend `components/schema-editor.svelte`, `routes/settings/{categories,relationships}/+page.svelte`, `src/lib/field-usage.ts`; tests and docs as above.

**Checks run:** `poe lint-backend`, `poe typecheck-backend` clean; `poe test-backend` 525 pass; `poe coverage` all targets met (application 100%, integration tests included, 27 pass); `poe lint-frontend` pass; `poe typecheck-frontend` 0 errors (2 existing warnings); `poe test-frontend` 148 pass.

**Next session must know:** WI-10 needs `count_with_attribute(type_slug, key, value=...)` for option-in-use counts; extend the two new methods and the `Count*AttributeUsage` queries and endpoints with an optional `?value=`. The "confirm on permanent deletion" wording lives in `frontend/DESIGN_GUIDELINES.md` §14 (added in WI-8).

## WI-10 session notes

**Status:** implemented, all backend and frontend checks green, committed as 602cfe4. Phase 3 (schema evolution, WI-6 to WI-10) is complete. Next item in the table: WI-11 (display options); WI-12 is optional.

**Done**
- Kind changes: `field-types/kind-changes.ts` holds a central matrix (`allowedKinds`, `kindChangeWarning`, `changeKind`). A saved field (`EditorField.originalKind`, set on load) can only switch to allowed kinds in the schema editor's dropdown and in group sub-field dropdowns; new fields can be any kind. Number to rating shows a warning; switching kind drops `display` and `config` (answers open question 55).
- "Replace" button on saved fields: archives the old field and adds a new text field in the same place, with the 5-second Undo toast.
- Choice options: removing an option that stored values use shows "“X” is used by N items. They keep it, shown as (no longer an option)." (non-blocking); the usage endpoints (`GET .../attribute/{key}/usage`) take an optional `?value=` (exact string match, JSONB containment). `ChoiceInput` shows a stored value that is no longer an option as selected, labelled "(no longer an option)".
- Backend: `count_with_attribute(..., *, value=None)` on both repositories; `Count*AttributeUsage` queries and routers accept `value`. Client regenerated.
- Tests: kind matrix, `changeKind`, `originalKind`, `staleChoice`, warning copy; backend value-match tests (in-memory, use case, router, integration). `docs/DECISIONS.md` and `docs/field-types.md` updated.

**Left:** the dropdown filtering, Replace button, option warning and stale-option rendering are UI-only and untested in a browser (no component tests, by decision). The text-to-choice conversion is deferred to WI-21. The "Replace" copy has not been reviewed against the design guidelines' wording.

**Files touched:** frontend `field-types/kind-changes.ts`, `choice/stale-choice.ts`, `schema-type-context.ts` (new), `field-usage.ts`, `schema-types.ts`, `field-types/registry.ts`, `group/group.ts`, `components/schema-editor.svelte`, `group/GroupExtras.svelte`, `choice/ChoiceExtras.svelte`, `choice/ChoiceInput.svelte`; backend ports, four repository adapters, two `Count*AttributeUsage` use cases, two routers; tests `kind-changes.test.ts` (new) plus backend test additions; docs.

**Checks run:** `poe lint-backend` and `poe typecheck-backend` clean; `poe test-backend` 531 pass; `poe coverage` all targets met (application 100%); `poe lint-frontend` pass; `poe typecheck-frontend` 0 errors (2 existing warnings); `poe test-frontend` 162 pass.

**Next session must know:** the schema editor now sets `SCHEMA_TYPE_CONTEXT` (type id and kind) for field extras that need usage counts. WI-11 (display options) should add per-kind `display` choices and read `meta.display`; `changeKind` already clears it when the kind changes.

## WI-11 session notes

**Status:** implemented, frontend checks green, committed as 2668afd. Next item: WI-15 (text constraints). WI-12 (rank matching) is optional and largely redundant since WI-14 made `kind` explicit; skip unless wanted.

**Done**
- `FieldTypeDescriptor.displayOptions` (`{ key, label, choices, default }`); the schema editor renders a "Show as" style dropdown per option from it. `display` is stored in `x-menagerist.display` (default = unset); other keys are editor state in `EditorField.config` mapped to validation keywords by the descriptor. Helpers in `field-types/display-options.ts`; `changeKind` also clears `config`.
- Boolean: Switch (new default, per the design guidelines) / Checkbox / Yes/No buttons (clearable to "not recorded"). Choice: Dropdown / Radio buttons / Chips (both with the "(no longer an option)" handling). Rating: 3, 5 or 10 stars, stored as `maximum`.
- `rowsToAttributes` omits a top-level boolean whose value is `''` (the cleared Yes/No state); group cells still treat `''` as `false`.
- Tests: `display-options.test.ts` (new) plus a boolean case in `attributes-editor.test.ts`. `docs/DECISIONS.md` and `docs/field-types.md` updated.

**Left:** group sub-fields have no "Show as" control (they render with defaults). Not tried in a browser (no component tests, by decision). The boolean default changed from checkbox to switch, so existing boolean fields look different until set to Checkbox.

**Files touched:** frontend `field-types/registry.ts`, `display-options.ts` (new), `kind-changes.ts`, `boolean/{boolean.ts,BooleanInput,BooleanView}`, `choice/{choice.ts,ChoiceInput}`, `rating/rating.ts`, `schema-types.ts`, `components/schema-editor.svelte`, `components/attributes-editor.svelte`; tests and docs as above. No backend changes.

**Checks run:** `poe lint-frontend` pass; `poe typecheck-frontend` 0 errors (2 existing warnings); `poe test-frontend` 174 tests pass. Backend unchanged, backend checks not run.

**Next session must know:** WI-15 also touches `rowsToAttributes` (an empty optional text with a pattern must be omitted) and adds backend schema-shape checks; keep it in the shared `check_meta_shape` helper.

## WI-15 session notes

**Status:** implemented, all backend and frontend checks green, committed as 26fdaca. Next item: WI-16 (highlighted fields). WI-12 stays optional.

**Done**
- Backend: `validate_attributes` errors now carry `keyword` and `value` next to `path` and `message` (`InvalidAttributesError.validation_errors` is `list[dict[str, Any]]`; the problem response passes them through). No new port, use case or endpoint. `check_schema` already rejects uncompilable patterns (also inside `allOf`) in all four type handlers; locked with tests.
- Frontend: `field-types/text/constraints.ts` (escape, unescape, `constraintKeywords`, `parseConstraints`, `describePattern`, `describeConstraints`, `readTextConfig`). Text descriptor writes one `pattern` or an `allOf` of two, reads back only those forms, and keeps anything else as `config.custom` (inputs disabled, note shown). New `formatError(keyword, value)` hook on `FieldTypeDescriptor`.
- `EditorSubField.config` added, so text sub-fields in a table carry constraints and `group.ts` passes `config` both ways (this also lets a rating sub-field keep its star count).
- `safe-validator.ts` (`createSafeValidator`: a pattern JavaScript rejects makes it skip pattern rules and set `degraded`) and `validation-messages.ts` (`friendlyClientError`, `friendlyServerError`, `serverErrorsToFields`, `topLevelKey`).
- UI (via svelte-file-editor): `TextExtras.svelte` and `ConstraintInputs.svelte` ("Validation (optional)" with "Starts with" and "Ends with"), the same inputs under text sub-fields in `GroupExtras.svelte`, helper text under a constrained field, client errors shown only after blur, a note when rules could not be checked, and both collection pages map server errors with `serverErrorsToFields`. An error inside a table row is now shown on the table (before it never matched a field).
- `rowsToAttributes` omits an empty text value that has a `pattern` or `allOf` (top level and group cells).
- Shared fixture `contract/fixtures/regex-conformance.json` read by pytest and vitest (answers open question 14 for regex cases).
- Docs: `docs/DECISIONS.md`, `docs/field-types.md` ("Text constraints").

**Left / deferred**
- The WI-10 style warning ("N items would fail the new constraint") is not built: it needs a query that evaluates a pattern over stored values in Python or Postgres. Stale values never block other edits (WI-7).
- The schema editor does not compile a pattern with `new RegExp` before saving: users only type literals, and the only way to get a bad pattern is the API (handled by the safe validator and by the backend `check_schema`).
- Not tried in a browser (no component tests, by decision): the "Validation (optional)" section, helper text, blur-only errors, and the table-row error placement.
- Switching a text field to long text drops its constraints (`changeKind` clears `config`).
- Integration test for JSONB round trip of patterns added (`test_node_type_repository.py`); the API-level smoke (I-5) is covered by the router-free use-case tests only.

**Files touched:** backend `domain/errors.py`, `application/_validate_attributes.py`; tests `test_text_constraints.py`, `adapters/persistence/test_node_type_repository.py` (new). Frontend `field-types/text/{text.ts,constraints.ts,TextExtras.svelte,ConstraintInputs.svelte}`, `field-types/registry.ts`, `field-types/group/{group.ts,GroupExtras.svelte}`, `schema-types.ts`, `safe-validator.ts`, `validation-messages.ts`, `components/attributes-editor.svelte`, `routes/collection/new/+page.svelte`, `routes/collection/[id]/+page.svelte`; test `text-constraints.test.ts`. `contract/fixtures/regex-conformance.json`; docs as above.

**Checks run:** `poe lint-backend` pass; `poe typecheck-backend` clean; `poe coverage` all targets met (domain, application and shared kernel 100%, adapters 87%, platform 82%, 30 integration tests pass); `poe lint-frontend` pass; `poe typecheck-frontend` 0 errors (2 existing img-alt warnings); `poe test-frontend` 205 tests in 17 files pass.

**Also changed:** `tests/schema-meta.test.ts` "single accessor" guard compared `path.relative` output (backslashes on Windows) with forward-slash names and failed on Windows; it now normalises the separator.

**Next session must know**
- Errors from the API are untyped in the OpenAPI schema (`errors` is a free-form list), so no client regeneration was needed.
- A backslash written through some shell heredocs is halved; write patterns and JSON with the file tools.
- `readTextConfig` lives in `constraints.ts` (not `text.ts`) to avoid an import cycle with the Svelte components.

## WI-16 session notes

**Status:** implemented, all backend and frontend checks green, committed as 44c01dc. Next item: WI-17 (attribute search). WI-12 stays optional.

**Done**
- Storage: `x-menagerist.highlights.card` (ordered `{key}` list, max 3). `schema-meta.ts` gained `readHighlights` and `withHighlights` (other highlight lists such as `connection` are kept; an empty list removes `highlights`).
- `lib/highlights.ts`: `MAX_HIGHLIGHTS`, `SURFACE_LIMITS` (grid 2, list 3, picker 1, row 2), `normaliseHighlights`, `highlightRanks`, `toggledRanks` / `movedRanks` / `canHighlightMore`, `summaryItems` (empty values skipped, limit applied).
- Descriptors: `highlightable`, `formatSummary` and `SummaryWidget` added to `FieldTypeDescriptor`. Text, number, boolean, date, choice and rating are highlightable; long text, table and custom are not. New `RatingSummary`, `ChoiceSummary`, `BooleanSummary`; date uses `formatSummary` (short date).
- `node-summary.svelte` (one renderer) is used by the grid card, list card, connection picker (first value) and connection rows (two values).
- Schema editor: opt-in `highlights` prop (passed by `settings/categories` only), a "Show on card" pin per eligible field, limit hint, "Shown on cards" list with move earlier/later. Ranks live on `EditorField.highlight`; `itemsToSchema` writes the list through `normaliseHighlights`; archiving or switching to a non-highlightable kind drops the field.
- Backend: `check_meta_shape` validates `highlights.card` shape only (list, at most 3, `{key}` entries, unique, existing and non-archived properties); create/update handlers reject a bad list. No API change, no client regeneration.
- Tests: backend `test_schema_meta.py` and `test_create_node_type.py`; frontend `highlights.test.ts`. The example fixture now carries `highlights`. Docs: `docs/DECISIONS.md`, `docs/field-types.md`, `frontend/DESIGN_GUIDELINES.md` section 7.

**Left / deferred**
- Live card preview in the editor (open question 62).
- Not tried in a browser (no component tests, by decision): the pin toggles and reorder list, the cards, the picker and the connection rows. The picker shows name, then the value, then the type label, with no separator.
- Group sub-fields cannot be highlighted. Relationship types have no highlight UI (WI-22).
- A field switched to a non-highlightable kind is dropped from the list silently.

**Files touched:** backend `application/schema_meta.py`; tests `test_schema_meta.py`, `test_create_node_type.py`. Frontend `lib/highlights.ts` (new), `schema-meta.ts`, `schema-types.ts`, `field-archive.ts`, `field-types/registry.ts`, `field-types/{boolean,choice,date,number,rating,text}/*.ts`, `field-types/{boolean/BooleanSummary,choice/ChoiceSummary,rating/RatingSummary}.svelte` (new), `components/node-summary.svelte` (new), `components/schema-editor.svelte`, `routes/collection/+page.svelte`, `routes/collection/[id]/+page.svelte`, `routes/settings/categories/+page.svelte`; test `highlights.test.ts` (new). Docs and `example-node-type-schema.json` as above.

**Checks run:** `poe lint-backend` and `poe typecheck-backend` clean; `poe test-backend` 563 pass; `poe coverage` all targets met (application 100%); `poe lint-frontend` pass; `poe typecheck-frontend` 0 errors (2 existing img-alt warnings); `poe test-frontend` 227 tests in 18 files pass.

**Next session must know**
- The subagent twice reported edits done that were not on disk in WI-15; this session it re-read files, but still verify with lint, typecheck and a grep.
- Heredocs in this shell halve backslashes; use the file tools for patterns.
- The stray staged `frontend/src/lib/field-types/BooleanView.svelte` (index only, not on disk) is still in `git status`.

## WI-17 session notes

**Status:** implemented, all backend and frontend checks green, committed as 06b605b. Next item: WI-18 (per-item custom fields; 18a first). WI-12 stays optional.

**Done**
- Backend: `q` on the item list also matches every string and number inside `attributes` (group cells and undefined keys included; never key names, booleans or nulls). `search_excluded_keys(schema)` in `schema_meta.py` (archived, `search: false`, `NON_SEARCHABLE_KINDS = {rating}`). `NodeRepository.list` and `count` take `attribute_search_exclusions` (type slug to keys); SQLAlchemy adapter uses `jsonb_path_query` (`column_valued`) with one clause per type that has exclusions plus an unrestricted clause for other types and untyped items; in-memory adapter walks values with the same rules. `ListNodes` loads all item types (pages of 100) only when `q` is set.
- Fixed the LIKE wildcard bug: `%`, `_` and backslash in `q` are escaped (name and description too).
- OpenAPI description added to `q`; client regenerated (generated code is gitignored).
- Frontend: descriptor `searchable?: boolean` (false for boolean and rating); `lib/search-context.ts` `matchContext`; the list and grid cards show "Matched in Director: Ridley Scott" while searching when the name and description did not match.
- Tests: `test_attribute_search.py` (11 unit), five `@pytest.mark.integration` tests in `test_node_repository.py` (values, exclusions per type, name and description, LIKE wildcards and backslash, deleted nodes; `count` checked against `list` in every case), `search-context.test.ts` (7). Docs: `docs/DECISIONS.md`, `docs/field-types.md`, `frontend/DESIGN_GUIDELINES.md` section 8. Open questions 20 to 22 closed by default; 63 and 64 added.
- Added a "Defaults taken without owner confirmation (for re-review)" table to `decisions.md` listing every default taken so far, plus open questions 63 to 65.

**Left / deferred**
- No editor control for `x-menagerist.search: false` (open question 63). Tags are not searched. Results are id-ordered, not by relevance.
- Scan speed on thousands of items not measured (the spec says measure before deciding); a `search_text` column with `pg_trgm` can replace the scan without changing the port.
- The non-searchable kind list is duplicated (`NON_SEARCHABLE_KINDS` backend, `searchable: false` frontend); keep in step when adding a kind.
- The "Matched in" line has not been tried in a browser (no component tests, by decision). A match inside a table shows the table's title and the cell text only.
- No API-level (router) test for the search; the use case and repository levels are covered.

**Files touched:** backend `application/schema_meta.py`, `application/list_nodes.py`, `ports/node_repository.py`, `adapters/persistence/node_repository.py`, `adapters/persistence/in_memory_node_repository.py`, `adapters/api/node/router.py`; tests `application/test_attribute_search.py` (new), `adapters/persistence/test_node_repository.py`. Frontend `lib/search-context.ts` (new), `field-types/registry.ts`, `field-types/{boolean,rating}/*.ts`, `routes/collection/+page.svelte`; test `search-context.test.ts` (new). Docs as above, `00-INDEX.md`, `decisions.md`, `open-questions.md`.

**Checks run:** `poe lint-backend` and `poe typecheck-backend` clean; `poe coverage` all targets met (application 100%, adapters 88%, integration tests included); `poe lint-frontend` pass; `poe typecheck-frontend` 0 errors (2 existing img-alt warnings); `poe test-frontend` 234 tests in 19 files pass.

**Next session must know**
- Shell heredocs halve backslashes; the LIKE escape character is written with the file tools and the integration test builds the backslash with `chr(92)`.
- The `svelte-file-editor` agent is unreliable on tab-indented edits; verify with a grep and the checks.
- The stray staged `frontend/src/lib/field-types/BooleanView.svelte` (index only) is still in `git status`.

## WI-18a session notes

**Status:** 18a implemented, all backend and frontend checks green, committed as d9dbdc6. 18b (promote a detail) and 18c (adopt across items, tips strip) are not started: they build on WI-19d (the node schema overlay), which replaces this stopgap for new typed per-item fields. Next in the table: WI-19 (presets) and WI-19d; read `wi-19-presets.md` and `wi-19d-per-item-schema-overlay.md` first. WI-12 stays optional.

**Done**
- Backend: new `application/custom_details.py` (`check_custom_details`, `MAX_CUSTOM_NAME_LENGTH` 100, `MAX_CUSTOM_DETAILS` 50) called from `CreateNode` and `UpdateNode`. It applies only to keys the type's schema does not define (archived ones count as defined), only to names that are new compared with the stored attributes, and the count only when it grows past the limit. Errors are `InvalidAttributesError` with keyword `customDetail`. This lives in the application layer, not in `Node` (the domain cannot see the schema, and its invariants run when nodes load from the database).
- Frontend: the row functions moved from the editor's `<script module>` to `lib/attribute-rows.ts` (`attributesToRows`, `rowsToAttributes`, `newDetailRow`, `AttributeRow` with `kind`, `raw`, `extra`). Rows are ordered by name (case-insensitive); numbers and yes/no values keep their type; null, nested values and lists keep their original in `raw` and are written back unchanged; names are trimmed. `lib/custom-details.ts` has `customDetailProblems`, `isDetailRow`, `canAddDetail`, `displayDetailValue` and the limits.
- UI: "Add detail" rows have a type choice (Text, Number, Yes/No) for new rows, matching value inputs, read-only JSON for uneditable values, inline errors, a limit hint, and Save disabled on both item forms while a detail-name problem exists. Read mode shows typed values. The editor's `<script module>` and its re-exports are gone (eslint `no-import-assign` rejects re-exporting names the instance script also imports): import the row helpers from `$lib/attribute-rows`.
- Tests: `test_custom_details.py` (13), `custom-details.test.ts` (20); `attributes-editor.test.ts` expectations updated for the new row shape and ordering. Docs: `docs/DECISIONS.md`, `docs/field-types.md`, `frontend/DESIGN_GUIDELINES.md` 16b. Open question 24 closed by default; 66 added; three rows added to the re-review table in `decisions.md`.

**Left / deferred**
- 18b and 18c (see above). No highlighting or typing beyond Text, Number and Yes/No until the overlay.
- Not tried in a browser (no component tests, by decision): the detail rows, type select, inline errors, disabled Save, and read mode.
- Names containing a slash cannot be addressed by the per-field server error mapping. A duplicate name with different case is only detected on the client.
- Edge types have no custom details.

**Files touched:** backend `application/custom_details.py` (new), `create_node.py`, `update_node.py`; tests `test_custom_details.py` (new). Frontend `lib/attribute-rows.ts` and `lib/custom-details.ts` (new), `components/attributes-editor.svelte`, `routes/collection/new/+page.svelte`, `routes/collection/[id]/+page.svelte`; tests `custom-details.test.ts` (new), `attributes-editor.test.ts`, `text-constraints.test.ts` (import path). Docs as above.

**Checks run:** `poe lint-backend` and `poe typecheck-backend` clean; `poe coverage` all targets met (application 100%); `poe lint-frontend` pass; `poe typecheck-frontend` 0 errors (2 existing img-alt warnings); `poe test-frontend` 254 tests in 20 files pass.

**Next session must know**
- Import `attributesToRows`, `rowsToAttributes` and `AttributeRow` from `$lib/attribute-rows`, not from the editor.
- The `svelte-file-editor` agent needed three rounds this session (silent misses, a re-export lint rule, a use-before-declaration); always verify with lint and typecheck.
- Heredocs in this shell halve backslashes.
- The stray staged `frontend/src/lib/field-types/BooleanView.svelte` (index only) is still in `git status`.

## WI-22a session notes

**Status:** 22a implemented, all backend and frontend checks green, committed as 66417f1. 22b (add several connections at once, optional `CreateEdges`) is not started. Remaining table items: WI-19 (presets), WI-19d (overlay), then 18b/18c, WI-21, WI-13. WI-12 stays optional.

**Done**
- `highlights.connection` list (max 2) on relationship types. Shared code generalised: `readHighlights` / `withHighlights` take a `HighlightList` (`'card' | 'connection'`); `normaliseHighlights`, `highlightRanks`, `toggledRanks`, `canHighlightMore` take a max (`maxHighlights(list)`); `summaryItems(..., 'connection')` reads the connection list; `Surface` gained `'connection'`. Backend `check_meta_shape` validates both lists (card max 3, connection max 2, same rules); a non-list `connection` is now rejected.
- Relationship type editor: `settings/relationships` passes `highlights highlightList="connection"`; the schema editor takes `highlightList` (texts "Show on connection", "Shown on connections"); `schemaToItems` and `itemsToSchema` take a trailing list argument.
- Item page: connection rows show the relationship label, the other item with its card highlights, and the connection's highlighted details (`node-summary`, `surface="connection"`). An "Edit connection" button opens a bits-ui dialog reusing `attributes-editor` over the relationship type's schema; Save uses `updateEdge` (the existing interceptor sends the ETag), maps server errors onto fields, shows the edit-conflict toast on 412, and is disabled while a detail-name problem exists. Removal is immediate with a 5-second Undo that re-creates the connection (new id, appended at the end); the inline confirmation is gone.
- Tests: connection cases in `highlights.test.ts` (list read/write, max 2, summary, editor round trip), backend shape tests. Docs: `docs/DECISIONS.md`, `docs/field-types.md`, `frontend/DESIGN_GUIDELINES.md` section 17, open question 51 closed by default, one row added to the re-review table.

**Left / deferred**
- 22b (multi-select add, duplicate skipping, optional `CreateEdges`). The add-connection form still has no details section and still says "Relationship" (follow-up 4).
- Not tried in a browser (no component tests, by decision): the pins on the relationship editor, the three-line rows, the edit dialog, the Undo.
- The dialog's muted line uses the loaded items (500) to name the other item; nothing is shown if it was not loaded. Undo changes the connection's id and list position. Item pages still do not show connection details for items with no relationship-type schema.

**Files touched:** backend `application/schema_meta.py`; test `test_schema_meta.py`. Frontend `lib/schema-meta.ts`, `lib/highlights.ts`, `components/schema-editor.svelte`, `routes/collection/[id]/+page.svelte`, `routes/settings/relationships/+page.svelte`; test `highlights.test.ts`. Docs as above.

**Checks run:** `poe lint-backend` and `poe typecheck-backend` clean; `poe coverage` all targets met; `poe lint-frontend` pass; `poe typecheck-frontend` 0 errors (2 existing warnings); `poe test-frontend` 259 tests pass.

**Next session must know**
- Use `write` tools or script files for anything with backslashes or nested quotes: shell heredocs break on both.
- Verify subagent edits with lint, typecheck and a grep.
- The stray staged `frontend/src/lib/field-types/BooleanView.svelte` (index only) is still in `git status`.

## WI-19d session notes

**Status:** implemented, all backend and frontend checks green, committed as e1a17b8. Next item: WI-19 (presets), then WI-18b/18c (their UI builds on this overlay), WI-21, WI-22b, WI-13. WI-12 stays optional.

**Scope decision:** `wi-19d-per-item-schema-overlay.md` is light on implementation detail, but `backend-surface.md` is explicit: "WI-19d (overlay, decided) adds a column and API fields, not a port." This session delivered that backend plumbing only — a nullable `extra_schema` on nodes, merged validation, and the API surface. It does **not** add an item-page editor for adding per-item typed fields; that is WI-18b/18c's UI, now unblocked.

**Done**
- Migration `d4e5f6a7b8c9` adds nullable `extra_schema` JSONB to `nodes` (v1: nodes only, not edges), applied via `poe db-up`.
- `Node` domain entity, `NodeModel`, both node repository adapters (SQLAlchemy and in-memory) gain `extra_schema`. `extra_schema=None` on update means "leave unchanged", matching `attributes_schema` on a node type.
- New `application/schema_meta.merge_attribute_schemas(type_schema, extra_schema)`: combines properties from both (raises `InvalidSchemaError` on a shared key, including one only archived on the type), concatenates `required` and `layout` (type first), leaves `highlights` type-only.
- New `application/schema_meta.check_schema_definition(schema)`: the jsonschema-validity + `check_meta_shape` pair already duplicated across the four node-type/edge-type use cases, now shared. `CreateNode`/`UpdateNode` call it on a given `extra_schema`, then validate `attributes` and custom-detail limits against the merged schema.
- API: `CreateNodeRequest`, `UpdateNodeRequest`, `NodeResponse` gain `extra_schema`. Client regenerated (`poe generate-frontend-client`); no frontend source changed, but typecheck/lint/tests re-run clean against the new generated types.
- Tests: domain (`test_node.py`), `schema_meta` (`merge_attribute_schemas`, `check_schema_definition`), `CreateNode`/`UpdateNode` (validation against the overlay alone, merged with a type schema, the key-collision rejection, "None keeps the stored overlay"), SQLAlchemy round-trip (`@pytest.mark.integration`, including a changed-and-saved case), router tests (create/update round-trip, malformed schema, 400 not 422 — `ValidationError` subclasses map to 400 in `problem_response.py`).
- Docs: `docs/DECISIONS.md`, `docs/field-types.md`.

**Left / deferred**
- No UI to create or edit `extra_schema`; only reachable via the API. WI-18b/18c build that.
- WI-17 attribute search does not exclude non-searchable overlay fields (e.g. a per-item rating) the way it does for type fields — exclusions are computed per type in `ListNodes`, not per node. Left for later; not a regression (an overlay rating is searched as text today, same as any custom detail was).
- Edges have no overlay (v1 scope, per spec).
- Not tried against a running frontend (no UI touches this yet).

**Files touched:** backend `domain/node.py`, `adapters/persistence/models.py`, `adapters/persistence/node_repository.py`, `adapters/persistence/in_memory_node_repository.py` (no code change needed, generic), `application/schema_meta.py`, `application/create_node.py`, `application/update_node.py`, `adapters/api/node/schemas.py`, new migration `d4e5f6a7b8c9_add_extra_schema_to_nodes.py`; tests `test_node.py`, `test_schema_meta.py`, `test_create_node.py`, `test_update_node.py`, `test_node_repository.py`, `test_node_router.py`. Frontend: only the generated API client. Docs as above.

**Checks run:** `poe lint-backend` and `poe typecheck-backend` clean; `poe test-backend` 614 pass; `poe coverage` (with `poe db-up` running Postgres and the new migration) 38 integration tests pass, all targets met (application 100%); `poe lint-frontend`, `poe typecheck-frontend` (0 errors, 2 existing warnings) and `poe test-frontend` (259 pass) all clean after the client regeneration.

**Next session must know**
- `merge_attribute_schemas` and `check_schema_definition` are the two functions WI-18b/18c and WI-19 (if it ever touches nodes directly) should reuse rather than re-deriving overlay logic.
- `ValidationError` subclasses (`InvalidSchemaError`, `InvalidAttributesError`) map to HTTP 400, not 422 — a couple of my first test assertions guessed 422 and had to be fixed.
- The migration chain head is now `d4e5f6a7b8c9`; `poe db-up` (which runs the `migrate` compose service) applied it cleanly in this session.
- `Node.update`/`Node.create` and both `Create/UpdateNodeCommand`s take `extra_schema` as an additional keyword-only field with a default, so no existing call site needed changes.

## WI-19a session notes

**Status:** implemented, all backend and frontend checks green, not committed. Next item: WI-19b (field groups, ad hoc per-item apply, copy details between items) or WI-19c (packs/import-export/built-ins), or WI-21/WI-22b/WI-13. WI-12 stays optional.

**Scope decision:** the spec splits presets into 19a (core: save/apply a field or a list, management page), 19b (field groups, ad hoc per-item application, copy-details-between-items) and 19c (packs, import/export, built-ins). This session delivered 19a only.

**Done**
- New backend module `presets` (own hexagonal layers, no dependency on `graph`, mirrors the `media` module's shape): domain `Preset` (kind/label/description/definition/version/builtin, soft-deletable; built-in presets reject edit/delete with `BuiltinPresetError`, 409), `ports/preset_repository.py`, SQLAlchemy + in-memory adapters, five use cases (`Create/Get/List/Update/DeletePreset`), router at `/preset` (POST, GET, GET/{id}, PATCH/{id} conditional, DELETE/{id}), registered in `entrypoints/api/__init__.py` and `alembic/env.py`. Migration `e5f6a7b8c9d0` creates the `presets` table (head is now `e5f6a7b8c9d0`, after WI-19d's `d4e5f6a7b8c9`).
- `application/preset_definitions.check_definition(kind, definition)`: structural shape check per kind (`field` needs a typed `property`; `field_set` needs a `section` and typed `properties`; `choice_list` needs non-blank `options`). Storage/validation supports all three kinds even though only `field` and `choice_list` have UI this session.
- Frontend: `$lib/presets.ts` (`fieldToDefinition`, `optionsToDefinition`, `definitionToField`, `listUpdateAvailable`, types). New `schema-meta.ts` accessor `replacePropMeta` (wholesale replace, not merge) so `fieldToDefinition` can drop `archived`/`origin` without touching `x-menagerist` outside the accessor file (the "only the accessor reads x-*" test caught the first attempt).
- Schema editor: "Save field for reuse" (any non-opaque field, saved or pending) and "Add from saved fields…" (inserts a pending field with fresh `origin`). `group` kind's UI label is now "Table" (code name unchanged), freeing "Field group" for WI-19b.
- `ChoiceExtras`: "Save these options as a list", "Use a saved list" (sets `origin`), and for a field with `origin`, an advisory fetch of the linked preset plus "Update available" / "Update options" (reuses the WI-9/10 in-use warning per removed option before replacing).
- New Settings page `settings/saved-fields` (Fields and Lists sections, list + delete with the 5-second Undo pattern; a "Field groups aren't available yet" placeholder) and a nav tile on `settings/+page.svelte`.
- Tests: domain, `preset_definitions`, all five use cases, in-memory repository, SQLAlchemy repository (`@pytest.mark.integration`), router — 53 new backend tests. Frontend: `presets.test.ts` for the conversion helpers. `docs/DECISIONS.md` and `docs/field-types.md` updated.

**Left / deferred (19b, 19c)**
- Field groups: no save/apply UI (the `field_set` kind is stored and validated but unreachable from the editor).
- No ad hoc per-item application (needs the WI-19d overlay's own editor, which doesn't exist yet either) and no "copy details from another item".
- No packs, import/export or built-in presets.
- "Save for reuse" from a custom detail (loose, per-item key) is not wired; only schema-editor fields and choice options are.
- Not tried in a browser (no component tests, by decision): the two dialogs, the schema-editor buttons, the "Update options" flow, the Settings page.
- The generated `PresetResponse.kind`/`.definition` types are looser (`string`/`Record<string, unknown>`) than the frontend's `PresetKind`/`FieldDefinition` types; call sites cast with `as unknown as X` at the API boundary rather than adding a runtime check, matching how other generated-client boundaries in this codebase are handled.

**Files touched:** backend `modules/presets/**` (new), `alembic/env.py`, `alembic/versions/e5f6a7b8c9d0_create_presets_table.py` (new), `entrypoints/api/__init__.py`; tests `tests/modules/presets/**` (new). Frontend `field-types/group/group.ts`, `schema-meta.ts`, `presets.ts` (new), `components/schema-editor.svelte`, `field-types/choice/ChoiceExtras.svelte`, `components/save-preset-dialog.svelte` (new), `components/preset-picker-dialog.svelte` (new), `routes/settings/+page.svelte`, `routes/settings/saved-fields/+page.svelte` (new); tests `presets.test.ts` (new). Docs as above.

**Checks run:** `poe lint-backend` and `poe typecheck-backend` clean; `poe test-backend` 667 pass; `poe coverage` (Postgres via `poe db-up`, both new migrations applied) 46 integration tests pass, all targets met (application 100%); `poe lint-frontend` pass; `poe typecheck-frontend` 0 errors (2 existing warnings); `poe test-frontend` 266 pass.

**Next session must know**
- Migration head is `e5f6a7b8c9d0`; `poe db-up` applied both `d4e5f6a7b8c9` (WI-19d) and `e5f6a7b8c9d0` (WI-19a) this session.
- `origin` is stored as an arbitrary member of `PropertyMeta`'s index signature in `schema-meta.ts` — no dedicated type was added there; `$lib/presets.ts` defines its own `Origin` type for it.
- `check_definition`'s `field_set` shape check exists and is tested, ready for WI-19b to use when it builds the save/apply UI.

## WI-22b session notes

**Status:** implemented, all backend and frontend checks green, not committed. Next: WI-19b/19c, WI-21, or WI-13.

**Done**
- Backend: `CreateEdgesCommand`/`CreateEdges` (new `application/create_edges.py`) connects one source to several targets of one relationship type in a single transaction, sharing attributes; a target already connected (either direction) is skipped via the existing `list_for_node` paging (mirrors the purge use cases' pattern). Route `POST /edge/batch` (`CreateEdgesRequest`/`CreateEdgesResponse` in `edge/schemas.py`), registered before `/edge/{edge_id}` so it isn't shadowed. No migration (no schema change).
- Frontend: the item page's "Connect item" form is now multi-select (`selectedTargets`, removable chips); a details form (`AttributesEditor`) appears when the chosen relationship type has fields and applies to every connection created. Submit calls the batch endpoint; success shows "N item(s) connected" (plus a skipped count if any) with a 5-second Undo that deletes the created edges individually (best-effort, no batch delete exists).
- Tests: 10 new backend tests (use case incl. dedupe in both directions, missing source/target, schema validation, auto-create type; router). `docs/DECISIONS.md` updated.

**Left / deferred:** creating a new item inline from the picker (typing a name that matches nothing) is not implemented — only existing items can be selected, per the spec's own note that this could be split out. Not tried in a browser.

**Files touched:** backend `application/create_edges.py` (new), `adapters/api/edge/{schemas.py,router.py}`, `adapters/api/dependencies.py`; tests `test_create_edges.py` (new), `test_edge_router.py`. Frontend `routes/collection/[id]/+page.svelte`. Docs as above.

**Checks run:** `poe lint-backend`/`typecheck-backend` clean; `poe test-backend` 677 pass; `poe coverage` all targets met (application 100%, 46 integration tests pass); `poe lint-frontend`/`typecheck-frontend` (0 errors, 2 existing warnings) clean; `poe test-frontend` 266 pass.

## WI-12 session notes

**Status:** implemented, all frontend checks green, committed as 92db277. Remaining table items: WI-19b/19c, WI-21, WI-13.

**Done**
- `FieldTypeDescriptor.rank?: (prop) => number` (registry.ts). `descriptorForProp`'s no-`kind` fallback now picks the highest-ranked matching descriptor (unranked defaults to 1), ties broken by registration order. The `x-menagerist.kind` direct-lookup path is unchanged.
- No built-in kind was given a non-default rank: checked each scalar's `fromSchema` and none currently overlap (confirmed in the DECISIONS entry), so this session only adds the mechanism, as the spec's own closing note anticipated ("worth doing only if more overlapping types are coming").
- Updated the `index.ts` ordering comment (order now only breaks ties) and the `field-types.md` matching description.
- Tests: 3 new cases in `registry.test.ts` (rank picks the winner regardless of registration order, ties fall back to order, rank 0 means no match). `docs/DECISIONS.md` updated.

**Left:** nothing planned; this stays dormant until a genuinely overlapping kind (multi-choice, partial date, identifier, URL/email) is added, which should set `rank` instead of relying on import order.

**Files touched:** frontend `field-types/registry.ts`, `field-types/index.ts`; tests `registry.test.ts`. Docs as above. No backend changes.

**Checks run:** `poe lint-frontend` pass; `poe typecheck-frontend` 0 errors (2 existing warnings); `poe test-frontend` 269 pass. Backend unchanged, backend checks not run.

## Required-field styling fix (open question 58)

**Status:** implemented, frontend checks green, not committed.

**Done:** `attributes-editor.svelte`'s required-field asterisk is now `text-muted-foreground` (was `text-destructive`), and becomes a "Recommended" text hint when the field is empty. Closes open question 58 (owner decided 2026-09-21, code hadn't caught up). Also closed open questions 7 (WI-12, answered by its own commit) and partly closed 52 (WI-22b's `CreateEdges` half).

**Checks run:** `poe lint-frontend` pass; `poe typecheck-frontend` 0 errors (2 existing warnings); `poe test-frontend` 269 pass (no new test added — this is a small visual/styling change, consistent with no component tests in this codebase by decision).

**Files touched:** frontend `components/attributes-editor.svelte`. Docs: `docs/DECISIONS.md`, this file, `open-questions.md` (58 closed, 7 closed, 52 partly closed).

## Table (group) column order fix

**Status:** implemented, all backend and frontend checks green, not committed.

**Bug (user-reported):** a `group`/"Table" field's column order was not preserved across a save and reload. Confirmed directly against Postgres: nested JSONB object keys are reordered on storage, the same issue WI-18a found for loose attribute keys — but `GroupInput.svelte`, `GroupView.svelte` and `group.ts`'s `fromSchema` all derived column order from raw `Object.entries(prop.items.properties)`, with no explicit order recorded (unlike top-level fields, which have `x-menagerist.layout`).

**Fix:** new `x-menagerist.columns` on the group property itself (an ordered array of sub-property keys), written by `toSchema` and read by a new shared helper `field-types/group/columns.ts`'s `orderedColumns(prop)`, used by `fromSchema` and both widgets. Falls back to `Object.entries` order when absent (old schemas, API-authored). Backend `check_meta_shape` validates `columns` is an array of strings.

**Files touched:** frontend `field-types/group/columns.ts` (new), `group.ts`, `GroupInput.svelte`, `GroupView.svelte`, `schema-meta.ts` (`PropertyMeta.columns` type); tests `group-columns.test.ts` (new), `field-types.test.ts` (fixture round-trip), `text-constraints.test.ts` (updated expectation). Backend `application/schema_meta.py` (`_check_property_meta_shape` extracted to keep complexity down); tests `test_schema_meta.py`. `docs/field-types-spec/example-node-type-schema.json` fixture updated with an explicit `columns` order. Docs: `DECISIONS.md`, `field-types.md`.

**Checks run:** `poe lint-frontend` pass; `poe typecheck-frontend` 0 errors (2 existing warnings); `poe test-frontend` 275 pass. `poe lint-backend`/`typecheck-backend` clean; `poe test-backend` 679 pass; `poe coverage` all targets met (application 100%, 46 integration tests pass).

**Left:** existing table fields saved before this fix keep JSONB-scrambled column order until the item type is re-saved from the schema editor (no migration, consistent with every other `x-menagerist` addition).

## WI-23/WI-24 session notes

**Status:** implemented, all frontend checks green, not committed. Next: WI-19b/19c, WI-21, WI-22b's inline-creation follow-up, or WI-13.

**WI-23 (column reordering) — done.** `GroupExtras.svelte` gained up/down (`ChevronUp`/`ChevronDown`) buttons per sub-field row, swapping entries in `field.subFields`; disabled at the ends. No backend or other file changes needed — `toSchema` already writes the resulting order into `x-menagerist.columns` (the earlier column-order fix), so reordering flows through to a save automatically.

**WI-24 (quantity kind) — done, scope reduced from the spec's draft.** New `quantity` kind (`{value: number, unit: string}`, e.g. "180 g"), matched only by an explicit `kind`. Its own prerequisite (shared with the candidate `location` kind) is done: `AttributeRow.value` widened to `string | GroupRow[] | GroupRow`; `attributesToRows` takes an optional `schema` so an object-shaped value under a schema-defined key hydrates as an editable flat row instead of read-only JSON; `rowsToAttributes` gained the write-back branch (a blank text sub-value like `unit` is kept, a blank number/date/enum sub-value is omitted, the whole field is omitted only when every raw sub-value was blank). **Scope reduction:** `canBeSubField: false` for v1 (the spec's draft said `true`) — a group cell is a plain string, not an object, so nesting a quantity inside a table needs a second, cell-level fix; deferred, noted in `wi-24-quantity-field-type.md`.
- Two widgets: `QuantityInput.svelte` (number + short text input side by side), `QuantityView.svelte` ("180 g" / "180" / "g" / "—").
- Three `attributesToRows` call sites in `collection/[id]/+page.svelte` now pass a schema. Two needed care: inside `load()`, the reactive `nodeSchema`/`nodeTypes` haven't updated within that synchronous block yet, so those two use `schemaOfType(node.type)` (which reads the `nodeTypes` state variable directly, already reassigned earlier in the same block) instead of the `nodeSchema` derived value; the edge-editing call site uses the existing `edgeTypeSchemaOf(edge)`, unaffected by that timing issue since it only runs from a later user-triggered handler.
- Contract fixture: added a "Weight" (`quantity`) property to `example-node-type-schema.json` (unplaced in the layout, so it appends at the end per `normalise()`'s rule — harmless, still valid).
- Tests: `quantity.test.ts` (new: `quantityText`, descriptor matching/round-trip, `formatSummary`, `canBeSubField: false`); composite-field cases added to `attributes-editor.test.ts` (`attributesToRows`/`rowsToAttributes` hydration, coercion, blank-handling, unknown-key fallback, end-to-end round trip). One test's own expectation was initially wrong (expected `unit: ''` to be dropped) and was corrected to match the intentional group-cell-style blank-text-is-kept behaviour, not the code.

**Left:** quantity as a group sub-field (needs cell-level object-value support — separate follow-up, noted in the spec). Not tried in a browser (no component tests, by decision).

**Files touched:** frontend `field-types/group/GroupExtras.svelte`; `field-types/quantity/{quantity.ts,format.ts,QuantityInput.svelte,QuantityView.svelte}` (new), `field-types/index.ts`, `schema-types.ts` (new `object` variant), `attribute-rows.ts`, `components/attributes-editor.svelte`, `routes/collection/[id]/+page.svelte`; tests `quantity.test.ts` (new), `attributes-editor.test.ts`. Docs: `DECISIONS.md`, `field-types.md`, `wi-24-quantity-field-type.md` (scope corrections), `example-node-type-schema.json`.

**Checks run:** `poe lint-frontend` pass; `poe typecheck-frontend` 0 errors (2 existing warnings); `poe test-frontend` 290 pass. Backend unchanged, backend checks not run.

**Next session must know:** two subagent runs for this item were interrupted mid-task by the weekly usage limit resetting; both had left partial-but-correct work (no corruption), picked up and finished directly rather than re-run from scratch. If a subagent report cuts off mid-sentence, check `git status`/`git diff` before assuming nothing happened.

## WI-18 (revised) session notes

**Status:** implemented, all backend and frontend checks green, not committed (done in an isolated worktree, `feature/per-item-overlay-fields`, per the user's explicit no-commit rule for this project — every change is staged with `git add` only). Next in the table: WI-19b/19c (field groups, ad hoc per-item apply, packs/import-export), WI-21, WI-13. WI-12 stays optional.

**Scope revision, mid-session (owner, 2026-09-22).** The original WI-18 spec's 18a (loose Text/Number/Yes-No custom details), and 18c (adopt-across-items, tips strip) are retired, not deferred — no backwards compatibility, no legacy data to migrate, since this is a pre-release application. Per-item extras are now typed fields in the node's `extra_schema` overlay (WI-19d), created with the same full Name + Kind flow schema fields use. Edges also lose ad-hoc fields entirely (owner decision: "just my app for now," no overlay-for-edges scope). See `wi-18-per-item-custom-fields.md`'s "Revised design" section (supersedes its own original 18a/18b/18c text) and `docs/DECISIONS.md`'s new entry for the full reasoning.

**Done**
- Backend: `application/extra_schema_limits.py` (new, replaces `custom_details.py`, deleted) — `check_extra_schema_limits`, `MAX_EXTRA_SCHEMA_FIELDS` 50, count-only (no label-length cap). Wired into `create_node.py`/`update_node.py`; fixed a real bug while wiring it — the old code only checked `extra_schema` limits when `attributes` also changed, so a pure "Add field" edit bypassed the check entirely; now checked whenever `extra_schema is not None`, independent of `attributes`.
- Backend: `application/promote_extra_schema_field.py` (new) — `PromoteExtraSchemaField`/`PromoteExtraSchemaFieldCommand(node_id, node_type_id, key)`. Composes `UpdateNodeType` + `UpdateNode` through `JoinedUnitOfWork`, one commit, following `media/application/upload_and_attach_media.py`'s exact pattern. Found and fixed a real bug during implementation: `UpdateNodeCommand.extra_schema=None` means "leave unchanged" (`Node.update()`'s own documented convention), so the initial draft's `None if not remaining else {...}` would have silently failed to clear a fully-promoted overlay, leaving the just-promoted key still defined there — `merge_attribute_schemas` would then reject it as a collision on the node's next load. Fixed by always constructing a real `{"properties": remaining}` dict, never `None`.
- Backend: router — `POST /node/{node_id}/attribute/{key}/promote`, `PromoteExtraSchemaFieldRequest`, DI provider, following the `purge_node_type_attribute` pattern exactly. Two new end-to-end router tests (`TestClient`, in-memory repos): success (value moved, type schema gains the property, overlay loses it) and 404 on a missing node.
- Frontend: `schema-editor-items.ts` (new) — `schemaToItems`/`itemsToSchema`/`schemaToArchived`/`isSection`/`EditorItem`/`EditorSection` extracted verbatim from `schema-editor.svelte`'s module script. Hit the exact `no-import-assign` ESLint pitfall this file's own WI-18a notes already documented (re-exporting a name from a component's module script while also importing it in the instance script) — resolved the same way: consumers (including `frontend/tests/highlights.test.ts` and `schema-editor-keys.test.ts`, which the initial grep for consumers missed because it only checked `frontend/src`, not `frontend/tests`) import directly from the new module, no re-export.
- Frontend: `field-kind-row.svelte` (new) — label/kind-select/display-options/required/kind-change-warning/`EditorExtras` extracted from `schema-editor.svelte`'s `fieldRow` snippet. Found and fixed a real behaviour-preservation bug during extraction: the original `handleKindChange` cleared a field's highlight rank when a kind change made it non-highlightable — `FieldKindRow`'s single shared `onFieldChange` callback would have silently dropped that. Fixed with a `handleFieldRowChange(field, next)` wrapper in `schema-editor.svelte` that only acts on an actual kind change, passed as the callback given to `FieldKindRow`.
- Frontend: `mergeAttributeSchemas` added to `schema-meta.ts` — TS mirror of the backend's function of the same name, 6 new tests in the existing `schema-meta.test.ts`.
- Frontend: `attributes-editor.svelte` rewritten — new `extraSchema`/`supportsExtraFields`/`nodeId`/`nodeTypeId`/`onPromoted` props; validation and value-conversion now run against `mergeAttributeSchemas(schema, extraSchema)`; overlay fields render through the existing `fieldEntry` snippet unchanged (same widgets as type fields); "Add field" (inline `FieldKindRow` draft, key via `generateFieldKey` against the union of both schemas' keys); remove-with-Undo; "Make this a field" calls `promoteExtraSchemaField`. All freeform "Additional details" machinery removed. Found and fixed a second real bug here too: `removeExtraField` originally set `extraSchema = null` when the last field was removed (matching `itemsToSchema`'s own "empty → null" behaviour) — exactly the `None`-means-unchanged trap `PromoteExtraSchemaField` had already been fixed for. Same fix applied: always write a real `{"properties": {}}` object, never `null`.
- Frontend: `attribute-rows.ts` trimmed (`newDetailRow`, `AttributeRow.extra` removed — confirmed via full-repo grep nothing else referenced them); `custom-details.ts` and its test (20 cases) deleted.
- Frontend: both route pages wired — `routes/collection/new/+page.svelte` (`extraSchema` state, merged-schema `rowsToAttributes`, `extra_schema` in the create body) and `routes/collection/[id]/+page.svelte` (`extraSchema` synced from `node.extra_schema` on load/cancel, merged-schema hydration and save body, edit-form wiring with `nodeId`/`nodeTypeId`/`onPromoted={load}`, view-mode `extraLayout` block reusing the existing `attrField` snippet). The edge (connection) `AttributesEditor` usages were deliberately left untouched, confirmed via diff.
- Docs: `docs/DECISIONS.md`, `docs/field-types.md`, `docs/field-types-spec/decisions.md`, `frontend/DESIGN_GUIDELINES.md` §16b.

**Left / deferred**
- No new component-level tests for `attributes-editor.svelte`'s add/remove/promote logic (no component-testing infrastructure in this repo, by decision; the file's existing tests only cover the plain `attributesToRows`/`rowsToAttributes` functions, unchanged).
- **Not tried in a running browser at all** — none of this session's UI changes (the `FieldKindRow` extraction's highlight-preserving fix, the new "Add field"/remove/promote flow, both route pages) have been manually exercised yet. This is a bigger gap than usual "no component tests, by decision" entries elsewhere in this file, because two of the fixes found during implementation (the highlight-clearing wrapper, the `extra_schema` null-vs-real-empty-object fix) are exactly the kind of thing that's easy to get subtly wrong and only a live check would catch with confidence. Do this before considering the feature done.
- Postgres integration test for `PromoteExtraSchemaField` (plan's Task 4 Step 5) was deliberately skipped — checked precedent first: even `upload_and_attach_media.py`, the exact `JoinedUnitOfWork` pattern this command is modelled on, has no Postgres-level integration test anywhere in the codebase; building one from scratch would mean inventing a new test pattern for the whole `graph` module (exposing a `session_factory` fixture, since the existing `db_session` fixture only yields a bound session). `pytest.mark.integration`/testcontainers infra exists and works if a future session wants this.
- `poe coverage` (the full gated coverage run) has not been run this session — only `poe test-backend`/targeted pytest runs and `poe lint-backend`/`poe typecheck-backend`. Run it before merging.
- Presets (WI-19b/c) may want to reuse `FieldKindRow`/`schema-editor-items.ts` too — not checked against this session's extraction, since WI-19 wasn't touched.

**Files touched:** backend `application/extra_schema_limits.py` (new, replaces deleted `custom_details.py`), `application/promote_extra_schema_field.py` (new), `application/create_node.py`, `application/update_node.py`, `adapters/api/node/{schemas.py,router.py}`, `adapters/api/dependencies.py`; tests `test_extra_schema_limits.py` (new), `test_promote_extra_schema_field.py` (new), `test_create_node.py`, `test_update_node.py`, `test_node_router.py` (deleted: `test_custom_details.py`). Frontend `lib/schema-editor-items.ts` (new), `lib/components/field-kind-row.svelte` (new), `lib/schema-meta.ts`, `lib/components/schema-editor.svelte`, `lib/components/attributes-editor.svelte`, `lib/attribute-rows.ts`, `routes/collection/new/+page.svelte`, `routes/collection/[id]/+page.svelte`; tests `schema-meta.test.ts`, `tests/highlights.test.ts`, `tests/schema-editor-keys.test.ts` (deleted: `custom-details.test.ts`). Docs as above.

**Checks run:** `poe lint-backend` clean; `poe typecheck-backend` (mypy --strict) 325 files, 0 errors; `uv run pytest` targeted runs for every touched backend file, all passing (backend architecture tests re-confirmed dependency direction still holds). `poe lint-frontend`/`npx eslint` on every touched file, clean; `poe typecheck-frontend` 97 files, 0 errors (2 pre-existing a11y warnings, unrelated); `poe test-frontend` 276/276 passing.

**Next session must know**
- This work happened in an isolated worktree at `.worktrees/per-item-overlay-fields` (branch `feature/per-item-overlay-fields`, off `feature/initial-implementation` @ 4aac623), because the user asked for Subagent-Driven Development, then asked to drop subagents entirely partway through (token efficiency) — the rest was done by the controller directly, self-reviewed, no subagent dispatch. Everything is staged (`git add`) but **not committed** — the user commits everything themselves, per an absolute project rule reaffirmed hard mid-session (a subagent got partway through a `git commit` before being killed; nothing landed, but staging-vs-committing needed an explicit user ruling afterward: `git add` is fine, `git commit` never is).
- Manually verify in a running app before calling this done (see "Left/deferred" above) — this is the one thing this session could not do for itself.
- If resuming: the worktree's ledger at `.superpowers/sdd/2026-09-22-per-item-overlay-fields/progress.md` has the full task-by-task record, including every ruling made (staging policy, the DB-touching-task scope reduction, the two `extra_schema=None` bug fixes) with reasoning — read it before assuming anything about what was or wasn't done.

## Quantity/choice sub-fields and group sub-key usage checks session notes

**Status:** implemented, all backend and frontend checks green, not committed.

**Done**
- Frontend: `quantity` and `choice` field-type descriptors are now `canBeSubField: true` (`field-types/quantity/quantity.ts`, `field-types/choice/choice.ts`). `attribute-rows.ts`'s `GroupRow` widened to `Record<string, string | Record<string, string>>`; new shared `coerceObjectValue`/`coerceGroupRow` helpers apply the existing "omit only when every sub-value is blank, keep a blank text sub-value" rule to both a top-level composite field and a composite table cell. `EditorSubField` gained `options?: string[]`; `group.ts`'s `toSchema`/`fromSchema` pass it through.
- `GroupView.svelte`: a `rating`/`quantity` column now renders through that kind's own `ViewWidget` (stars, "180 g"); every other kind is unchanged (deliberately not a fully generic descriptor dispatch, since `date`/`boolean` also have `ViewWidget`s that render in a different, longer style than this table wants).
- `GroupExtras.svelte`: a `choice` column gets its own inline options editor (add/remove chips, scoped to `EditorSubField.options`, no preset/saved-list machinery — that stays exclusive to top-level choice fields). Column removal now queries usage first (`{key: field.key, sub_key: sf.key}`) and, if any items/connections hold it, shows an inline confirm (`purgeWarning`) before removing instead of the previous silent immediate splice; a choice column's option removal stays advisory (remove immediately, warn after if in use, `optionRemovalWarning`) — the same two-tier split WI-9/WI-10 already established for top-level fields, now reachable for table columns too.
- Backend: `count_with_attribute`/`list_with_attribute` on both `NodeRepository`/`EdgeRepository` (ports, SQLAlchemy adapters via `jsonb_array_elements`+`table_valued`, in-memory adapters) take an optional `sub_key`; `Count/PurgeNodeTypeAttributeUsage`, `Count/PurgeEdgeTypeAttributeUsage` and their routes (`GET .../attribute/{key}/usage`, `DELETE .../attribute/{key}`, both node-type and edge-type) take the same `sub_key`. Purge with `sub_key` strips only that key from each row of the array (`_purged_attributes`), leaving the rest of the row and the array itself.
- Tests: in-memory + SQLAlchemy integration tests for `sub_key` matching (both repositories), use-case tests (count + purge, both node/edge), router tests (both node-type/edge-type), frontend unit tests for the new group-cell coercion (quantity in a table row, choice column) and the `role`-as-choice sub-field round trip in `field-types.test.ts`. Docs: this entry, `docs/DECISIONS.md`, `docs/field-types.md`, `wi-24-quantity-field-type.md`.

**Left / deferred**
- No new component tests (no component-testing infrastructure in this repo, by decision) — the `GroupExtras.svelte` column-removal confirm, choice-column options editor, and `GroupView.svelte`'s rating/quantity cell rendering have not been tried in a running browser.
- Presets (WI-19b/c "field groups") could eventually let a choice column reuse a saved options list the way a top-level choice field does; deliberately out of scope here per the owner's answer that presets stay exclusive to top-level fields for now.
- A saved `quantity`/`choice` sub-field's kind-change matrix (`kind-changes.ts`'s `ALLOWED`) has no entry for either kind, so both fall back to the generic "stay only itself" default — same as every other kind not explicitly listed; not a regression, just not extended in this session.

**Checks run:** `poe lint-backend`/`poe typecheck-backend` clean; `poe test-backend` (unit) 716 pass; integration tests (Postgres via `poe db-up`) pass, including the new `sub_key` cases; `poe coverage` all targets met (application 100%). `poe lint-frontend` (prettier + eslint) clean; `poe typecheck-frontend` 0 errors (2 pre-existing img-alt warnings); `npx vitest run` 273 pass across 21 files.

## WI-25 session notes

**Status:** implemented, all frontend checks green, not committed.

**Done**
- Fixed a user-reported bug first: `quantity`'s `quantityText` (`format.ts`) only accepted a JS `number`, but every read-mode caller feeds it a value already stringified by `attributesToRows` - so the numeric part silently vanished and only the unit showed. Now accepts a numeric string too. See `docs/DECISIONS.md`.
- New `list` kind: plain array of free-text strings, `display: numbered|bulleted` (cosmetic only), `canBeSubField: false`. Files: `field-types/list/{list.ts, ListInput.svelte, ListView.svelte}`. `schema-types.ts`'s array variant widened to allow `items: { type: 'string' }` (previously array properties could only be `group`'s `items: { type: 'object' }`); this needed matching narrowing-guard fixes in `field-types/group/columns.ts` (already had the fix from the earlier session) and `GroupInput.svelte` (`addRow`'s guard), plus explicit-shape assertions in three existing tests whose inline property literals lost their inferred union member once a second array shape existed (`field-types.test.ts`, `group-columns.test.ts`, `schema-editor-keys.test.ts`).
- New `checklist` kind, added mid-session on request: array of `{text, done}` with a real persisted boolean tick per item, not a `list` display variant. Files: `field-types/checklist/{checklist.ts, ChecklistInput.svelte, ChecklistView.svelte}`. `attribute-rows.ts` gained `ChecklistRow` and a schema-aware branch that must run *before* the existing generic array-of-objects (`isGroupValue`) fallback - both `attributesToRows` and `rowsToAttributes` check the schema's declared `checklist` kind first, otherwise a checklist's boolean `done` would silently degrade to `false` through the group cell coercion path (which only understands string-typed table cells). A regression test locks this in.
- `attribute-rows.ts` also gained a `list` branch in both directions: hydrate to `string[]` (no stringifying, unlike quantity's object value), write back dropping blank/whitespace-only items and omitting the key entirely when every item is blank.
- Docs: `docs/field-types.md` (two new table rows plus a "Ordered list and checklist" section), `docs/DECISIONS.md` (two entries: the field types, and the quantity bugfix), `docs/field-types-spec/further-field-types.md` (both candidate rows marked scheduled, "Ordered list kind" section's open questions resolved), `00-INDEX.md`, this file, new `wi-25-ordered-list-and-checklist-field-types.md`.
- Tests: `list.test.ts` (new), `checklist.test.ts` (new), `attributes-editor.test.ts` (list and checklist round-trip/blank-handling cases, plus the group/checklist disambiguation case), `quantity.test.ts` (the bugfix cases).

**Left / deferred**
- No third list style beyond numbered/bulleted (e.g. lettered) - owner explicitly deferred this.
- Neither kind is a group sub-field or highlightable.
- No live toggle of a checklist tick from the item's read-only view mode - only from the edit form, consistent with every other field in this codebase.
- No component tests (no component-testing infrastructure in this repo, by standing decision) - none of the four new widgets have been tried in a running browser yet.
- No backend changes were needed for either kind (no kind allowlist exists server-side; search already scans arrays generically and already excludes booleans).

**Files touched:** frontend `lib/field-types/list/{list.ts, ListInput.svelte, ListView.svelte}` (new), `lib/field-types/checklist/{checklist.ts, ChecklistInput.svelte, ChecklistView.svelte}` (new), `lib/field-types/quantity/format.ts`, `lib/field-types/index.ts`, `lib/field-types/group/{columns.ts, GroupInput.svelte}`, `lib/attribute-rows.ts`, `lib/schema-types.ts`; tests `list.test.ts` (new), `checklist.test.ts` (new), `attributes-editor.test.ts`, `quantity.test.ts`, `field-types.test.ts`, `group-columns.test.ts`, `schema-editor-keys.test.ts`. Docs as above.

**Checks run:** `poe lint-frontend` pass; `poe typecheck-frontend` 0 errors (2 pre-existing img-alt warnings); `npx vitest run` 294/294 pass across 23 files.

**Next session must know**
- Two svelte-file-editor subagent dispatches this session had the Svelte MCP server unavailable (`plugin:svelte:svelte` connection timeout) and fell back to plain Read/Edit/Write, verifying manually via `poe lint-frontend`/`poe typecheck-frontend`/`vitest run` instead of the usual autofixer tool. Worth checking whether that MCP server is reachable at the start of the next session.
- `attribute-rows.ts` now has three schema-aware branches that must stay ordered correctly relative to the generic `isGroupValue` catch-all: `checklist` and `list` are both checked before it. Adding a fourth array-shaped kind later should follow the same "check the declared kind first" pattern, not rely on shape alone.
