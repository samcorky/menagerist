# WI-14: Structured metadata, one `x-menagerist` namespace

> Part of the field-types spec. Read `00-INDEX.md` and `01-context-and-conventions.md` first (skip the second if this is that file).
> **Depends on:** WI-4 (the `opaque` kind handles an unknown `kind`).
> "WI-n" refers to `wi-*.md` files listed in `00-INDEX.md`; "open question N" refers to `open-questions.md`.


**Problem.** Non-validation metadata is scattered across flat vendor keywords: `x-multiline` and `x-layout` today, and the first drafts of WI-5, WI-6, WI-8 and WI-11 would have added `x-rating`, `x-required`, `x-archived` and `x-display`. That causes:
- No single place to read, write, strip or version the metadata, so every feature reaches into the schema directly.
- A field's identity is inferred from the shape of its JSON Schema (`fromSchema` guessing), which is why registration order and WI-12 exist at all.
- Name-clash risk. `x-required` reads too much like the API's existing OpenAPI extension `x-required-permission` (`permission_aware_route.py`); `x-logo` is also in use in the API docs. Those are unrelated to node-type schemas but confusing next to them.
- No version marker for future schema-format changes.

**Principle.** Standard JSON Schema keywords describe validation; `x-menagerist` describes everything else. Test: deleting every `x-menagerist` member from a schema must not change whether any value is valid. (So `minimum`, `maximum`, `enum` and `format` stay standard; `display`, `archived` and layout do not.)

**Shape.**

Schema root:
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": { "...": "..." },
  "x-menagerist": {
    "version": 1,
    "layout": [ { "key": "..." } ],
    "required": ["<field key>"]
  }
}
```

Each property:
```json
{
  "title": "Rating",
  "type": "number",
  "minimum": 1,
  "maximum": 5,
  "multipleOf": 1,
  "x-menagerist": { "kind": "rating", "display": "stars", "archived": false, "config": {} }
}
```

| Member | Level | Meaning | Item |
|---|---|---|---|
| `version` | root | Metadata format version, so future changes can be migrated | WI-14 |
| `layout` | root | Field ordering and containers (was `x-layout`) | WI-13 |
| `required` | root | Fields marked required. Advisory only, never sent to the validator | WI-6 |
| `highlights` | root | Fields whose values are shown on cards and pickers (display only) | WI-16 |
| `kind` | property | Explicit field type (`text`, `longtext`, `number`, `boolean`, `date`, `choice`, `group`, `rating`, …) | WI-14 |
| `display` | property | Presentation variant ("Show as") | WI-11 |
| `archived` | property | Soft-deleted; data kept, hidden from forms | WI-8 |
| `search` | property | `false` opts a field out of attribute search (default: searched) | WI-17 |
| `suggest` | property | `false` stops link and choice suggestions for this field (default: on) | WI-21 |
| `config` | property | Type-specific settings that do not affect validation (for example a currency code) | later types |

**Rules.**
- The editor always writes `kind`. When it is absent (for example a plain JSON Schema authored through the API) the type is inferred from standard keywords only (string, number, boolean, `enum`, `format: date`, array of objects), and anything else becomes opaque. With an explicit `kind`, lookup is a direct `getDescriptor(kind)`, and rating no longer has to win a shape race against number.
- An unknown `kind` (for example a future plugin kind that is not installed) maps to the `opaque` kind from WI-4, and the property is preserved untouched. Built-in kinds are unqualified; plugin kinds should be qualified (`plugin-id:kind`).
- Unknown members inside `x-menagerist` are preserved on round-trip, for forward compatibility.
- All access goes through one accessor module per side. Nothing else reads `x-*` keywords directly.

**No backwards compatibility (decision).** Old-format schemas are not migrated and there are no legacy readers. The old keys are simply replaced in the same change, and existing node types and edge types that use them are recreated or re-saved:

| Removed | Replaced by |
|---|---|
| `x-multiline: true` on a string property | `x-menagerist.kind: "longtext"` |
| `x-layout` at the root | root `x-menagerist.layout` |
| root `required` array | root `x-menagerist.required` (advisory only, WI-6) |

Consequence for a schema saved in the old format: its layout is ignored (fields render in schema key order), `x-multiline` fields render as single-line text, and required markers disappear, until the type is re-saved from the schema editor. No stored attribute data is affected. `x-rating`, `x-required`, `x-archived` and `x-display` were only first-draft names in WI-5, WI-6, WI-8 and WI-11 and never shipped.

**Implementation.**
- Frontend: add `frontend/src/lib/schema-meta.ts` with `SchemaMeta` and `PropertyMeta` types and `readSchemaMeta`, `readPropMeta`, `withSchemaMeta`, `withPropMeta`. Replace direct accesses in `schema-editor.svelte`, `attributes-editor.svelte`, `collection/[id]/+page.svelte`, `text.ts`, `longtext.ts` and `schema-types.ts`, and update the tests that mention `x-multiline` / `x-layout`. Add `'x-menagerist'?: PropertyMeta` to the `JsonSchemaProperty` variants, which also removes the need for a rating-specific variant.
- Registry: `descriptorForProp` uses `readPropMeta(prop).kind` first and falls back to inference from standard keywords. Each descriptor's `toSchema` writes its `kind`.
- Backend: add a small typed module next to `_validate_attributes.py` (for example `schema_meta.py`) exposing `required_keys(schema)` and `archived_keys(schema)`, and have `validate_attributes` use it to strip archived properties and the top-level `required`. Fully typed (`mypy --strict`), no I/O, so it stays in the application layer. Optionally validate the *shape* of `x-menagerist` when a node type or edge type is saved (object, known members correctly typed, unknown members allowed).
- No data migration and no compatibility shims (see the decision above).

**Acceptance.**
- A schema created in the editor round-trips through `schemaToItems` / `itemsToSchema` unchanged, including `kind`, `display`, `archived`, `layout` and `required`.
- For every fixture schema, validation results are identical with and without `x-menagerist`.
- No code outside the two accessor modules reads `x-*` keywords (enforce with a simple grep-style test).

**Tests.** Reader/writer round-trips; unknown members preserved; unknown `kind` becomes opaque; explicit `kind` overrides shape inference; a schema with no `x-menagerist` at all is inferred from standard keywords.
