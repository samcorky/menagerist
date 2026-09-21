# Field Types

New field types can be added without modifying any central switch/case in `schema-editor.svelte`, `attributes-editor.svelte`, or any backend handler.

---

## Frontend registry

### File layout

```
frontend/src/lib/field-types/
  registry.ts          ← register() / getDescriptor() / allDescriptors() / descriptorForProp()
  schema-types.ts      ← shared JsonSchemaProperty, AttributesSchema, EditorField types
  text.ts              ← plain string
  number.ts
  boolean.ts
  date.ts              ← string + format: date
  longtext.ts          ← string + explicit kind: longtext
  choice.ts            ← string + enum
  group.ts             ← array of objects
  ScalarInput.svelte   ← shared widget for text / number / date
  BooleanInput.svelte
  LongtextInput.svelte
  ChoiceInput.svelte   ← bits-ui Select
  ChoiceExtras.svelte  ← options tag-editor (EditorExtras)
  GroupInput.svelte    ← editable table of rows
  GroupExtras.svelte   ← sub-field list editor (EditorExtras)
  GroupView.svelte     ← read-mode table (ViewWidget)
  index.ts             ← side-effect imports in registration order
```

### `FieldTypeDescriptor` (from `registry.ts`)

```ts
import type { Component } from 'svelte';
import type { JsonSchemaProperty, EditorField } from '$lib/schema-types';

export type FieldTypeDescriptor = {
  kind: string;
  /** Label shown in the kind dropdown in schema-editor. */
  label: string;
  /**
   * Whether this type may appear as a group sub-field.
   * Set to false for types that cannot nest (choice, group).
   * Defaults to true.
   */
  canBeSubField?: boolean;
  /** Serialise an EditorField to a JSON Schema property. */
  toSchema: (field: EditorField) => JsonSchemaProperty;
  /**
   * Attempt to deserialise a JSON Schema property into an EditorField.
   * Return null if this descriptor does not match the property shape.
   * Registration order in index.ts determines precedence — most-specific first.
   */
  fromSchema: (key: string, prop: JsonSchemaProperty, required: boolean) => EditorField | null;
  /**
   * Optional extra controls rendered below the field row in schema-editor.
   * Used by choice (options list) and group (sub-field list).
   */
  EditorExtras?: Component<{ field: EditorField; onChange: (f: EditorField) => void }>;
  /** Widget rendered inside attributes-editor for data entry. */
  InputWidget: Component<{
    value: unknown;
    onChange: (v: unknown) => void;
    ariaLabel: string;
    prop: JsonSchemaProperty;
  }>;
  /** Optional widget for read-mode display. Falls back to String(value) when absent. */
  ViewWidget?: Component<{ value: unknown; prop: JsonSchemaProperty }>;
};
```

### Built-in field types and their JSON Schema shapes

| Kind | JSON Schema shape | Backend validated | Notes |
|---|---|---|---|
| `text` | `{ type: 'string' }` | ✅ type | Fallback — matched last |
| `number` | `{ type: 'number' }` | ✅ type | |
| `boolean` | `{ type: 'boolean' }` | ✅ type | |
| `date` | `{ type: 'string', format: 'date' }` | ✅ type + format | `jsonschema[format-nongpl]` validates ISO 8601 dates |
| `longtext` | `{ type: 'string' }` with `x-menagerist.kind: "longtext"` | ✅ type | Only matched by its explicit `kind`; the metadata is ignored by the validators |
| `choice` | `{ type: 'string', enum: [...] }` | ✅ enum membership | |
| `group` | `{ type: 'array', items: { type: 'object', properties: {...} } }` | ✅ structure + sub-fields | Sub-fields are validated recursively |

### Registration order in `index.ts`

```ts
// Most-specific string subtypes first so text doesn't match them:
import './date';        // string + format: date
import './longtext';    // string + kind: longtext (explicit kind only)
import './choice';      // string + enum
import './number';
import './boolean';
import './text';        // plain string — fallback, must be last among scalars
import './group';       // after scalars so sub-field fromSchema lookups work
```

`descriptorForProp(prop)` first looks at `x-menagerist.kind`: an explicit kind is a direct registry lookup, and the property must still match that descriptor's `fromSchema`. Without a `kind` it iterates the registry in insertion order and returns the first descriptor whose `fromSchema` returns non-null, so order matters — `text` would greedily match every string property if registered before `date` and `choice`. Anything unrecognised (an unknown `kind`, a `kind` that does not fit the shape, or a shape no descriptor matches) becomes the non-selectable `opaque` kind and is preserved unchanged.

---

## Adding a new field type

### Example: adding a `url` type

**1. Create `field-types/url.ts`:**

```ts
import { register } from './registry';
import UrlInput from './UrlInput.svelte';

register({
  kind: 'url',
  label: 'URL',
  canBeSubField: true,
  toSchema: (f) => ({ title: f.label, type: 'string', format: 'uri' }),
  fromSchema: (key, prop, required) =>
    prop.type === 'string' && 'format' in prop && prop.format === 'uri'
      ? { key, label: prop.title, kind: 'url', required, options: [], subFields: [] }
      : null,
  InputWidget: UrlInput,
});
```

