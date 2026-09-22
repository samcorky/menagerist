# WI-18: Per-item custom fields

> Part of the field-types spec. Read `00-INDEX.md` and `01-context-and-conventions.md` first (skip the second if this is that file).
> **Depends on:** WI-14, WI-20, WI-19d (overlay). WI-9 (usage endpoint) is no longer needed here — see the revision note below.
> "WI-n" refers to `wi-*.md` files listed in `00-INDEX.md`; "open question N" refers to `open-questions.md`.

> **Revision (2026-09-22, owner):** superseded below. 18a's loose-string stopgap and 18c's adopt-across-items flow are **dropped, not deferred** — no backwards compatibility, no legacy data to migrate (`decisions.md` already called 18a "a stopgap"). 18b is redefined against the WI-19d overlay instead of loose attributes. See "Revised design" below; the original text after it is kept for the reasoning it still explains (round-trip rules, interactions) but its 18a/18c sections no longer apply.

## Revised design (supersedes 18a and 18c below)

**Goal, unchanged.** A light-touch way to add a one-off, fully-typed detail to a single item, with a path into the node type when it keeps recurring — but the "one-off" field is typed from the start (any registry kind), not a loose string/number/boolean guess.

**"Add detail" becomes "Add field".** Every per-item extra is a property in the node's `extra_schema` (WI-19d overlay), for typed and untyped nodes alike (`merge_attribute_schemas(null, extra_schema)` already supports a type-less node). No more loose top-level attribute keys with no schema behind them.

- **Creation UI.** A shared `FieldKindRow.svelte` is extracted from `schema-editor.svelte`'s `fieldRow` snippet: label input, kind select (`kindOptions`, no `allowGroup` restriction), the kind's `displayOptions`, and its `EditorExtras` (choice options, text constraints, quantity, …). No highlight toggle, no replace/archive/save-preset controls — those stay type-only. `attributes-editor.svelte` uses it for "Add field": on confirm, generates a key the same way WI-20 does (slug of the label, unique across the type's `properties` *and* the node's `extra_schema` properties), appends the property to `extra_schema` (with its own `x-menagerist.layout` entry) and a default value to `attributes`.
- **Rendering.** Overlay fields render through the existing `fieldEntry` snippet, unchanged — they are ordinary properties with real widgets and real client-side validation, not a special case.
- **Removal.** Drop the property from `extra_schema` and the value from `attributes`, immediate with a 5-second Undo (same pattern as `removeWithUndo` in the schema editor). No archive, no usage count, no purge confirmation — an overlay field belongs to exactly one node, so none of the "how many items would this affect" machinery applies.
- **Limits.** Only the count limit carries over (50 fields per item, `MAX_EXTRA_SCHEMA_FIELDS`), checked against `extra_schema`'s property count. The 100-character name limit is dropped: an overlay field's label is an ordinary JSON Schema `title`, same as a ordinary schema field's, which has no length cap anywhere else in the app — keeping a special cap just for overlay labels would be an asymmetry with no purpose now that the key is slug-generated (WI-20), not the label itself.

