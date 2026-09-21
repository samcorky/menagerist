# WI-7: Validate only the attributes that changed

> Part of the field-types spec. Read `00-INDEX.md` and `01-context-and-conventions.md` first (skip the second if this is that file).
> **Depends on:** None technically; do after WI-6 (both change `_validate_attributes.py`).
> "WI-n" refers to `wi-*.md` files listed in `00-INDEX.md`; "open question N" refers to `open-questions.md`.


**Problem.** See "Current behaviour". Untouched stale values (removed enum option, changed field kind, tightened constraint) block unrelated edits.

**Spec.** In `UpdateNode` and `UpdateEdge`, only report validation errors for top-level attribute keys whose value differs from the stored value.
- Extend the helper: `validate_attributes(schema, attributes, *, previous: dict[str, Any] | None = None)`. With `previous=None` (create) behaviour is unchanged. With `previous` set, run the same full validation, then drop any error whose first path segment is a key with `attributes.get(k) == previous.get(k)`, using deep equality (group values are lists of dicts). `InvalidAttributesError` is raised only if errors remain.
- Errors with an empty path (root-level, for example a type error on the whole object) are always kept.
- Create paths (`create_node`, `create_edge`) keep full validation.
- Keep this in the application layer next to `_validate_attributes.py`. No new infrastructure and no port changes.

**Acceptance.** A node holding a value that no longer matches the schema can still be saved when the user edits only the name or a different field. Editing the invalid field to another invalid value still errors.

**Tests** (unit, no DB): unchanged invalid key is ignored; changed invalid key errors; changed valid key passes; group value deep-equality; create still validates everything.


---

## Background (shared by WI-6 to WI-10)


- Editing a node type's `attributes_schema` never touches existing nodes (`update_node_type.py` only saves the type).
- `UpdateNode` validates the **entire** `attributes` dict against the current schema whenever `command.attributes` is not `None`, and the UI sends the full dict on every save. So any schema tightening can block saving an old node, even for fields the user did not touch.
- The backend enforces JSON Schema `required`. Adding a required field therefore makes every existing node of that type fail its next save. This contradicts the design decision that required fields are a soft visual signal that never blocks saving.
- Removing a field from the schema leaves its data in the JSONB (there is no `additionalProperties: false`). The attributes editor then shows the orphaned value under "Additional details", labelled with the raw UUID key. Re-adding the field creates a new UUID, so the old data does not reattach (WI-20 changes this: a re-added field with the same title gets the same readable key and reattaches).
- Schemas are shared instance-wide, so a type edit affects every node of that type.