**2. Create `UrlInput.svelte`** (a simple Svelte 5 component):

```svelte
<script lang="ts">
  import { Input } from '$lib/components/ui/input/index.js';
  let { value, onChange, ariaLabel }: { value: unknown; onChange: (v: unknown) => void; ariaLabel: string } = $props();
</script>

<Input
  type="url"
  value={typeof value === 'string' ? value : ''}
  oninput={(e) => onChange((e.target as HTMLInputElement).value)}
  aria-label={ariaLabel}
/>
```

**3. Register in `index.ts`** (before `text` since it also matches `string`):

```ts
import './url';   // add before text
import './text';
```

**4. Add the JSON Schema type to `schema-types.ts`** if the shape is new:

```ts
export type JsonSchemaProperty =
  | ...existing variants...
  | { title: string; type: 'string'; format: 'uri' };
```

---

## Backend alignment

### How validation works

All attribute validation runs through `application/_validate_attributes.py`:

```python
def validate_attributes(schema: dict[str, Any], attributes: dict[str, Any]) -> None:
    _cls = jsonschema.validators.validator_for(schema)
    validator = _cls(schema, format_checker=_cls.FORMAT_CHECKER)
    errors = [...]
    if errors:
        raise InvalidAttributesError(errors)
```

The backend uses `jsonschema[format-nongpl]` (see `pyproject.toml`) which registers checkers for all standard formats: `date`, `date-time`, `time`, `uri`, `email`, `ipv4`, `ipv6`, and more.

### When do you need to add backend code?

| Field type scenario | Backend work needed |
|---|---|
| Uses only standard JSON Schema keywords (`type`, `enum`, `properties`, `items`) | **None** — validated automatically |
| Uses a standard `format` string (`date`, `uri`, `email`, etc.) | **None** — covered by `jsonschema[format-nongpl]` |
| Uses a custom `format` string (e.g. `format: 'isbn'`) | **Yes** — register a format checker |
| Uses metadata in `x-menagerist` (e.g. `kind`, `display`) | **None** — unknown keywords are ignored by the validator |

### Registering a custom format checker

If you add a field type that uses a non-standard `format`, register a checker in the backend:

```python
# backend/src/app/platform/jsonschema_formats.py
import re
import jsonschema

@jsonschema.FormatChecker.cls_checks("isbn")
def _check_isbn(value: str) -> bool:
    return bool(re.fullmatch(r"97[89][- ]?[0-9]{10}", value.strip()))
```

Import the module in the API entrypoint for its side-effect:

```python
# backend/src/app/entrypoints/api/__init__.py
import app.platform.jsonschema_formats  # noqa: F401
```

No other changes are required — `_validate_attributes.py` picks up all registered checkers via `FORMAT_CHECKER`.

### Alignment checklist for a new field type

- [ ] `frontend/src/lib/field-types/<kind>.ts` — descriptor with `toSchema` / `fromSchema`
- [ ] `frontend/src/lib/field-types/<kind>-input.svelte` — `InputWidget` component
- [ ] (optional) `<kind>-extras.svelte` — `EditorExtras` for custom schema-editor controls
- [ ] (optional) `<kind>-view.svelte` — `ViewWidget` for read-mode display
- [ ] Add the shape to the `JsonSchemaProperty` union in `schema-types.ts` if new
- [ ] Register in `field-types/index.ts` at the correct position (most-specific first)
- [ ] **If using a custom `format`:** register a format checker in `platform/jsonschema_formats.py` and import it from the API entrypoint
- [ ] **No changes needed** to `schema-editor.svelte`, `attributes-editor.svelte`, or any application-layer handler

---

## The `x-menagerist` namespace

Standard JSON Schema keywords (`type`, `enum`, `format`, `minimum`, …) describe validation. Everything else lives under one `x-menagerist` member, at the schema root and on each property (including group sub-properties). Deleting every `x-menagerist` member never changes whether a value is valid, with two deliberate exceptions on the backend: the root `required` array and archived properties are stripped before validation (see below).

Root: `version` (metadata format, currently `1`), `layout` (field order and sections), `required` (fields marked required; advisory only, never validated).
Property: `kind` (the field type, always written by the editor), `display`, `archived`, `search`, `suggest`, `config`.

- Unknown members are preserved on round-trip.
- The frontend reads and writes the namespace only through `frontend/src/lib/schema-meta.ts`; the backend only through `backend/src/app/modules/graph/application/schema_meta.py`. Tests enforce that nothing else refers to it.
- There is no migration and no compatibility reader: `x-multiline`, `x-layout` and a root `required` array are ignored. Re-save an item type from the schema editor to move it to the new format.
- The backend validates the shape of known members when a node type or edge type is saved, and ignores a root `required` array and any property with `archived: true` when validating attributes.

### Field keys

A field's key (the name it has in `properties` and in a node's `attributes`) is generated by `frontend/src/lib/field-key.ts` from the title when a field is added, then never changes. A new field carries `keyPending: true` in the schema editor until the schema is saved, so its key tracks the label while it is being typed. Keys are opaque: nothing may parse meaning out of them. Older UUID keys remain valid.
