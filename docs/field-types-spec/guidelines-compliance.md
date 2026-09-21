# Compliance review against the design guidelines and architecture docs

> Part of the field-types spec. Read `00-INDEX.md` and `01-context-and-conventions.md` first (skip the second if this is that file).
> **Type:** reference file. Read before writing any UI copy.
> "WI-n" refers to `wi-*.md` files listed in `00-INDEX.md`; "open question N" refers to `open-questions.md`.


Read for this review: `frontend/DESIGN_GUIDELINES.md` (binding for UI), `docs/ARCHITECTURE.md`, `AGENTS.md`, `CLAUDE.md`, `docs/DECISIONS.md`, and the project's stated principles: no ceremony without a concrete driver, structural enforcement over convention, and the graph model staying invisible to casual users.

**Result:** mostly aligned. The review found conflicts, which are fixed in the items above where the answer was clear and raised as open questions where it needs a decision.

| # | Rule (source) | Spec item | Status | Resolution |
|---|---|---|---|---|
| 1 | Freeform fields use "the same Name + Kind flow" and kinds must match between schema and freeform fields (guidelines §16b, §26) | WI-18a limits custom details to Text, Number and Yes/No; WI-19d was optional | **Conflict, resolved** | The guidelines require typed per-item fields, so WI-19d (overlay) was chosen. WI-18a is a stopgap until it lands. |
| 2 | Menagerist "doesn't do this automatically or nag the user to formalise" a recurring custom field (§16b) | WI-18c strip; WI-21 inline hint on an item | **Conflict (partly)** | Suggestions stay passive and inside Settings (the schema editor). The inline item hint is out of v1. Type-ahead (prevention) stays. §3.4 favours suggestions. Decided: amend §16b to allow passive tips inside Settings only (may be revisited later). |
| 3 | Do not expose internal field identifiers; derive the key from the label without surfacing it (§16, §16a) | WI-20 showed the key under "Advanced" | **Conflict, fixed** | The key is not shown in the normal UI. WI-20b ("Change key") needs it visible, so it is not for v1. Decided: no developer view in v1. |
| 4 | Yes/No is a toggle switch, not a checkbox (§16a) | WI-11 defaulted to a checkbox | **Conflict, fixed** | Switch is the default; checkbox and Yes/No buttons are alternatives. |
| 5 | The kind is called "Rating"; add it when a concrete collection type needs it (§16a) | WI-5 | Fixed | Descriptor label is "Rating". The driver is the movie card. |
| 6 | Required is a soft signal, never blocks saving (§16a) | WI-6 | Aligned | WI-6 is itself a compliance fix. |
| 7 | No graph vocabulary in UI text; connections, not edges or links (§3.1, §17, §24) | WI-21, WI-18c, WI-9 copy | **Fixed** | See the UI copy table below. |
| 8 | Undo (5 seconds) for reversible actions, confirmation for irreversible ones, not both (§14) | WI-8 archive, WI-21 connect, WI-9 purge | **Fixed** | Archive and connect use the 5-second Undo toast. The permanent purge keeps a confirmation that says what will be lost. |
| 9 | Truncation rules and collection-first hierarchy (§7c, §3.2) | WI-16 | Aligned | Note added to WI-16. |
| 10 | Validate at useful moments, not on every keystroke (§15) | WI-1, WI-15 | Note added | Constraint messages appear on blur or save. The existing validator is derived on every change; keep messages hidden until then. |
| 11 | Search is natural language (§8) | WI-17 | Partly | Attribute values become searchable. Phrases such as "signed items" or "things from 1999" are out of scope. |
| 12 | Progressive disclosure, minimise decisions, one obvious action (§3.3 to §3.5, §10) | Schema editor gains many per-field controls | Risk | Keep the field row to label, kind, required and "show on card". Put show-as, search opt-out and suggestions opt-out behind one per-field "More options". |
| 13 | Business logic in domain and application; composite writes through `JoinedUnitOfWork` (`AGENTS.md`; used in `upload_and_attach_media.py`) | WI-18b was two frontend calls | **Fixed** | One backend command composes the existing update commands in one unit of work, and WI-21 does the same for create-item plus create-edge. |
| 14 | Dependency direction, in-memory adapters, CQRS, RFC 9457 errors, no `try/except` in routers, 100% coverage for domain and application (`AGENTS.md`) | All backend items | Aligned | Restated by the spec; every new use case needs full unit coverage. |
| 15 | Bounded contexts; cross-module references by id (`ARCHITECTURE.md`) | `presets` module; `ListNodes` reading node types | Aligned | Judgement call whether presets needs its own module now (open question 47). |
| 16 | No ceremony without a concrete driver; worker, outbox and clock are parked | WI-12, WI-13, WI-19c, WI-19d, WI-20b, the portable regex subset | Flagged | See the driver table below. Everything runs on demand; there is no worker or background job. |
| 17 | Never commit on the user's behalf (`CLAUDE.md`) | `01-context-and-conventions.md` said "one commit per work item" | **Fixed** | Reworded: one reviewable change per item, and the user commits. |
| 18 | Add dependencies only when strictly necessary; check Renovate and image size (`AGENTS.md`) | Drag-and-drop library (runtime), test libraries (dev only) | Note | The WI-13 spike must estimate bundle size and prefer the lightest option. Dev dependencies do not affect the image. |
| 19 | Docs explain why and avoid volume; British English (`AGENTS.md`) | DECISIONS entries | Note | Keep each entry short; add no new documents beyond updating the existing ones. |
| 20 | All API calls through `client.ts`; no SSR; Svelte 5 runes (`AGENTS.md`) | E2E seeding | Note | E2E helpers use the same client wrapper where practical. |

## UI copy (guidelines §24: user-facing language wins)

| Internal | Say in the UI |
|---|---|
| node, item record | item, or the specific type (Record, Person) |
| edge, link, relationship | connection; "Connect these 3 records to Miles Davis"; "Connected as: Artist" |
| edge type, target | how they are connected; the item they connect to |
| schema, key, UUID, kind string | not surfaced; fields have a label and a kind (Text, Number, Yes/No, Rating...) |
| archive | Remove field (recoverable under "Removed fields") |
| purge | Delete data permanently |
| adopt, promote | Make this a field; Move to the new field |
| suggestion | Tip |
| highlight | Show on card |
| preset, `field_set`, `choice_list` | Saved fields (the Settings page); Field group; List. Adding one: "Add from saved fields"; saving one: "Save for reuse" |
| `group` field kind | Table |
| pack | Export and import saved fields (no separate user-facing word) |

## Concrete drivers (no ceremony without one)

- **Has a driver:** the bug fixes; WI-14 and WI-20 (reduce ceremony and make data readable; the guidelines say derive the key from the label); WI-5 (movie card rating); WI-6 (guideline compliance); WI-7 to WI-10 (safe destructive and evolving operations); WI-15, WI-16, WI-17 (requested); WI-18 and WI-19d (guideline §16b requires typed per-item fields).
- **Roadmap-driven, defer until asked:** WI-19c import/export and built-in packs (goals list import/export and plugins).
- **No driver yet, keep optional or stretch:** WI-12 rank matching, WI-13 drag-and-drop, WI-20b change key, the portable regex subset (only if free-form regex ships).
- **Idea awaiting a guideline decision:** WI-21 value suggestions (conflicts with §16b as written).
