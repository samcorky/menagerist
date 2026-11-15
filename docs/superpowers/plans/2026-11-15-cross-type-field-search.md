# Cross-type field search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Search conditions that reach a field on every item type, by key + kind or by saved-field origin. Then wishlist status (#241) and acquisitions (#349) ship as content.

**Architecture:** A pure application-layer pass (`field_scope_expansion.py`) rewrites each cross-type field condition into an `or` of typed leaves (plus, for key + kind, the existing overlay leaf) before `resolve_fields`. It runs in `prepare_query` and in `_Expander.smart`. Adapters are unchanged.

**Tech Stack:** Python 3.14 / FastAPI backend, SvelteKit + Svelte 5 frontend, shared JSON contracts.

**Spec:** `docs/superpowers/specs/2026-11-15-cross-type-field-search-design.md`

## Global Constraints

- `graph` must not import `presets`. The origin is compared as a string from `x-menagerist.origin.preset`.
- 100% coverage for domain and application. Strict mypy. Strict svelte-check.
- British English. No node/edge/graph words in UI copy (design §24).
- Stacked PRs: (1) backend + codec, (2) builder UI, (3) content. Commits and PR bodies carry no Claude attribution.

## Review Focus

- A choice value that exists on one type but not another still matches the types that have it. No error, because option lists aren't checked.
- `!=` / `not_in` across types never returns items lacking the field (scoped per leaf).
- A type added after a smart collection was saved is matched without re-saving.
- A cross-type condition inside a smart collection nested in another is expanded once, not twice.
- An `origin` whose copies have different kinds keeps only the leaves whose kind accepts the operator and value. If none do, it is refused at the original path.

---

### Task 1 (PR 1): Query shape and expansion

**Files:**
- Modify: `backend/src/app/modules/graph/domain/query.py` (`FieldCondition.origin`, `_field_condition`, `_CONDITION_KEYS`)
- Create: `backend/src/app/modules/graph/application/field_scope_expansion.py`
- Modify: `application/prepare_query.py`, `application/collection_expansion.py`, `application/query_resolution.py` (`_resolve_field` refuses unexpanded `origin`)
- Modify: `shared/contracts/query-shapes.json`, `frontend/src/lib/query/codec.ts`, `frontend/src/lib/query/types.ts`
- Test: `backend/tests/modules/graph/application/test_field_scope_expansion.py`, search tests in-memory + Postgres

**Interfaces:**
- Produces: `expand_field_scopes(where: Group | None, schemas: Mapping[str, Mapping[str, Any]]) -> Group | None`. Raises `InvalidQueryError` at the condition's path for an operator or value that fits no matched kind.
- Shape: exactly one of `type`, `field_kind`, `origin`. `key` is required except with `origin`. `sub_key` is allowed with all three. `ref` only with `type`.

- [ ] Contract cases: valid `field_kind` + `sub_key`, valid `origin`, valid `origin` + `sub_key`. Invalid: `origin` + `type`, `origin` + `key`, `origin` + `ref`, empty `origin`. Remove the "per-item field with a sub_key" invalid case.
- [ ] Expansion tests: two types sharing `status`/choice give `or(type A leaf, type B leaf, overlay leaf)`. Archived and other-kind properties are skipped. `sub_key` gives table columns only, with no overlay leaf. `origin` matches properties by `origin.preset`. No match gives an empty `or` (matches nothing). Kind mismatch for every match raises.
- [ ] Search tests (in-memory and Postgres): Film and Game items with `status`, plus an untyped item with an overlay `status`, are all found by one condition. `!=` excludes items with no field. A smart collection holding the condition picks up a type created afterwards.
- [ ] Implement. Run `poe test-backend-fast --mode agent`, targeted search tests, then `poe test-frontend --mode agent` for the codec.
- [ ] DECISIONS entry and update to the 2026-10-16 entry. Commit, push, PR 1.

### Task 2 (PR 2): Search builder

**Files:** `frontend/src/lib/query/fields.ts`, `builder.ts`, `summary.ts`, `components/query-condition-row.svelte` and siblings as needed; their tests.

- [ ] The "Per-item fields" group becomes "Any item type". Its rows are key + kind pairs merged from loaded type schemas and `GET /node/item-fields`, labelled by the most common title.
- [ ] A "Saved fields" group lists `field` presets. Choosing one writes `{kind: 'field', origin: id, op}`. Its kind and options come from the preset's property.
- [ ] Chips and summary name the field and say "any item type" or "saved field".
- [ ] `poe test-frontend`, `poe lint-frontend`, `poe typecheck-frontend`. Commit, push, PR 2.

### Task 3 (PR 3): Content

**Files:** `backend/src/app/modules/catalogue/entries/field-status.json` (new), `field-acquisition.json` (new), `group-purchase-details.json` (removed), catalogue index/tests, example packs.

- [ ] Status: choice, Owned and Wanted, no default.
- [ ] Acquisition: table with Date (partial date), Price (money), Source (text), How (choice: Bought, Gift, Inherited, Traded) and Notes (long text).
- [ ] Packs: add Status / Acquisition to fitting types, and a "Wanted" smart collection using `field_kind`.
- [ ] Check the table field's highlight on cards. Fix it generally only if broken.
- [ ] Catalogue/pack tests, `poe coverage`. Commit, push, PR 3.
