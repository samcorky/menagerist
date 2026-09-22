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
  /**
   * Friendly wording for a failed validation keyword (client and server errors), or null to fall
   * back to the validator's message. The text type words its own `pattern`s.
   */
  formatError?: (keyword: string, value: unknown) => string | null;
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
| `text` | `{ type: 'string' }`, optionally with an anchored `pattern` or an `allOf` of two (see "Text constraints") | ✅ type + pattern | Fallback — matched last |
| `number` | `{ type: 'number' }` | ✅ type | |
| `boolean` | `{ type: 'boolean' }` | ✅ type | |
| `date` | `{ type: 'string', format: 'date' }` | ✅ type + format | `jsonschema[format-nongpl]` validates ISO 8601 dates |
| `longtext` | `{ type: 'string' }` with `x-menagerist.kind: "longtext"` | ✅ type | Only matched by its explicit `kind`; the metadata is ignored by the validators |
| `choice` | `{ type: 'string', enum: [...] }` | ✅ enum membership | |
| `rating` | `{ type: 'number', minimum: 1, maximum: 5, multipleOf: 1 }` with `x-menagerist.kind: "rating"` | ✅ range + whole numbers | Star widget; only matched by its explicit `kind`, so it never captures a plain number. Unset is omitted. May be a group sub-field |
| `group` | `{ type: 'array', items: { type: 'object', properties: {...} } }` | ✅ structure + sub-fields | Sub-fields are validated recursively |

### Registration order in `index.ts`

```ts
// Most-specific string subtypes first so text doesn't match them:
import './date';        // string + format: date
import './longtext';    // string + kind: longtext (explicit kind only)
import './choice';      // string + enum
import './number';
import './rating';    // number + kind: rating (explicit kind only)
import './boolean';
import './text';        // plain string — fallback, must be last among scalars
import './group';       // after scalars so sub-field fromSchema lookups work
```

`descriptorForProp(prop)` first looks at `x-menagerist.kind`: an explicit kind is a direct registry lookup, and the property must still match that descriptor's `fromSchema`. Without a `kind` it picks the highest-ranked descriptor whose `fromSchema` matches (`FieldTypeDescriptor.rank`, default rank 1 when a descriptor doesn't declare one), ties broken by registration order in `index.ts`. No built-in kind currently declares a non-default rank, since none of their shapes overlap; a future kind that does overlap with an existing one (for example a multi-choice type sharing `enum` with `choice`) should declare a higher `rank` rather than relying on import order. Anything unrecognised (an unknown `kind`, a `kind` that does not fit the shape, or a shape no descriptor matches) becomes the non-selectable `opaque` kind and is preserved unchanged.

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

### Archived fields

`x-menagerist.archived: true` on a property hides the field while keeping its data. Frontend: `normalise()` skips it, the editors omit it from the layout and "Additional details", and `validationSchema()` drops it. Backend: `validation_schema()` drops it. `EditorField.meta` carries the flag through the schema editor, which keeps archived fields in a separate list and writes them back untouched.

### Deleting an archived field's data

The schema editor shows "Used by N items" (or connections) for each archived field and a "Delete data permanently" action, backed by `GET` and `DELETE /node-type/{id}/attribute/{key}` (and `/edge-type/...`). The purge is immediate and cannot be undone; removing the property from the type happens when the form is saved.

### Changing a field's kind

A saved field can only move to a kind listed in `frontend/src/lib/field-types/kind-changes.ts` (text and longtext swap; number, boolean, date and choice can become text; number and rating swap). Use "Replace" for anything else. New kinds must be added to that matrix.

### Display options ("Show as")

Add `displayOptions` to a descriptor to offer presentation styles: `{ key: 'display', label, choices, default }` stores the choice in `x-menagerist.display`; any other `key` is editor state (`EditorField.config`) that the descriptor maps to a validation keyword in `fromSchema` / `toSchema` (as the rating star count does with `maximum`). The widget reads `readPropMeta(prop).display` and falls back to the default.

### Text constraints (starts with, ends with)

A text field can require a prefix and/or a suffix. These change validity, so they are standard keywords, not `x-menagerist` members: one constraint is a single anchored `pattern` (`"^cover-"`), both are an `allOf` of two (`[{ "pattern": "^cover-" }, { "pattern": "\\.jpg$" }]`). Never merge them into one regex: `^a.*a$` would reject `a`, and the message could not say which half failed.

- The pattern is the only stored copy. `text/constraints.ts` writes it (`constraintKeywords`) and reads back exactly those forms (`parseConstraints`) into `EditorField.config` (`startsWith`, `endsWith`; group sub-fields use `EditorSubField.config`). Any other `pattern` or `allOf` is kept unchanged as `config.custom`, the two inputs are disabled and a note says so.
- Users never type a regex. Only literal text is escaped (`\ ^ $ . * + ? ( ) [ ] { } | /`, never `-`, because `\-` is invalid under the `u` flag).
- Two engines check the same pattern: Python `re.search` on the backend and `new RegExp(p, 'u')` in `@cfworker/json-schema`. Generated patterns behave identically in both, except that Python's `$` also matches before a trailing newline. Text typed into the form is single-line, so the difference is accepted. `contract/fixtures/regex-conformance.json` is read by both test suites, so they fail together if an engine disagrees.
- A pattern JavaScript rejects (for example one authored through the API) makes `validate()` throw. `createSafeValidator` catches that, skips the pattern rules and the attributes editor says some rules could not be checked; the server still enforces them. The backend already rejects uncompilable patterns when a type is saved (`check_schema`).
- An empty optional text field with a pattern is omitted from the payload (an empty string fails an anchored pattern), at the top level and in group rows.
- Errors: `formatError` turns a failed `pattern` into `Must start with "cover-"` or `Must end with ".jpg"` from the pattern itself, for client errors (`friendlyClientError`) and server errors (`friendlyServerError`, using the `keyword` and `value` the API now returns for every attribute error). Client errors appear after the field loses focus; server errors appear on save.
- Case-sensitive only. A stored value that no longer matches a newly added constraint never blocks saving other fields (changed-keys validation); editing that field re-validates it.

