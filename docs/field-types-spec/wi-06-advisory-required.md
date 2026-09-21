# WI-6: Make `required` a soft signal

> Part of the field-types spec. Read `00-INDEX.md` and `01-context-and-conventions.md` first (skip the second if this is that file).
> **Depends on:** WI-14 (`x-menagerist.required`).
> "WI-n" refers to `wi-*.md` files listed in `00-INDEX.md`; "open question N" refers to `open-questions.md`.


**Spec.**
- Stop emitting the standard JSON Schema `required` array from the schema editor. Store the names in `x-menagerist.required` (WI-14; array of field keys).
- Frontend readers use `readSchemaMeta(schema).required` for the asterisk and the "required" hint. The client-side validator must be given a copy of the schema with `required` removed, so required never produces a blocking error.
- Backend: `validate_attributes` validates a copy of the schema with the top-level `required` removed. This guarantees required stays advisory even for a schema authored through the API with a standard `required` array.
- Keep `required` errors purely advisory: the form may show "recommended" styling, but must never disable save.

**Confirm before implementing.** I did not verify whether the collection page's save button currently blocks on client-side `fieldErrors`. If it does, decide whether that should also be advisory-only for everything except malformed values.

**Tests.** Backend: a schema with `required` and an attributes dict missing the key validates cleanly. Frontend: schema editor emits `x-menagerist.required`, not `required`.


---

## Background (shared by WI-6 to WI-10)


- Editing a node type's `attributes_schema` never touches existing nodes (`update_node_type.py` only saves the type).
- `UpdateNode` validates the **entire** `attributes` dict against the current schema whenever `command.attributes` is not `None`, and the UI sends the full dict on every save. So any schema tightening can block saving an old node, even for fields the user did not touch.
- The backend enforces JSON Schema `required`. Adding a required field therefore makes every existing node of that type fail its next save. This contradicts the design decision that required fields are a soft visual signal that never blocks saving.
- Removing a field from the schema leaves its data in the JSONB (there is no `additionalProperties: false`). The attributes editor then shows the orphaned value under "Additional details", labelled with the raw UUID key. Re-adding the field creates a new UUID, so the old data does not reattach (WI-20 changes this: a re-added field with the same title gets the same readable key and reattaches).
- Schemas are shared instance-wide, so a type edit affects every node of that type.
