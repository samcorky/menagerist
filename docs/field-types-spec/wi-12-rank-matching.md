# WI-12: Rank-based descriptor matching (optional)

> Part of the field-types spec. Read `00-INDEX.md` and `01-context-and-conventions.md` first (skip the second if this is that file).
> **Depends on:** WI-14. Optional; only if more overlapping kinds are scheduled.
> "WI-n" refers to `wi-*.md` files listed in `00-INDEX.md`; "open question N" refers to `open-questions.md`.


**Prior art (borrowed idea 2 of 3).** JSON Forms chooses a renderer by scoring each renderer's "tester" against the schema and taking the highest rank, rather than depending on registration order.

**Problem.** `descriptorForProp` and `propertyToField` currently return the first descriptor whose `fromSchema` is non-null, so correctness depends on the import order in `field-types/index.ts` (rating before number, multi-choice before group, text last). A wrong import order fails silently.

**Spec (proposal).**
- Add an optional `rank?: (prop: JsonSchemaProperty) => number` to `FieldTypeDescriptor`, where `0` means "does not match". If absent, derive it from `fromSchema`: non-null gives rank `1`, null gives `0`.
- `descriptorForProp` (and `propertyToField` in `schema-editor.svelte`) pick the highest rank; ties are broken by registration order.
- Specific types declare a higher rank than generic ones (for example rating and date above number and text). `text` stays the lowest-ranked match, so the comment about import order becomes unnecessary.
- `fromSchema` is unchanged and still builds the `EditorField`.

**Acceptance.** Shuffling the import order in `index.ts` does not change which descriptor matches any property.

**Tests** (`tests/field-types.test.ts`): existing `descriptorForProp` cases pass unchanged; a test registers descriptors in reverse order and asserts identical matches; a tie is resolved by registration order.

**Decide before implementing.** After WI-14, an explicit `x-menagerist.kind` bypasses matching entirely, so ranking only decides for properties with no kind (API-authored). That shrinks the value of this item further. It is worth doing only if more overlapping types are coming (multi-choice, partial date, identifier, and URL/email all overlap with `text` or `array`). If only rating is added, the ordering comment is enough.
