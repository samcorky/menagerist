# Progress

Update at the end of every session. Read this first.

| Item | Status | Branch | Notes for the next session |
|---|---|---|---|
| WI-1 to WI-4 bug fixes | done, awaiting user review and commit | feature/initial-implementation | See "WI-1 to WI-4 session notes" below. |
| WI-14 metadata namespace | todo | | |
| WI-20 readable field keys | todo | | |
| WI-5 rating | todo | | |
| WI-6 advisory required | todo | | |
| WI-7 changed-keys validation | todo | | |
| WI-8 archive fields | todo | | |
| WI-9 purge and usage | todo | | |
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

**Status:** implemented, all checks green, not committed (the user commits). Next item: WI-14 (metadata namespace).

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
