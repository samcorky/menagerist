# WI-11: "Show as" display options

> Part of the field-types spec. Read `00-INDEX.md` and `01-context-and-conventions.md` first (skip the second if this is that file).
> **Depends on:** WI-14 (`display`, `config`).
> "WI-n" refers to `wi-*.md` files listed in `00-INDEX.md`; "open question N" refers to `open-questions.md`.


**Prior art (borrowed idea 1 of 3).** JSON Forms drives presentation from per-control `options` in its UI schema (for example an enum rendered as radio buttons instead of a dropdown) without changing the data schema. `x-menagerist.display` below is the same idea, kept inside our single schema. Keep the naming close to that convention where it costs nothing.

**Decision direction.** Keep one field type per stored data shape and vary presentation through a per-field setting, rather than creating separate types that store the same data. Separate types would clutter the kind picker and compete in `fromSchema`, because the kind is inferred from the schema's shape.

**Storage (proposal).**
- `EditorField` gains an optional `config?: Record<string, unknown>`.
- Persisted as `display` (a string) inside the property's `x-menagerist` object (WI-14) for display style, plus type-specific keywords where the value affects validation (for example `maximum` for the star count).
- `FieldTypeDescriptor` declares its options, for example `displayOptions?: { key: string; label: string; choices: { value: string; label: string }[]; default: string }[]`. The schema editor renders a "Show as" dropdown automatically from that, so a new display style is one entry plus one widget branch.
- Widgets read the setting from `prop` (`readPropMeta(prop).display`), so `fromSchema` never needs to change for display-only settings and there is no shape-matching conflict.

**First users.**

| Type | Show as | Notes |
|---|---|---|
| Boolean (Yes/No) | Switch (default, per the design guidelines) / Checkbox / Yes-No buttons | True/False is a wording choice, put it in the label. Yes/No buttons can be cleared to "not recorded", which matters for values like "Signed?". A plain checkbox cannot distinguish "no" from unset. |
| Choice | Dropdown (default) / Radio buttons / Button chips | Radio buttons are a display of Choice, not of boolean. |
| Rating | Number of stars (3, 5, 10) | Sets `maximum`. |

**Acceptance.** Changing "Show as" changes only the widget; stored values and validation are unaffected. Existing schemas without `display` render with each type's default.

**Tests:** descriptor `displayOptions` drive the editor dropdown; `display` round-trips; default rendering unchanged.
