# Considered and not adopted: JSON Forms

> Part of the field-types spec. The finished work items and reference files are in git history.
> **Type:** reference file (no work to do).
> "WI-n" refers to `wi-*.md` files (finished ones are in git history); "open question N" refers to `open-questions.md`.


Reviewed September 2026. Do not re-litigate this without a new driver.

- **No shadcn-svelte renderer set.** The Svelte 5 port (`@chobantonov/jsonforms-svelte`) is a community package with a first public release that ships Flowbite and Skeleton renderer sets. We would write every renderer ourselves, which is what the field-type registry already is.
- **Wrong half of the problem.** JSON Forms renders forms from a schema. This spec's hard parts are authoring and evolution (schema editor, archive, purge, soft `required`, changed-keys validation), which it does not cover.
- **Layout split.** JSON Forms keeps layout in a separate UI schema. We store layout inside the schema (`x-menagerist.layout`), so adopting it means two documents to keep in sync or a translation layer.
- **Validation.** As far as I know its core validates with Ajv by default, which the attributes editor just dropped (`02696ec`) in favour of `@cfworker/json-schema`.
- **Revisit if** we later want conditional rules (show or hide a field based on another field's value). Its rule engine handles that well, and it could replace input rendering only, not the schema editor.

The three ideas worth borrowing are called out in WI-11 (per-control display options), WI-12 (rank-based matching) and WI-13 (layout vocabulary: vertical, horizontal, group, categorization).
