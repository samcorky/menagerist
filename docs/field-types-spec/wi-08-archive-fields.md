# WI-8: Soft-delete (archive) fields

> Part of the field-types spec. Read `00-INDEX.md` and `01-context-and-conventions.md` first (skip the second if this is that file).
> **Depends on:** WI-14 (`archived` member) and WI-7.
> "WI-n" refers to `wi-*.md` files listed in `00-INDEX.md`; "open question N" refers to `open-questions.md`.


**Spec (proposal).**
- In the schema editor, "Remove field" on an existing field marks the property `x-menagerist.archived: true` (WI-14) instead of removing it. It is reversible, so it uses the 5-second Undo toast rather than a confirmation dialog (guidelines §14). Fields that were never saved (added in the current editing session) can still be removed outright.
- Archived properties are retained in `properties`, removed from the layout (`x-menagerist.layout`), and shown in a collapsed "Removed fields" list in the schema editor with a **Restore** action. Restore re-adds the field to the end of the layout (open question: remember its previous position).
- `normalise()` in `frontend/src/lib/layout.ts` appends every property that is not placed in the layout, so it would bring archived fields straight back. It must skip properties with `x-menagerist.archived: true` (and `orderedKeys` callers must be checked for the same reason).
- Attributes editor and read mode: archived keys are excluded from the schema layout **and** from "Additional details" (add archived keys to the set used to compute `freeformRows`), so their data is preserved but invisible.
- Server-side validation ignores archived properties (strip them from the validation copy of the schema).
- `schemaToItems` / `itemsToSchema` in `schema-editor.svelte` must round-trip archived properties untouched.
- Type-level edge types follow the same rules (same editor).

**Acceptance.** Archive a field, save a node, restore the field: the original value is still there.

**Tests:** editor round-trip keeps `archived`; attributes editor hides archived keys and does not list them as freeform; backend ignores archived properties.


---

## Background (shared by WI-6 to WI-10)


- Editing a node type's `attributes_schema` never touches existing nodes (`update_node_type.py` only saves the type).
- `UpdateNode` validates the **entire** `attributes` dict against the current schema whenever `command.attributes` is not `None`, and the UI sends the full dict on every save. So any schema tightening can block saving an old node, even for fields the user did not touch.
- The backend enforces JSON Schema `required`. Adding a required field therefore makes every existing node of that type fail its next save. This contradicts the design decision that required fields are a soft visual signal that never blocks saving.
- Removing a field from the schema leaves its data in the JSONB (there is no `additionalProperties: false`). The attributes editor then shows the orphaned value under "Additional details", labelled with the raw UUID key. Re-adding the field creates a new UUID, so the old data does not reattach (WI-20 changes this: a re-added field with the same title gets the same readable key and reattaches).
- Schemas are shared instance-wide, so a type edit affects every node of that type.
