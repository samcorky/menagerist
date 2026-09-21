# WI-22: Connection details, show, edit and summarise

> Part of the field-types spec. Read `00-INDEX.md` and `01-context-and-conventions.md` first (skip the second if this is that file).
> **Depends on:** WI-16 (highlights) and WI-14. Frontend only, except an optional `CreateEdges` command.
> "WI-n" refers to `wi-*.md` files listed in `00-INDEX.md`; "open question N" refers to `open-questions.md`.


**Goal.** Let a connection carry details that people can see and change on the item page: "Signed at London, 12 Mar 2024, signed by Bryan Cranston". Reuse what already exists (relationship type fields, the field kinds and widgets, and the highlight mechanism from WI-16) instead of building a second system.

**Verified in the code.** The backend already supports this end to end: `POST /edge` accepts `attributes`, `PATCH /edge/{id}` updates them (ETag-conditional), `EdgeResponse` returns them, `UpdateEdge` validates them against the relationship type's schema, and settings already lets you define that schema. What is missing is the frontend: the item page lists only the connection label and the other item's name, and the add-connection form has no details section. **This item needs no backend change.**

## Where highlights are scoped

| Highlight list | Stored on | Describes | Shown on |
|---|---|---|---|
| `highlights.card` (WI-16) | the **item type's** schema | the item's own fields | list and grid cards, the picker suffix, and connection rows (as a summary of the *other* item) |
| `highlights.connection` (new) | the **relationship type's** schema | the connection's own details | the connection row, on both items' pages |

- Both are per type, shared by everyone and permanent: not per item, not per user and not per view. Every item of a type summarises itself the same way everywhere, and every connection of a relationship type does too.
- Per-item overlay fields (WI-19d) are not highlightable, because a type-level list cannot name fields that only some items have. Items with no type have no schema and therefore no highlights (they show name and type only).
- `highlights.connection` holds at most 2 entries and uses the same rules as WI-16: eligible kinds only, ordered, archived or missing keys dropped by `normaliseHighlights`, and the shape validated in the shared schema-check helper (the relationship-type handlers use it too).

## WI-22a: show and edit connection details

- **Connection row.** Three lines, all single-line with ellipsis (guidelines §7c): the connection label ("Signed at", or the reverse label seen from the other side, as today), the other item's title with its own card highlights, and the connection's highlighted details ("12 Mar 2024 · Bryan Cranston").
- **Edit.** Tapping a row opens an "Edit connection" sheet (a bottom sheet on mobile, as the capture sheet already is) that reuses `attributes-editor` over the relationship type's schema. That gives the same kinds, widgets, soft required, friendly errors and the "Additional details" section for loose extras, so it is one mental model with items (guidelines §16a, §16b). Saving calls `PATCH /edge/{id}` with the ETag; server validation errors are mapped back onto fields, as on the item page. **Remove connection** uses the 5-second Undo toast (§14).
- **Relationship type editor.** The Settings page for relationship types gets the same "Show on card" style toggle from WI-16, labelled for connections, capped at 2.
- **Rendering reuse.** Generalise `node-summary.svelte` (WI-16) into a summary component that takes a set of values, a schema, a highlight list and a size. An item summary and a connection summary are then two uses of the same component and the same `SummaryWidget`s.
- **Not in v1:** typed per-connection extras beyond the relationship type's fields (the overlay is for items only), and searching connection details (see the search follow-up in `01-context-and-conventions.md`).

## WI-22b: add several connections at once

- **Multi-select.** After choosing the relationship ("Pictured with"), the picker allows selecting several items at once and creating new ones inline (name only, untyped unless the picker's filter names a type), so the photo with six people is one action, not six.
- **Details.** If the relationship type has fields, one details form appears and applies to **every** selected item. Connections that need different details (a poster signed in three places on different dates) are added one at a time, or edited afterwards through 22a.
- **Result.** "6 people connected" with the 5-second Undo toast (deleting the created connections).
- **Idempotence.** Connections that already exist for an item, target and relationship type are skipped and reported. There is no uniqueness constraint in the database, so this check uses the existing `list_for_node` (as WI-21 does). Whether the batch is one backend command or several client calls: a single `CreateEdges` command in one unit of work is preferable to N calls (structural over convention), and would be the only backend addition in this item.

## Examples

- **Poster signed in three places:** three connections "Signed at" to the Places London, Liverpool and Southampton. The relationship type has fields Date and Signed by, both highlighted. The poster's connection list reads "London · 12 Mar 2024 · Bryan Cranston" and so on.
- **Photo:** one "Pictured with" multi-add for Me, Dad and four cast members; "Taken at" one event; the event is "Held at" the Place. Neither connection needs details.

## Interactions

- WI-7 (changed keys only), WI-6 (advisory required), WI-8 (archive) and WI-14 (`x-menagerist`) already apply to edge types because `UpdateEdge` and `CreateEdge` use the same validation helper and the relationship editor is the same schema editor.
- WI-21: later, repeated free-text details on connections ("Signed by" typed on several) could feed the same connect-to-an-item suggestions.
- Guidelines: §17 (connection rows show details), §14 (Undo), §10 and §16 (forms), §24 ("Connection" wording; the picker still says "Relationship", follow-up 4).

**Acceptance.**
- With Date and Signed by highlighted, the poster's connection rows show them; editing a row changes them, saves with the ETag, and shows server errors on the right field; removing a connection offers Undo.
- Highlighting nothing leaves rows as today (label and item name).
- Selecting six people and confirming creates six connections in one action, skips ones that already exist and reports them.
- Nothing in this item requires a new endpoint, except optionally `CreateEdges`.

**Tests.** Frontend: connection row rendering with and without highlights and details; the edit sheet's ETag save and error mapping; multi-select creation and duplicate skipping; `normaliseHighlights` for the `connection` list. If `CreateEdges` is added: in-memory unit tests (creates, skips duplicates, refuses a self connection, atomic) and integration `I-11`. End-to-end: highlight two fields on a relationship type, add a connection with details, see them on the row, edit and undo a removal.
