# WI-10: Constrain kind changes and warn on removed choice options

> Part of the field-types spec. Read `00-INDEX.md` and `01-context-and-conventions.md` first (skip the second if this is that file).
> **Depends on:** WI-8 and WI-9 (usage counts).
> "WI-n" refers to `wi-*.md` files listed in `00-INDEX.md`; "open question N" refers to `open-questions.md`.


**Kind changes on an existing field.** Correction to an earlier claim: a stored JSON number or boolean does **not** validate against `type: 'string'`, but the UI rewrites values as strings on the next save (`attributesToRows` → `rowsToAttributes`), so conversions to text heal themselves. With WI-7 in place, values that do not fit never block unrelated saves.

| From → To | Offer in kind dropdown? |
|---|---|
| text ↔ longtext | Yes |
| number, boolean, date, choice → text / longtext | Yes (values are stringified on next save) |
| text / longtext → number, boolean, date, choice | No inline; use **Replace field** (create a new field, archive the old one) |
| text → choice | Only through the WI-21 suggestion, which builds the options from the existing values |
| anything ↔ group | No; use Replace field |
| rating ↔ number | Yes (rating is a constrained number); warn that values outside 1–5 will error when edited |

Implement by giving each `FieldTypeDescriptor` an optional `convertibleFrom?: string[]` (or a central matrix), and filter the kind dropdown for existing fields. New, unsaved fields can be any kind.

**Removing a choice option that is in use.** Show a warning with a count of affected nodes (reuse the WI-9 count query, matching value equality on the key). Do not block. Nodes keep the value (WI-7 stops it blocking saves). In the attributes editor, when a stored value is not among the options, render it as a selected item labelled "(no longer an option)" instead of showing "— select —".

**Tests:** dropdown filtering; the "no longer an option" rendering.


---

## Background (shared by WI-6 to WI-10)


- Editing a node type's `attributes_schema` never touches existing nodes (`update_node_type.py` only saves the type).
- `UpdateNode` validates the **entire** `attributes` dict against the current schema whenever `command.attributes` is not `None`, and the UI sends the full dict on every save. So any schema tightening can block saving an old node, even for fields the user did not touch.
- The backend enforces JSON Schema `required`. Adding a required field therefore makes every existing node of that type fail its next save. This contradicts the design decision that required fields are a soft visual signal that never blocks saving.
- Removing a field from the schema leaves its data in the JSONB (there is no `additionalProperties: false`). The attributes editor then shows the orphaned value under "Additional details", labelled with the raw UUID key. Re-adding the field creates a new UUID, so the old data does not reattach (WI-20 changes this: a re-added field with the same title gets the same readable key and reattaches).
- Schemas are shared instance-wide, so a type edit affects every node of that type.
