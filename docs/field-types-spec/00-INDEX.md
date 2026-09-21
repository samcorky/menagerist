# Field types and schema evolution: spec index

**Status:** proposal for Claude Code to read, challenge and implement. Items the owner has approved in review are listed in [`decisions.md`](decisions.md); everything else is a proposal or has a default in [`open-questions.md`](open-questions.md). Record decisions in `docs/DECISIONS.md` as you implement.
**Repo / branch:** `samcorky/menagerist`, `feature/initial-implementation`
**Reviewed at:** `c6fbaeb` (2026-09-20)
**Scope:** the field-type registry work from `ed7cf7f` / `c6fbaeb`, the attributes editor, and how node-type schema edits affect existing nodes.

This is the single 155 KB spec split into small files so each session loads only what it needs. The original `field-types-spec.md` is kept alongside for reference.

## How to use these files

1. Read this index, then [`01-context-and-conventions.md`](01-context-and-conventions.md) (repo conventions, vocabulary, cross-cutting rules).
2. Pick **one** work item file (`wi-*.md`) and implement it as a separate, reviewable change. Each file states what it **depends on**, its scope, acceptance criteria and tests.
3. Read only the reference files that item names. Usually that is [`testing-strategy.md`](testing-strategy.md) for its integration tests (rows I-1 to I-11 and the work-item map), [`backend-surface.md`](backend-surface.md) for ports, use cases and endpoints, and [`guidelines-compliance.md`](guidelines-compliance.md) before writing any UI copy.
4. [`decisions.md`](decisions.md) says what is decided. [`open-questions.md`](open-questions.md) lists the rest, each with a default. Do not treat a closed question as open.
5. Do not commit on the user's behalf (`CLAUDE.md`).

## Order of work

Integration tests are written alongside each item (see `testing-strategy.md`). `considered-not-adopted.md` records the JSON Forms review and the three ideas borrowed from it (WI-11, WI-12 and WI-13).

| Phase | Files | Note |
|---|---|---|
| 1. Bug fixes | [`wi-01-04-bug-fixes.md`](wi-01-04-bug-fixes.md) | Independent; do first. |
| 1b. Structured metadata namespace | [`wi-14-metadata-namespace.md`](wi-14-metadata-namespace.md) | Land before everything below. |
| 1c. Readable, immutable field keys | [`wi-20-readable-field-keys.md`](wi-20-readable-field-keys.md) | Before anything that creates fields. |
| 2. Rating field type | [`wi-05-rating-field-type.md`](wi-05-rating-field-type.md) | Small; exercises the registry. |
| 3. Schema evolution | [`wi-06-advisory-required.md`](wi-06-advisory-required.md), [`wi-07-changed-keys-validation.md`](wi-07-changed-keys-validation.md), [`wi-08-archive-fields.md`](wi-08-archive-fields.md), [`wi-09-purge-and-usage.md`](wi-09-purge-and-usage.md), [`wi-10-kind-changes-and-option-warnings.md`](wi-10-kind-changes-and-option-warnings.md) | In this order; WI-6 and WI-7 both change `_validate_attributes.py`. |
| 4. Display options and matching | [`wi-11-display-options.md`](wi-11-display-options.md), [`wi-12-rank-matching.md`](wi-12-rank-matching.md) | WI-12 is optional. |
| 5. More field types and constraints | [`wi-15-text-constraints.md`](wi-15-text-constraints.md), [`further-field-types.md`](further-field-types.md) | `further-field-types.md` lists candidates, including the location kind; none scheduled. |
| 5b. Highlights and attribute search | [`wi-16-highlighted-fields.md`](wi-16-highlighted-fields.md), [`wi-17-attribute-search.md`](wi-17-attribute-search.md) |  |
| 5c. Per-item custom fields | [`wi-18-per-item-custom-fields.md`](wi-18-per-item-custom-fields.md) | 18a first; 18b and 18c after WI-19d is understood. |
| 5d. Reusable presets and per-item typed fields | [`wi-19-presets.md`](wi-19-presets.md), [`wi-19d-per-item-schema-overlay.md`](wi-19d-per-item-schema-overlay.md) | 19d (overlay) is decided. |
| 5e. Value suggestions | [`wi-21-value-suggestions.md`](wi-21-value-suggestions.md) | Later; needs WI-18c. |
| 5f. Connection details | [`wi-22-connection-details.md`](wi-22-connection-details.md) | Frontend; needs WI-16. |
| 6. Stretch: drag-and-drop layout editor | [`wi-13-drag-and-drop-layout.md`](wi-13-drag-and-drop-layout.md) | After WI-8; benefits from WI-11. |

## All files

