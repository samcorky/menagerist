# Decisions so far

> Part of the field-types spec. See `00-INDEX.md`. Record each decision in `docs/DECISIONS.md` as you implement it (short, explaining why).

## Confirmed by the owner

**Scope and compatibility**
- No backwards compatibility and no migration for old-format schemas; `x-multiline`, `x-layout` and a root `required` array are replaced (`wi-14-metadata-namespace.md`).
- Parent and child item types: dropped, not in this spec. Parent and child *items* already work with connections that have a reverse label.
- JSON Forms is not adopted; three ideas are borrowed from it (`considered-not-adopted.md`).

**Keys, metadata and validation**
- Non-validation metadata lives under one `x-menagerist` namespace with an explicit `kind` per field; standard JSON Schema keywords keep validation (`wi-14-metadata-namespace.md`).
- Field keys are the slug of the title at creation, then immutable. Keys are not shown in the UI, there is no "Change key" in v1, and re-adding a same-titled field may reattach orphaned data (accepted). Existing UUID-keyed fields keep working (`wi-20-readable-field-keys.md`).
- Text constraints (starts with, ends with) are stored as generated anchored `pattern`s (`wi-15-text-constraints.md`).

**Features**
- Highlights are display only. They are scoped to the item type (`highlights.card`, shared by every user and item of that type) (`wi-16-highlighted-fields.md`).
- Search scans all attribute values, not only highlighted ones (`wi-17-attribute-search.md`).
- Typed per-item fields use a node schema overlay (`extra_schema` on nodes); loose string details are a stopgap (`wi-19d-per-item-schema-overlay.md`, `wi-18-per-item-custom-fields.md`).
- Suggestions are passive tips inside Settings only, with type-ahead; no inline hints while browsing. This amends guidelines §16b and may be revisited (`wi-21-value-suggestions.md`).
- Reusable parts live in a new backend module `presets`. UI names: the `group` kind is labelled "Table"; a reusable named set is a "Field group" (`field_set` in code); the Settings page is "Saved fields" (`settings/saved-fields`) with Fields, Field groups and Lists; actions are "Save for reuse" and "Add from saved fields" (`wi-19-presets.md`).
- "Item type" replaces "Category" in the UI as a **separate** change, with a redirect from `settings/categories`.
- The location kind is available on any item type; a search may match a latitude (accepted); include the "Use my current location" button (hidden when unavailable) (`further-field-types.md`).

**Backend and process**
- No permission checks on the purge for now; add a DECISIONS entry that destructive commands should check permissions once an authorisation model exists (`wi-09-purge-and-usage.md`).
- The purge updates each node through the unit of work so ETags change; the outbox and WebSocket pattern can come later (`wi-09-purge-and-usage.md`).
- Playwright Test in the frontend package for end-to-end tests, run against the compose stack; component tests (3b) are not part of this change (`testing-strategy.md`).
- Update `frontend/DESIGN_GUIDELINES.md` in the same change: §7, §14, §16a, §16b, §17 (`01-context-and-conventions.md`).

## Follows from the binding design guidelines (no separate decision)

- `required` is advisory only and never blocks saving (§16a) (`wi-06-advisory-required.md`).
- No graph words (node, edge, graph, link, schema, key) in UI text; use "connection" and plain language (§24) (`guidelines-compliance.md`).
- Undo (5 seconds) for reversible actions, confirmation only for permanent ones (§14).

## Proposed, not yet confirmed by the owner

- Connection details (WI-22): a `highlights.connection` list on relationship types, an edit sheet reusing the attribute editor, and multi-add. Proposed in response to the owner's idea of reusing highlights for connections (`wi-22-connection-details.md`).
- No free-form regex in v1 (only the generated starts-with and ends-with patterns); if it ever ships, restrict it to the portable subset described in `wi-15-text-constraints.md`.
- Presets defaults: shared across the whole instance, no built-in presets in v1, repeat imports recognised by a content hash (`open-questions.md`, questions 30 to 32).
- The OpenStreetMap link for "Open in map" (the owner accepted the question as worded but did not name a provider).
- Every defaulted question still open in `open-questions.md`.

## Closed questions (as recorded in `open-questions.md`)