### Card highlights

`x-menagerist.highlights.card` is an ordered list of `{ "key": ... }` (at most 3) naming the fields a type shows on its cards. Read it with `readHighlights` and write it with `withHighlights` (`schema-meta.ts`); `normaliseHighlights` in `lib/highlights.ts` cleans a stored list, and `summaryItems(attributes, schema, surface)` returns the values to show for an item (empty ones skipped, the surface's limit applied). To make a new type highlightable, set `highlightable: true` on its descriptor and, if plain text is not enough, add `formatSummary(value, prop)` or a `SummaryWidget` (props `value`, `prop`, `size`). The schema editor keeps a 1-based `EditorField.highlight` rank on each field and writes the list through `itemsToSchema`; archiving a field clears it. The backend checks only the shape (`check_meta_shape`): at most 3 unique entries naming existing, non-archived properties.

### Attribute search

The item list's `q` also searches attribute values (see `docs/DECISIONS.md`). Backend: `search_excluded_keys(schema)` in `schema_meta.py` returns the top-level keys a search skips (archived, `x-menagerist.search: false`, and the kinds in `NON_SEARCHABLE_KINDS`, currently `rating`). `ListNodes` maps each item type slug to those keys and passes them to `NodeRepository.list` / `count` as `attribute_search_exclusions`. A new non-text kind should be added to `NON_SEARCHABLE_KINDS` and given `searchable: false` on its frontend descriptor. Frontend: `matchContext(item, schema, q)` in `lib/search-context.ts` applies the same rules to say why an item matched.

### Per-item details ("Add detail")

Keys an item's type does not define are edited as loose "details". `lib/attribute-rows.ts` holds the row model (`attributesToRows`, `rowsToAttributes`, `newDetailRow`): rows are ordered by name, keep a `kind` (`text`, `number`, `boolean`, `json`) and, for values the form cannot edit, the stored `raw` value. `lib/custom-details.ts` has the name rules (`customDetailProblems`, `isDetailRow`, `canAddDetail`) and the limits (`MAX_CUSTOM_NAME_LENGTH` 100, `MAX_CUSTOM_DETAILS` 50). The backend applies the same limits to new or changed details in `application/custom_details.py` (`check_custom_details`, called from `CreateNode` and `UpdateNode`; errors carry the keyword `customDetail`). A field the type defines is never a detail, archived ones included.

### Connection highlights

`x-menagerist.highlights.connection` on a relationship type's schema lists up to 2 fields shown on connection rows (`MAX_CONNECTION_HIGHLIGHTS`); the card list is separate. `readHighlights` / `withHighlights` take the list name (`'card'` or `'connection'`), `summaryItems(..., 'connection')` reads the connection list, and the schema editor takes `highlightList` (the relationships settings page passes `'connection'`). The backend shape check covers both lists (`check_meta_shape`).

### Per-item typed fields (`extra_schema`)

A node may carry `extra_schema`, a schema in the same shape as a node type's `attributes_schema`, adding fields to that one item only. `application/schema_meta.merge_attribute_schemas` combines a node's type schema and its `extra_schema` for validation; a key defined by both is rejected. `highlights` is not merged — only a type's own schema controls card highlights. There is no editor UI for `extra_schema` yet; it is reachable only through the API (`CreateNodeRequest`/`UpdateNodeRequest`/`NodeResponse`).

### Saved fields and lists (presets)

A `field` or `choice_list` preset can be saved from the schema editor ("Save for reuse" on a field; "Save these options as a list" on a choice field) and applied to another item type ("Add from saved fields…"; "Use a saved list"), via the new `presets` backend module (`POST /preset`, `GET /preset`, `PATCH /preset/{id}`, `DELETE /preset/{id}`). Applying copies the definition with a fresh key and writes `x-menagerist.origin: {preset, version}`; a choice field whose linked preset has a newer version shows "Update options" (with the existing in-use warning). Manage saved presets at `settings/saved-fields`. `$lib/presets.ts` holds the frontend conversion helpers (`fieldToDefinition`, `definitionToField`, `optionsToDefinition`, `listUpdateAvailable`).

### Table (group) column order

A `group` field's own `x-menagerist.columns` records its sub-property keys in order; `GroupInput`, `GroupView` and `fromSchema` all read it through `field-types/group/columns.ts`'s `orderedColumns(prop)` rather than `Object.entries`, because nested JSONB object keys are not stored in insertion order (verified against Postgres). A property with no `columns` falls back to `Object.entries` order.