| File | What it covers | Size |
|---|---|---|
| [`01-context-and-conventions.md`](01-context-and-conventions.md) | How to work in this repo, vocabulary and cross-cutting requirements. | 5 KB |
| [`backend-surface.md`](backend-surface.md) | New use cases, endpoints, ports and adapters, and what changes in existing use cases. | 10 KB |
| [`considered-not-adopted.md`](considered-not-adopted.md) | Why JSON Forms was not adopted and the three ideas borrowed from it. | 2 KB |
| [`further-field-types.md`](further-field-types.md) | Candidate kinds (partial date, money, URL, multi-choice, ...) and the location kind. | 6 KB |
| [`guidelines-compliance.md`](guidelines-compliance.md) | 20-row review, UI copy table (graph words never in the UI) and driver triage. | 7 KB |
| [`open-questions.md`](open-questions.md) | Every question with its status; closed ones state the decision. | 7 KB |
| [`testing-strategy.md`](testing-strategy.md) | Backend integration (I-1 to I-11), contract fixtures, frontend integration, Playwright; work-item map. | 14 KB |
| [`wi-01-04-bug-fixes.md`](wi-01-04-bug-fixes.md) | Four confirmed bugs: clearing choice/date, blank group cells, day-early dates, unrecognised properties rewritten. | 5 KB |
| [`wi-05-rating-field-type.md`](wi-05-rating-field-type.md) | Star rating kind with hover, click, keyboard; includes reference code. | 7 KB |
| [`wi-06-advisory-required.md`](wi-06-advisory-required.md) | `required` becomes advisory and never reaches the validators. | 3 KB |
| [`wi-07-changed-keys-validation.md`](wi-07-changed-keys-validation.md) | UpdateNode/UpdateEdge report errors only for changed keys. | 3 KB |
| [`wi-08-archive-fields.md`](wi-08-archive-fields.md) | Removing a field archives it; data kept; restore from Removed fields. | 3 KB |
| [`wi-09-purge-and-usage.md`](wi-09-purge-and-usage.md) | Count and permanently delete a field's data across an item type. | 4 KB |
| [`wi-10-kind-changes-and-option-warnings.md`](wi-10-kind-changes-and-option-warnings.md) | Which kind changes are offered; warn when removing an in-use option. | 3 KB |
| [`wi-11-display-options.md`](wi-11-display-options.md) | Per-field presentation variants (boolean switch/checkbox/buttons, choice dropdown/radio/chips, rating stars). | 3 KB |
| [`wi-12-rank-matching.md`](wi-12-rank-matching.md) | Optional: replace registration-order matching with ranked matching. | 2 KB |
| [`wi-13-drag-and-drop-layout.md`](wi-13-drag-and-drop-layout.md) | Rows, groups and tabs in `x-menagerist.layout`, edited by drag and drop. | 7 KB |
| [`wi-14-metadata-namespace.md`](wi-14-metadata-namespace.md) | Move all non-validation metadata under `x-menagerist` with an explicit `kind`; no backwards compatibility. | 6 KB |
| [`wi-15-text-constraints.md`](wi-15-text-constraints.md) | Generated anchored patterns; regex dialect handling between Python and JavaScript. | 9 KB |
| [`wi-16-highlighted-fields.md`](wi-16-highlighted-fields.md) | Display-only highlights, scoped to the item type. | 6 KB |
| [`wi-17-attribute-search.md`](wi-17-attribute-search.md) | Search scans all attribute values; query, ports and result context. | 5 KB |
| [`wi-18-per-item-custom-fields.md`](wi-18-per-item-custom-fields.md) | Make "Add detail" safe (18a), promote a detail to a field (18b), adopt across items (18c). | 9 KB |
| [`wi-19-presets.md`](wi-19-presets.md) | New `presets` module; copy-on-apply with provenance; packs and import/export. | 10 KB |
| [`wi-19d-per-item-schema-overlay.md`](wi-19d-per-item-schema-overlay.md) | Nodes carry an `extra_schema` so per-item fields are typed like schema fields. | 2 KB |
| [`wi-20-readable-field-keys.md`](wi-20-readable-field-keys.md) | Field keys become the slug of the title at creation and never change. | 7 KB |
| [`wi-21-value-suggestions.md`](wi-21-value-suggestions.md) | Passive tips in Settings, type-ahead, and a connect-items command. | 11 KB |
| [`wi-22-connection-details.md`](wi-22-connection-details.md) | Show and edit a connection's details; highlights on relationship types; multi-add. | 7 KB |
| [`decisions.md`](decisions.md) | What the owner has decided, and what is only proposed. | (see file) |
| [`example-node-type-schema.json`](example-node-type-schema.json) | Example item type schema using readable keys, `x-menagerist`, rows and tabs. Useful as a contract fixture. | small |

## Where the original sections went

The text still says "section N" in a few places; the replacements below were applied, and this table maps the original numbering.

| Original section | File |
|---|---|
| 0. How to use | `01-context-and-conventions.md` |
| 1. Bugs (WI-1 to WI-4) | `wi-01-04-bug-fixes.md` |
| 1b. WI-14 / 1c. WI-20 | `wi-14-metadata-namespace.md` / `wi-20-readable-field-keys.md` |
| 2. WI-5 | `wi-05-rating-field-type.md` |
| 3. WI-6 to WI-10 | `wi-06` to `wi-10` files |
| 4 to 4j. WI-11 to WI-22 | `wi-11` to `wi-22` files (WI-19d has its own file) |
| 5. Further field types | `further-field-types.md` |
| 6. JSON Forms | `considered-not-adopted.md` |
| 7. Integration testing | `testing-strategy.md` |
| 8. Backend surface | `backend-surface.md` |
| 9. Cross-cutting | `01-context-and-conventions.md` |
| 9b. Compliance review | `guidelines-compliance.md` |
| 10. Open questions | `open-questions.md` |