1. **Closed:** checked in the code: the Save button is disabled only while saving or loading, so client-side errors never block it; the server rejects malformed values with a 422, which the editor maps back onto fields. WI-6 only has to keep `required` away from both validators.
3. **Closed:** moot: no event publisher or outbox exists; the outbox and WebSocket pattern can be added later.
15. **Closed:** the purge updates each node through the unit of work, so ETags change (decided).
16. **Closed:** component tests are not part of this change; rely on the module-chain tests and Playwright (decided).
17. **Closed:** no permission check on the purge for now; record the gap in DECISIONS (decided).
19. **Closed:** relationship types get their own `highlights.connection` list, and connection details are shown and edited on the item page (WI-22).
23. **Closed:** typed per-item fields use the WI-19d overlay (decided).
25. **Closed:** "create an item type from these details" is out of v1.
28. **Closed:** the `group` kind is labelled "Table" in the UI; the reusable named collection is a "Field group" (`field_set` in code) (decided).
30. **Closed:** a repeat import is recognised by a content hash of the definition (default, not yet confirmed).
31. **Closed:** no built-in presets in v1 (default, not yet confirmed); revisit when packs are wanted.
32. **Closed:** presets are shared across the whole instance, like item types today (default, not yet confirmed).
33. **Closed:** overlay chosen (see 23).
34. **Closed:** "Item type" replaces "Category" as a separate change, with a redirect from `settings/categories` (decided).
35. **Closed:** the reason list for UUID keys is complete (confirmed).
36. **Closed:** accepted: re-adding a same-titled field reattaches orphaned data (decided).
37. **Closed:** "Change key" is dropped from v1; the single rekey command can be revisited later (decided).
42. **Closed:** no global off switch; the per-field opt-out is enough (decided with 44).
44. **Closed:** amend §16b to allow passive tips inside Settings only; inline hints stay out. May be revisited later (decided).
45. **Closed:** yes, update the design guidelines in the same change (decided).
46. **Closed:** the Settings page is "Saved fields" with Fields, Field groups and Lists; "Save for reuse" and "Add from saved fields" are the actions (decided).
47. **Closed:** `presets` is its own backend module (decided).
48. **Closed:** no developer view of field keys and no "Change key" in v1 (decided).
49. **Closed:** accept that a search can match a latitude for v1 (decided).
50. **Closed:** include the "Use my current location" button (hidden when unavailable) and an OpenStreetMap "Open in map" link; a `geo:` link later (decided).

## Defaults taken without owner confirmation (for re-review)

**Review 2026-09-21 (owner):** confirmed as defaults: restore at the end of the layout (Q2, Q59), no `search: false` editor control yet (Q63), and the exception that detail-name problems disable Save (Q66). Changed: the required marker becomes a neutral asterisk with a soft "recommended" hint when empty (Q58, not yet implemented). Rows below marked *confirmed* need no further review.

Everything below was implemented on a default while working through the spec. None is confirmed by the owner. Change a row here, in `open-questions.md` and in `docs/DECISIONS.md` together. "Q" numbers refer to `open-questions.md`.

| Area | Default taken | Q | Session |
|---|---|---|---|
| Opaque fields | Only the title is editable; a visible "custom" badge marks them | Q4, Q53 | WI-4 |
| Group boolean cells | An untouched boolean cell stays `false` | Q54 | WI-2 |
| Metadata version | `x-menagerist.version` starts at 1 | Q5 | WI-14 |
| Old-format schemas | No migration; layout, long-text and required markers are lost until re-saved | Q56 | WI-14 |
| Rating colour | Fixed amber, not the theme accent | Q6 | WI-5 |
| Required marker (CHANGED, to do) | Neutral asterisk, soft "recommended" hint when empty; the red asterisk is still in the code | Q58 | WI-6 |
| Restoring a field (confirmed) | Returns at the end of the layout, not its old position (Undo restores exactly) | Q2, Q59 | WI-8 |
| Purge | Takes effect immediately even if the form is then cancelled; no permission check | Q17 | WI-9 |
| Kind changes | Matrix in code (widen only); text to choice deferred to WI-21; "Replace" wording not reviewed | Q55 | WI-10 |
| Boolean default | Switch instead of checkbox, so existing boolean fields look different | | WI-11 |
| Sub-field display | Group sub-fields have no "Show as" control | | WI-11 |
| Rank matching | WI-12 skipped: explicit `kind` makes it largely redundant | Q7 | WI-11 |
| Text constraints | Case-sensitive only; no free-form regex, no min/max length | Q12, Q13 | WI-15 |
| Contract fixtures | Live in `contract/fixtures/` at the repo root; CI path filters not checked | Q14 | WI-15 |
| Constraint warning | No "N items would fail this new constraint" count | Q60 | WI-15 |
| Constraint helper text | Shown under the field until an error replaces it | Q61 | WI-15 |
| Kind switch on text | Text to long text drops the constraints | | WI-15 |
| Highlight counts | 3 per type; grid 2, list 3, picker 1, connection row 2; no per-surface lists | Q18 | WI-16 |
| Live card preview | Deferred | Q62 | WI-16 |
| Highlight on kind change | Dropped silently, no editor note | Q65 | WI-16 |
| Attribute search | Tags not searched (Q20); numbers searched except rating (Q21); id-ordered results (Q22) | Q20 to Q22 | WI-17 |
| Search opt-out (confirmed) | `search: false` honoured by the API, no editor control | Q63 | WI-17 |
| Match context | "Matched in ..." shown on list and grid cards while searching | Q64 | WI-17 |
| Detail limits | 100-character names, 50 details per item, details only, nodes only | Q24, Q26 | WI-18a |
| Detail name problems (confirmed) | Block Save (exception to "client errors never block") | Q66 | WI-18a |
| Detail value types | Text, Number, Yes/No for new details; anything else read-only JSON | | WI-18a |
| Connection rows | Show the other item's card highlights and the connection's own details; remove is undoable (re-creates the connection) instead of confirmed | Q51 | WI-22a |

Also still proposed rather than confirmed (see the section above): connection details (WI-22), no free-form regex in v1, presets defaults (Q30 to Q32), the OpenStreetMap provider, and every other defaulted question in `open-questions.md`.