**WI-18b: promote an overlay field to the item type.**
- Action on an overlay field, shown only when the node has a type: **Make this a field on `<item type>`**.
- New backend command `PromoteExtraSchemaField(node_id, node_type_id, key)`, in `graph/application`, composed the same way `upload_and_attach_media.py` composes `StageMedia`+`AttachMedia`: one `async with self._uow`, wrap `repos` in `JoinedUnitOfWork`, call `UpdateNodeType` to add the property (already validated — it was already a valid schema property in the overlay) to `attributes_schema`, then call `UpdateNode` to remove it from `extra_schema` (value in `attributes` is untouched — it already satisfies the property), one `commit()`. This has to be one transaction: two separate PATCH calls could leave the key defined in both places, which `merge_attribute_schemas` rejects as a collision on the node's next load.
- Key collision: if the type's schema already has a property with that key (or an archived one), the command raises the same way `UpdateNodeType` would for a duplicate key; the frontend surfaces it as an inline error and leaves the overlay field in place (open question: whether to auto-suffix instead — default to erroring for v1, matching "no silent rekey" elsewhere in this spec).
- Endpoint: `POST /node/{node_id}/attribute/{key}/promote` (`operation_id`: `promote_extra_schema_field`), body `{node_type_id}`, 200 with the updated node (or 204; match the router's existing convention for composite actions).

**Dropped: WI-18c (adopt across items, tips strip, `ListNodeTypeCustomAttributes`, `AdoptNodeTypeCustomAttribute`).** There is no loose-custom-detail data to adopt once 18a is gone, so "N items use a custom key" has no source. If a later need arises for "the same overlay label appears on many items, offer to promote it everywhere", that is new scope, not this item.

**Edges (owner, 2026-09-22): also lose ad-hoc fields, not just nodes.** `attribute-rows.ts`'s loose-detail machinery was shared by both the node and the edge (connection) attribute editors (`AttributesEditor`, used at the connection-edit dialog from WI-22a). The `extra_schema` overlay is nodes-only in v1 (`wi-19d-per-item-schema-overlay.md`), and there is no edge equivalent in this pass. Once 18a is removed, a connection can only have fields its relationship type's schema defines — "Additional details" on a connection is gone, not replaced. `AttributesEditor` becomes purely schema-driven: type fields plus, for nodes only, overlay fields; nothing freeform. If per-connection ad-hoc fields are wanted later, that is a new "overlay for edges" item, not this one.

**Files to remove (18a stopgap):** `frontend/src/lib/attribute-rows.ts`, `frontend/src/lib/custom-details.ts`, and their call sites/tests, plus the backend `application/custom_details.py` (`check_custom_details`) and its call sites in `create_node.py`/`update_node.py` (replaced by validating `extra_schema`'s own property/name/count limits, per "Limits" above).

---

## Original text (18a/18c superseded; kept for context)

**Goal.** Keep the light-touch way to add a one-off detail to a single item ("Add detail"), fix its rough edges, and give it a path into the node type when the same detail keeps recurring. This is the "progressive disclosure" step between free-form notes and a typed field.

**Current state (verified in `attributes-editor.svelte` and Postgres).**
- Any attribute key that is not in the schema layout is shown under "Additional details" (collapsed when the type has fields, flat when the node has no type) with an "Add detail" button. Each row is a free-text name and a free-text value. The name **is** the stored key.
- Rough edges:
  - Two rows with the same name silently overwrite each other on save (`Object.fromEntries`, last one wins). Rows with a blank name are silently dropped. Names are not trimmed.
  - Values are always strings. `attributesToRows` runs `String(value)` on everything, so a number or boolean set through the API becomes `"5"` or `"true"` on the next UI save, `null` becomes `"null"`, and a nested object becomes `"[object Object]"`.
  - There is no stable order: JSONB does not keep object key order. Verified: keys inserted as `zeta, Region, a-long-custom-name, aa, k1` come back as `aa, k1, zeta, Region, a-long-custom-name` (shorter keys first). Custom details therefore reshuffle after saving.
  - No limits on name length or on the number of custom details.
- Custom details are searched (WI-17 scans keys the schema does not define) and shown in read mode, but they cannot be highlighted (highlights are per type), validated (no schema) or typed beyond text.

**Decision: keep them as loose keys in `attributes`, with the label as the key** (field keys from WI-20 are lowercase slugs such as `region`; custom detail names keep their case, such as `Region`, and the editor treats the two as colliding). No new column, no migration and no API change for the core work. The label-as-key convention has a real benefit: search context and read mode show a human-readable name ("Matched in Region: EU"). A first-class `custom_fields` list (ordered, typed, renamable without touching the key) is the alternative if typed or ordered custom fields become a real need; it would need a migration and response-model changes. See open question 23, and WI-19d, which is the same decision seen from the presets side.

## WI-18a (superseded, see "Revised design" above): make the current behaviour safe (frontend, no backend change)

This is a **stopgap**. The design guidelines (§16b) say freeform fields use the same Name + Kind flow and the same kinds and widgets as schema fields, so fully compliant per-item fields are typed (WI-19d). Keep 18a small; WI-19d (overlay, decided) replaces the stopgap for new per-item fields.

- **Names.** Trim on entry. Reject (inline error, save blocked) a blank name that has a value, a name already used in this node (case-insensitive), and a name equal to **any** key in the schema's `properties`, including archived ones (otherwise a custom detail could revive hidden data). Length limit as a constant (proposal: 100 characters), and a cap on the number of custom details per node (proposal: 50).
- **Order.** Display custom details in a deterministic order (alphabetical, case-insensitive), because insertion order cannot be persisted.
- **Lossless round-trip.** Custom keys are edited as text only when their stored value is a string. A number or boolean keeps its type: offer a small kind choice when adding a detail (Text, Number, Yes/No) and store real JSON numbers and booleans. Anything the UI cannot edit (null, nested objects, arrays of scalars) is shown read-only as compact JSON and written back **unchanged**, never stringified.
- **Backend guard.** Add the same limits (name length, count, non-blank trimmed names) as a domain invariant on `Node`, so API clients cannot bypass them. Keys defined by a schema are unaffected.
- No new kinds here: date, rating, choice and the rest only exist as type fields. That is the reason for 18b.

## WI-18b (superseded, see "Revised design" above): "Add to <item type> fields" (promote a custom detail, this node only)

- Action on each custom detail when the node has a type: **Make this a field on <item type>**. It opens a small form: label (prefilled from the name), kind (prefilled from the value's shape: number, boolean or text), then confirm.
- **Backend flow, one transaction.** The same `AdoptNodeTypeCustomAttribute` command as WI-18c, scoped to this node (`node_ids=[this node]`): it adds the new property to the item type and moves this node's value from the name to the new key (WI-20), coerced to the kind. If the value does not fit, say so and keep it as a custom detail. A two-call frontend flow (update the type, then update the node) would work but is not atomic and can leave a half-done state, which this repo's composition pattern (`JoinedUnitOfWork`) exists to avoid.
- Not available for nodes without a type (there is no schema to add to). Whether to offer "create a type from these details" is out of scope (open question).

## WI-18c (dropped, see "Revised design" above): adopt across items and suggest promotions (backend)

- **Custom names in use.** Query `ListNodeTypeCustomAttributes`: top-level keys used by nodes of a type that the type's schema does not define, with counts, most used first. Verified on Postgres with `jsonb_object_keys` grouped and filtered by `NOT (k = ANY(:schema_keys))`.
- **Adopt.** Command `AdoptNodeTypeCustomAttribute(node_type_id, from_key, property, node_ids | None)`: adds `property` (a new key from WI-20 plus its definition) to the item type's schema and moves every matching node's value from `from_key` to that key, only where the value validates against the new property; it returns `{moved, skipped}`. Verified that a rekey (`(attributes - 'Region') || jsonb_build_object(:to_key, attributes->'Region') WHERE attributes ? 'Region'`) touches only nodes of that type.
  - Implement it in the application layer by paging through the affected nodes and updating each through the unit of work (validate the value with the property's schema, then `node.update`), not as a single SQL statement. That keeps per-node validation and bumps each node's `updated_at`/ETag, which a raw JSONB update would skip. Compose the existing `UpdateNodeType` and `UpdateNode` handlers through `JoinedUnitOfWork` so the schema change and every node update share one transaction (the pattern `upload_and_attach_media.py` already uses).
  - Reuses the WI-9 usage count (`.../attribute/{key}/usage`, which works for any key including a human-readable label) to show "Used by N items" before confirming.
- **UI.** In the schema editor (Settings) only, a passive "Tips" strip: "'Region' is used on 12 items. Make it a field?" It is never shown while browsing or editing items, because §16b says the app should not nag users to formalise custom fields (open question 44). Choosing it pre-fills the add-field form and offers **Also move the value on the other N items**. Only shown for names used on at least a few items (constant).
- **Endpoints (proposal, matching the existing router style).** `GET /node-type/{node_type_id}/custom-attribute` (`operation_id`: `list_node_type_custom_attributes`, returns `[{key, count}]`) and `POST /node-type/{node_type_id}/attribute/{key}/adopt` (`operation_id`: `adopt_node_type_custom_attribute`, body `{from_key, property, node_ids?}`, returns `{moved, skipped}`). Edge types mirror them if edge custom details are supported (open question).
- Authorisation follows the same decision as WI-9 (open question 17).

## Interactions (superseded; see the revised design's own interactions below)

- WI-17: custom details are searched and never excluded; the match context uses the name as the label.
- WI-16: not highlightable while they are custom. Promoting one (18b/18c) is how a detail gets highlighted.
- WI-7: no schema means no validation errors for custom keys, so they never block a save.
- WI-8: archived keys must be excluded from the "Additional details" list and from the name-collision check (18a).
- WI-9: the usage and purge endpoints work on custom names too (`key` is just a string), so "delete this custom detail from every item of this type" needs no extra work beyond a UI.

**Acceptance (superseded).**
- Adding two details with the same name shows an inline error and does not save; the name is trimmed.
- A number set through the API in a custom key is still a number after editing another field in the UI; null and nested values survive a save unchanged.
- Custom details keep a stable alphabetical order after reload.
- 18b: promoting a text detail to a Rating (or Date) field on the type moves the value, and the value shows in the type field instead of "Additional details".
- 18c: adopting a label used on 12 items moves compatible values, reports skipped ones, and leaves nodes of other types untouched.

**Tests (superseded).** 18a: name validation (blank, duplicate, case-insensitive, equal to a schema key including an archived one), ordering, lossless round-trip for number, boolean, null, object and array values, the domain limits. 18b: promotion flow with a fitting and a non-fitting value. 18c: unit (in-memory) and integration `I-8` for the listing query, the rekey and the skipped-value handling; ETag changes on moved nodes; end-to-end flow of promoting a detail.

## Revised interactions, acceptance and tests (current)

**Interactions.**
- WI-17: overlay fields are ordinary schema properties, so they are searched and excluded exactly like type fields (`search: false` honoured, WI-17's existing per-type exclusion logic extends to the merged schema).
- WI-16: overlay fields are not highlightable (highlights stay type-only, `wi-16-highlighted-fields.md`); promoting one to the type (18b) is how it becomes eligible.
- WI-7: `UpdateNode`'s changed-keys validation applies to `extra_schema` edits the same as `attributes_schema` edits.
- WI-8/WI-9: do not apply to overlay fields (single node, no archive, no usage/purge) — only to the type's own schema, unchanged.
- WI-20: key generation for a new overlay field must check uniqueness against both the type's `properties` (including archived) and the node's own `extra_schema` properties.

**Acceptance.**
- Adding a field of any registry kind to an item without a type works and round-trips (label, kind, constraints, value).
- Removing an overlay field drops both the property and its value, with a working 5-second Undo.
- Promoting an overlay field moves the property into the item type's schema in one request; the node's `extra_schema` no longer defines the key; the value is unchanged and now shows as a type field; other nodes of the type are unaffected.
- Promoting a key that collides with an existing (including archived) type property fails with an inline error and leaves the overlay field in place.

**Tests.** Backend: `PromoteExtraSchemaField` unit tests (success, key collision, node without the key, node without a type), integration test for the merged-transaction move (schema updated and node's `extra_schema`/`attributes` correct after commit, ETag/`updated_at` bumped on both), router test for the endpoint. Frontend: `FieldKindRow` extraction (kind options, display options, extras) tested once and reused; `attributes-editor` tests for add/remove/promote on the overlay, key-uniqueness against both schemas, and the untyped-node case.
