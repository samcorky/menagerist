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
| WI-9 purge and usage | done, awaiting user review and commit | feature/initial-implementation | See "WI-9 session notes" below. |
| WI-10 kind changes and option warnings | todo | | |
| WI-11 display options | todo | | |
| WI-12 rank matching (optional) | todo | | |
| WI-15 text constraints | todo | | |
| WI-16 highlighted fields | todo | | |
| WI-17 attribute search | todo | | |
| WI-18 per-item custom fields | todo | | |
| WI-19 presets | todo | | |
| WI-19d per-item schema overlay | todo | | |
| WI-21 value suggestions | todo | | |
| WI-22 connection details | todo | | |
| WI-13 drag-and-drop layout (stretch) | todo | | |

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

**Status:** implemented, all backend and frontend checks green, not committed. Next item: WI-10 (kind changes and option warnings).

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
