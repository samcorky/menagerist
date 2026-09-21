# Open questions

> Part of the field-types spec. Read `00-INDEX.md` and `01-context-and-conventions.md` first (skip the second if this is that file).
> **Type:** reference file. Each open question has a default; closed ones state the decision.
> "WI-n" refers to `wi-*.md` files listed in `00-INDEX.md`; "open question N" refers to `open-questions.md`.


1. **Closed:** checked in the code: the Save button is disabled only while saving or loading, so client-side errors never block it; the server rejects malformed values with a 422, which the editor maps back onto fields. WI-6 only has to keep `required` away from both validators.
2. WI-8: on restore, should a field return to its previous layout position and section?
3. **Closed:** moot: no event publisher or outbox exists; the outbox and WebSocket pattern can be added later.
4. WI-4: is a visible "custom" badge on opaque fields the right UX, given the "never feel like configuring a database" principle?
5. WI-14: should `version` start at 1 now, given there is no migration path yet?
6. Rating colour: fixed amber or theme accent (`primary`)?
7. WI-12: is rank-based matching worth it now, or only once a second overlapping type (multi-choice, partial date, identifier) is scheduled?
8. WI-13: is depth 3 with tabs at the top level the right limit, or should tabs be dropped until asked for?
9. WI-13: should the backend validate the layout structure on node-type save?
10. WI-13: which drag-and-drop library, given Svelte 5, touch, keyboard and nested containers?
11. WI-14: `x-menagerist` is descriptive but long; is a shorter name wanted, given it is repeated on every property?
12. **Closed (WI-15):** case-sensitive only for v1 (decided by default). Was: is case-sensitive matching enough? A case-insensitive option could be emitted as per-letter character classes for ASCII (`[Cc][Oo]...`), but it makes patterns unreadable and the editor's reverse-parse harder.
13. **Closed (WI-15):** structured constraints only (starts with, ends with); no free-form regex, and min/max length is not built. Was: should min/max length and a free-form regex live in the same "Validation" section as advanced options? If free-form regex ships at all, the recommended route is the portable subset with backend-authoritative enforcement (see WI-15); otherwise keep constraints purely structured.
14. **Partly closed (WI-15):** the regex conformance fixture lives in `contract/fixtures/` at the repo root and both suites read it; CI path filters have not been checked. Was: where should the shared contract fixtures live so both suites can read them (a top-level `contract/fixtures/` directory, or under `docs/`), and should CI path filters treat a change there as touching both backend and frontend?
15. **Closed:** the purge updates each node through the unit of work, so ETags change (decided).
16. **Closed:** component tests are not part of this change; rely on the module-chain tests and Playwright (decided).
17. **Closed:** no permission check on the purge for now; record the gap in DECISIONS (decided).
18. **Closed (WI-16):** defaults kept: 3 highlighted fields; grid 2, list 3, picker 1, row 2; no per-surface lists yet (not confirmed by the owner). Was: are 3 highlighted fields and the per-surface counts (grid 2, list 3, picker 1, relationship row 2) right, and should explicit per-surface lists exist from the start or only when someone needs them?
19. **Closed:** relationship types get their own `highlights.connection` list, and connection details are shown and edited on the item page (WI-22).
20. **Closed (WI-17, default, not confirmed):** tags are not searched. Was: should tags be searched too? They are not today, and this change touches the same query.
21. **Closed (WI-17, default, not confirmed):** numbers are searched except ratings; yes/no and rating are the only non-searchable kinds. Was: should numbers be searchable by default (a year or price is, a rating is not)? Confirm boolean and rating as the only non-searchable kinds.
22. **Closed (WI-17, default, not confirmed):** results stay in id order. Was: is id-ordered search acceptable for v1, given relevance ranking would need a different pagination cursor?
23. **Closed:** typed per-item fields use the WI-19d overlay (decided).
24. **Closed (WI-18a, default, not confirmed):** 100-character names and 50 details per item, applied to details only, not schema keys. Was: WI-18: limits for custom details (proposal: 100-character names, 50 per node). Right numbers, and should they apply to schema-defined keys as well?
25. **Closed:** "create an item type from these details" is out of v1.
26. WI-18c: do edge types get custom details, adoption and the suggestions strip too, or node types only?
27. WI-18c: should adoption run in one transaction for all affected nodes, or in batches (a large type could be slow) with partial-progress reporting?
28. **Closed:** the `group` kind is labelled "Table" in the UI; the reusable named collection is a "Field group" (`field_set` in code) (decided).
29. WI-19: copy-on-apply with provenance for v1, and live-linked choice lists (with a sync command) only later. Agree, or should linked lists come first because editing once for every type is the main benefit?
30. **Closed:** a repeat import is recognised by a content hash of the definition (default, not yet confirmed).
31. **Closed:** no built-in presets in v1 (default, not yet confirmed); revisit when packs are wanted.
32. **Closed:** presets are shared across the whole instance, like item types today (default, not yet confirmed).
33. **Closed:** overlay chosen (see 23).
34. **Closed:** "Item type" replaces "Category" as a separate change, with a redirect from `settings/categories` (decided).
35. **Closed:** the reason list for UUID keys is complete (confirmed).
36. **Closed:** accepted: re-adding a same-titled field reattaches orphaned data (decided).
37. **Closed:** "Change key" is dropped from v1; the single rekey command can be revisited later (decided).
38. WI-21: are the starting thresholds (3 repeats and 8 or more distinct values for a link; 12 or fewer distinct and 10 or more filled for a choice) sensible, and should they be settings or constants?
39. WI-21: keep the text after linking (recommended, reversible) or offer to clear it? Should archiving the field be offered automatically when everything is linked?
40. WI-21: should a newly created target item default to untyped, ask for an item type, or suggest one (for example Person for an Artist field)? What edge direction and reverse-label defaults?
41. WI-21: split multi-valued cells ("A; B", "A & B") and fuzzy variants ("Davis, Miles") later with a review step, or never?
42. **Closed:** no global off switch; the per-field opt-out is enough (decided with 44).
43. WI-21: is "reappear when the count has doubled" the right rule for a dismissed suggestion, or should it never return, or return after a time period?
44. **Closed:** amend §16b to allow passive tips inside Settings only; inline hints stay out. May be revisited later (decided).
45. **Closed:** yes, update the design guidelines in the same change (decided).
46. **Closed:** the Settings page is "Saved fields" with Fields, Field groups and Lists; "Save for reuse" and "Add from saved fields" are the actions (decided).
47. **Closed:** `presets` is its own backend module (decided).
48. **Closed:** no developer view of field keys and no "Change key" in v1 (decided).
49. **Closed:** accept that a search can match a latitude for v1 (decided).
50. **Closed:** include the "Use my current location" button (hidden when unavailable) and an OpenStreetMap "Open in map" link; a `geo:` link later (decided).
51. **Closed (WI-22a, default, not confirmed):** a connection row shows both the other item's card highlights and the connection's own details. Was: WI-22: should a connection row show the other item's card highlights as well as the connection's own details (two levels of detail on one row), or the item title only when the connection has details?
52. WI-22b: when creating people inline in a multi-add, which type do they get (untyped, or the type the picker is filtered to)? And is a single `CreateEdges` command wanted, or is calling `POST /edge` several times acceptable for v1?
53. WI-4: should `opaque` fields be editable beyond the title (for example a "Convert to text" action that drops the unknown keywords), or stay read-only apart from the title until WI-14 defines unknown kinds? Default: title only.
54. WI-2: should an untouched boolean cell in a group row stay `false` (current, no unset state) or be omitted? Default: `false`, recorded in `docs/DECISIONS.md`.
55. **Closed (WI-10):** changing a field's kind clears its `display` and `config` metadata; other metadata is kept.
56. WI-14: old-format item types lose layout, long-text rendering and required markers until re-saved. Default (decided in the spec): no migration; say so in release notes if the app has users by then.
57. WI-20: the key follows the label while a field is unsaved and freezes on save. If the editor ever keeps a saved schema open in place (no reload after save), pending flags must be cleared on save. Today saving closes the editor, so no action is needed.
58. WI-6: required fields show an always-on red asterisk (`text-destructive`), which reads like an error. Should it be a neutral or "recommended" style, and should empty required fields be highlighted (guidelines §16a) now or with the §18 "items missing information" group? Default: leave as is.
59. WI-8: should a restored field return to its previous position in the layout (needs the old position stored) or the end? Default: the end. Undo, by contrast, restores the exact previous editor state.
60. WI-15: should a new constraint on a saved text field warn with the number of items whose value would fail it (as removing a choice option does)? It needs a query that evaluates the pattern over stored values. Default: no; stale values never block other edits.
61. WI-15: should the attributes form show a rule's helper text always (as now) or only while the field is focused or empty? Default: always shown until there is an error.
62. WI-16: add a live card preview at the top of the schema editor, using sample values (deferred, optional in the spec)?
63. WI-17: should `x-menagerist.search: false` get an editor control (a per-field "Include in search" option behind a "More options" section, guidelines-compliance row 12)? Default: no editor control yet; the API and both search paths honour it.
64. WI-17: where should the "Matched in ..." line show? Default: on the list card and the grid card, one truncated line each, only while a search is active and the name and description did not match.
65. WI-16: when a highlighted field's kind changes to a non-highlightable one, should the editor say so? Default: it drops silently (the pin is hidden for those kinds).
66. WI-18a: detail-name problems (blank name with a value, duplicates, a name equal to a field) disable Save, an exception to "client errors never block Save" because the alternative is silent data loss. Keep the exception?
