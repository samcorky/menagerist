# WI-19d: Typed per-item fields via a node schema overlay (decided)

> Part of the field-types spec. Read `00-INDEX.md` and `01-context-and-conventions.md` first (skip the second if this is that file).
> **Depends on:** WI-14, WI-20, WI-18. Read `wi-19-presets.md` for how presets use it.
> "WI-n" refers to `wi-*.md` files listed in `00-INDEX.md`; "open question N" refers to `open-questions.md`.


Koillection stores typed fields on each item. The Menagerist equivalent is a nullable `extra_schema` on each node, in the same JSON Schema shape as a node type (properties with `x-menagerist`, layout array for order), validated together with the type's schema.

- **Benefits:** reuses the registry, editor, validation and search unchanged; per-item typed fields (rating, date, choice with options); and promoting one to the type becomes a **move** of the property, because the key is already unique within the item type (the editor checks it against the type's keys when promoting and appends a numeric suffix or rekeys on a clash), so almost no rekey is needed and WI-18c would shrink to "move the definition, keep the values".
- **Costs:** a migration (nullable column on nodes, possibly edges); `NodeResponse`, create and update models change; `validate_attributes` must merge the two schemas and reject key collisions; highlights stay type-only; and definitions are duplicated across nodes and can drift (mitigated by the WI-18 suggestions strip).
- **Decided:** the overlay is the storage model for typed per-item fields, as the design guidelines (§16b, §26) require (open questions 23 and 33 are closed). WI-19a to WI-19c do not depend on it.
- **v1 scope:** nodes only, not edges. Definitions in the overlay are ordinary properties, so every kind, `display`, constraint and layout option works per item.
- **Consequences for other items:** WI-18a's Text/Number/Yes-No limit for new details disappears (all kinds are available per item); WI-18b becomes "add to item type" by *moving* the overlay property into the type's schema, with values untouched; WI-18c's adopt stays for API-authored and legacy loose keys; and keys added to an overlay must be unique across both the type's schema and the overlay (WI-20 generator checks both).
