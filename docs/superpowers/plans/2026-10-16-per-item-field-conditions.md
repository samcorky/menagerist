# Per-item field conditions (phase 1b) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a search filter on the fields an individual item carries in its own `extra_schema` overlay, and let the filter builder offer them in a "Per-item fields" group.

**Architecture:** A field condition names either an item type (`type`, today) or a field kind (`field_kind`, new), never both. A per-item condition applies to an item whose own overlay declares that key with that kind and has not archived it; the value test is the existing one on `attributes[key]`. A new read lists the per-item fields in use. No query version bump.

**Tech Stack:** FastAPI, SQLAlchemy/Postgres JSONB (GIN `jsonb_path_ops`), SvelteKit 5 runes, shadcn-svelte, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-14-smart-collections-advanced-search-design.md`, phase 1b. Phase 1 plan for conventions and rulings: `docs/superpowers/plans/2026-10-14-query-engine-advanced-search.md`; rulings R1-R13 are in `.superpowers/sdd/2026-10-14-query-engine-advanced-search/progress.md`.

## Global Constraints

- Dependency direction `entrypoints → adapters → application → domain`; `domain/` imports only the allow-listed stdlib modules (no new ones); classes in `graph/application/` are handlers or named `*Command/*Query/*Result/*Permission`.
- The Python evaluator is the reference; the SQL compiler must agree on every scenario in `test_node_search.py` (runs on both adapters).
- Svelte files (`.svelte`, `.svelte.ts`) go through the `svelte:svelte-file-editor` agent. British English. No "node", "edge" or "graph" in user-visible text.
- Domain and application stay at 100% line and branch coverage. Run only relevant checks via `uv run poe ...`.
- No agent runs `git add` or `git commit`; the user commits after each task.
- Shared contracts in `shared/contracts/` are read by both test suites; a change to the query format updates `query-shapes.json` only with cases both sides agree on.

## Review Focus

- **A per-item key that equals a type key on another type** (`weight` on a Game type, `weight` as a Film item's own field): the condition must match only items whose own overlay declares it, never the Game's type field.
- **Archived per-item field:** matches nothing.
- **Same key, different kinds on different items** (`size` as number on one item, text on another): conditions name the kind; each matches only its own items; the listing returns two rows.
- **Complements (`!=`, `not_in`, `empty`) and `not`:** scoped to items that declare the field, so "Signed != yes" never returns items that have no such field.
- **An item with no overlay (`extra_schema` NULL):** never matches, never errors.
- **Hostile input:** `field_kind` that is not a known kind, a `sub_key` or `ref` operand on a per-item condition, both `type` and `field_kind`, neither: all 400 with a path.

## Rulings made while planning

- **R14:** Only fields with an explicit `x-menagerist.kind` are filterable per item. The listing omits inferred-kind fields (API-made overlays); editor-written overlays and promotions always carry a kind. Cost if wrong: such fields are searchable by text only, as today.
- **R15:** No stale warning for a per-item condition: with no item declaring the field it simply matches nothing, and the builder flags a key absent from the listing. Cost if wrong: no server-side warning text for this case.
- **R16:** Per-item conditions cannot use a table column (`sub_key`) or a field reference (`ref`), and per-item sorting is out of scope. Cost if wrong: add later; the format is additive.

---

### Task 1: Parse and validate per-item conditions (domain and application)

**Files:**
- Modify: `backend/src/app/modules/graph/domain/query.py` (`FieldCondition`, `_field`)
- Modify: `backend/src/app/modules/graph/application/query_resolution.py` (`_resolve_field`)
- Modify: `shared/contracts/query-shapes.json`, `shared/README.md`
- Test: `backend/tests/modules/graph/domain/test_query.py`, `backend/tests/modules/graph/application/test_query_resolution.py`

**Interfaces:**
- Produces: `FieldCondition(type: str | None, key, op, value, sub_key, field_kind: str | None = None)` with the invariant exactly one of `type` / `field_kind` is set; wire form `{"kind": "field", "key": "signed", "field_kind": "boolean", "op": "=", "value": true}` (no `type`).
- Consumes: `KIND_OPERATORS`, `REF_KINDS`, `NO_VALUE_OPERATORS`, `_check_value` (unchanged signature).

- [ ] **Step 1: Write failing tests.** Parser: a per-item condition parses to `FieldCondition(type=None, field_kind="boolean", ...)`; rejects with a path: both `type` and `field_kind`, neither, `field_kind` not a string or unknown to the parser, `sub_key` present with `field_kind`, a `{"ref": ...}` operand with `field_kind`. Resolution: wrong operator for the kind (`>` on `boolean`) is a 400; a value of the wrong shape is a 400; a valid condition yields no warnings, no entry in `FieldResolution.kinds` and is not stale (R15).
- [ ] **Step 2: Run, expect failure.** `cd backend && uv run pytest tests/modules/graph/domain/test_query.py tests/modules/graph/application/test_query_resolution.py -q`
- [ ] **Step 3: Implement.** In `domain/query.py`:

```python
@dataclass(frozen=True, kw_only=True)
class FieldCondition:
    """Compare a field of one item type, or a per-item field by its kind.

    `type` addresses a field of an item type; `field_kind` addresses a field an
    item declares in its own overlay. Exactly one is set. `sub_key` addresses a
    table column and is only valid with `type`.
    """

    key: str
    op: str
    type: str | None = None
    field_kind: str | None = None
    value: Operand | None = None
    sub_key: str | None = None
```

In `_field`, read both, require exactly one (`InvalidQueryError("Name an item type or a field kind, not both.", path=path)` / `"Name an item type or a field kind."`), reject `sub_key` with `field_kind`, and reject a `FieldReference` anywhere in the parsed value when `field_kind` is set. The set of known kinds is the application's `KIND_OPERATORS`; the domain cannot import it, so the parser only checks `field_kind` is a non-empty string within `MAX_TEXT_LENGTH`; `_resolve_field` rejects unknown kinds with `InvalidQueryError("Unknown field kind.", path=path)`. Update every constructor call and type use of `FieldCondition.type` (grep `\.type` in `query_resolution.py`, `query_eval.py`, `query_sql.py`, `search_nodes.py`): in `_resolve_field`, when `condition.field_kind` is set, skip `_find`, take `kind = condition.field_kind`, run the existing operator and `_check_value` checks, and return False without touching `kinds`.
- [ ] **Step 4: Fixture cases.** Add valid and invalid per-item cases to `shared/contracts/query-shapes.json` only after Task 4 teaches the frontend decoder; until then put them in the backend tests and note it in the report. Document the new form in `shared/README.md`.
- [ ] **Step 5: Run, expect pass, then** `uv run poe lint-backend && uv run poe typecheck-backend && uv run poe test-backend`; check 100% line and branch coverage of `query.py`, `query_resolution.py`.

**Checkpoint:** user may commit.

---

### Task 2: Evaluate and compile per-item conditions

**Files:**
- Modify: `backend/src/app/modules/graph/adapters/persistence/query_eval.py` (`_field_matches`)
- Modify: `backend/src/app/modules/graph/adapters/persistence/query_sql.py` (`_field`, `_field_test`)
- Create: `backend/src/app/alembic/versions/<rev>_extra_schema_index.py` (head is currently `s0b1c2d3e4f5`; check `alembic heads` first)
- Modify: `backend/src/app/modules/graph/adapters/persistence/models.py` (declare the index)
- Test: `backend/tests/modules/graph/adapters/persistence/test_node_search.py`, `backend/tests/platform/test_query_indexes_migration.py` or the closest existing index test

**Interfaces:**
- Consumes: Task 1's `FieldCondition`. Both adapters take the kind from `condition.field_kind`, not from `ctx.field_kinds`, when it is set.
- Produces: the scope predicate "the item's own overlay declares `key` with this kind and does not archive it".

- [ ] **Step 1: Write failing scenarios** in `test_node_search.py` (run on both adapters). Seed items whose `extra_schema` declares: `signed` (boolean), `size` (number) on one item and `size` (text) on another, an archived `condition` field, plus a Game-type item whose *type* defines `weight`, and a Film item whose overlay defines its own `weight` (number). Scenarios: per-item boolean `=`; per-item number `>=`; `size` as number matches only the number item and `size` as text only the other; the archived field matches nothing; `weight` per-item number matches the Film's own field and not the Game's type field; `!=` and `not_in` match only items that declare the field (an item without it never matches); `empty` / `not_empty` scoped likewise; `not` wrapping a per-item condition; an item with `extra_schema` NULL never matches and never errors; a per-item condition inside an `or` with a type condition; paging/ordering unchanged.
- [ ] **Step 2: Run, expect failure** (`uv run pytest tests/modules/graph/adapters/persistence/test_node_search.py -q`; Postgres cases need the integration marker, see how the file selects adapters).
- [ ] **Step 3: Evaluator.** In `_field_matches`, when `condition.field_kind` is set: `kind = condition.field_kind`; in-scope test is `_declares(node.extra_schema, condition.key, kind)`:

```python
def _declares(extra_schema: Mapping[str, Any] | None, key: str, kind: str) -> bool:
    """Whether the item's own overlay declares `key` with `kind` and keeps it live."""
    props = (extra_schema or {}).get("properties")
    prop = props.get(key) if isinstance(props, Mapping) else None
    meta = prop.get(NAMESPACE) if isinstance(prop, Mapping) else None
    return (
        isinstance(meta, Mapping)
        and meta.get("kind") == kind
        and meta.get("archived") is not True
    )
```

  Otherwise the existing path with `node.type != condition.type`. `NAMESPACE` is in `application/schema_meta.py`; adapters may import application, but check the architecture tests; if `query_eval.py` cannot import it, use the string `"x-menagerist"` as the existing code does.
- [ ] **Step 4: SQL.** For a per-item condition use, in place of `of_type`:

```python
_has = NodeModel.extra_schema.contains(
    {"properties": {condition.key: {"x-menagerist": {"kind": kind}}}}
)
_archived = NodeModel.extra_schema.contains(
    {"properties": {condition.key: {"x-menagerist": {"archived": True}}}}
)
in_scope = and_(NodeModel.extra_schema.isnot(None), _has, not_(_archived))
```

  `extra_schema IS NOT NULL AND ...` is never NULL and stays indexable; `not_(_archived)` is safe because it is only reached when the first term is true. Combine exactly as `_field` does today (`and_(in_scope, not_(test) if complement else test)`).
- [ ] **Step 5: Index.** GIN `jsonb_path_ops` on `nodes.extra_schema` (partial `WHERE extra_schema IS NOT NULL`), declared in `models.py` and created in a new migration with a `downgrade`. Add an `EXPLAIN` test like the existing ones (use the file that tests `test_query_indexes_migration`) showing a bitmap index scan for a per-item condition on a few thousand generated rows.
- [ ] **Step 6: Run scenarios (both adapters), lint, typecheck, `test-backend`, the Postgres integration tests for search and migrations, architecture and cqrs tests.**

**Checkpoint:** user may commit.

---

### Task 3: List the per-item fields in use

**Files:**
- Modify: `backend/src/app/modules/graph/ports/node_repository.py` (new `item_fields`)
- Modify: `adapters/persistence/{node_repository,in_memory_node_repository}.py`
- Create: `backend/src/app/modules/graph/application/list_item_fields.py`
- Modify: `adapters/api/node/{router,schemas}.py`, `adapters/api/dependencies.py`
- Test: `backend/tests/modules/graph/application/test_list_item_fields.py`, repository scenario tests, `backend/tests/modules/graph/adapters/api/test_item_fields_router.py`; update `test_cross_user_isolation.py`

**Interfaces:**
- Produces: `ItemFieldUse(key: str, kind: str, label: str, count: int)` (frozen dataclass in `domain/query.py`); `NodeRepository.item_fields(*, scope: AccessScope, limit: int) -> list[ItemFieldUse]`; `ListItemFields` (a `QueryHandler`) with `ListItemFieldsQuery()` returning `list[ItemFieldUse]`; `GET /node/item-fields` returning `[{key, kind, label, count}]`.
- Rules (R14): only properties with an explicit string `x-menagerist.kind` that is a key of `KIND_OPERATORS`, not archived, in the caller's access scope; grouped by `(key, kind)`; `label` is the most common title among the group (ties by name; fall back to the key); ordered by count descending then key; at most `limit` (200) rows. Archived and inferred-kind fields are omitted.

- [ ] **Step 1: Write failing tests**: counting across items, same key with two kinds is two rows, archived omitted, inferred kind omitted, another owner's items never counted, the limit applies, an empty database returns `[]`, router returns 200 with the shape above and requires sign-in.
- [ ] **Step 2: Implement** in SQL as a `jsonb_each(extra_schema->'properties')` lateral over `nodes` with the scope predicate and the filters above (aggregate with `count(*)` and a `mode()` over the label), and in memory with the same logic over stored nodes. Find how the editor stores a field's label (`grep -rn "title" frontend/src/lib/schema*` and the schema editor) and use that property; document the choice in the use case docstring.
- [ ] **Step 3: Router and OpenAPI:** `operation_id="list_item_fields"`, tag and description in the existing style; run `uv run poe generate-frontend-client`.
- [ ] **Step 4: Run lint, typecheck, `test-backend`, Postgres tests for this repository method, architecture and cqrs tests; domain/application at 100%.**

**Checkpoint:** user may commit.

---

### Task 4: Frontend model for per-item conditions (plain TypeScript)

**Files:**
- Modify: `frontend/src/lib/query/{types,codec,operators,fields,summary,builder,warnings,tree}.ts` as needed
- Create: `frontend/src/lib/item-fields.ts` (fetch the listing)
- Modify: `shared/contracts/query-shapes.json` (add the per-item valid/invalid cases deferred from Task 1)
- Test: `frontend/tests/query-{codec,summary,builder,operators,shapes-contract}.test.ts`, `frontend/tests/item-fields.test.ts`

**Interfaces:**
- Produces: `FieldCondition` type with optional `type` and `field_kind`; `ItemField = { key, kind, label, count }`; `fetchItemFields(): Promise<ItemField[] | null>` (null on failure, never partial); a field-picker option id `item:<kind>:<key>`; `describeCondition` wording `Item field › <label>: <operator> <value>`; an `ItemField`-aware `fieldOptions(catalogue, itemFields)` that returns a "Per-item fields" group after the type groups.
- The decoder mirrors the server: exactly one of `type` / `field_kind`, no `sub_key` or `ref` with `field_kind`, never throws.

- [ ] **Step 1: Failing tests** for each bullet above, including the shared fixture cases from Task 1 and: switching a row from a type field to a per-item field resets the operator and value as it does between kinds; a per-item row whose key is missing from the listing is flagged "No item has this field" (R15); `describeCondition` falls back to the key when the label is unknown.
- [ ] **Step 2: Implement.** Keep `fitsLimits`, depth and condition counting unchanged.
- [ ] **Step 3:** `uv run poe lint-frontend && uv run poe typecheck-frontend && uv run poe test-frontend`.

**Checkpoint:** user may commit.

---

### Task 5: Per-item fields in the filter builder (Svelte)

**Files:** (all through the `svelte:svelte-file-editor` agent)
- Modify: `frontend/src/lib/components/{query-condition-row,query-builder,query-value-input,query-chips}.svelte`, `frontend/src/routes/items/+page.svelte`, `frontend/src/lib/query/builder-state.svelte.ts`
- Test: `frontend/tests/query-components.test.ts`

**Interfaces:**
- Consumes: Task 4's `fetchItemFields`, `fieldOptions`, the combobox in `ui/combobox`.
- Produces: a "Per-item fields" group in the field combobox (search matches the group name and labels), value input and operators chosen from the per-item kind exactly as for a type field, chips with the Task 4 wording, a "No item has this field" warning row state, and a page that loads the listing once alongside the item types.

- [ ] **Step 1: Failing tests** (server-render and plain-function level, as the repo's harness allows): the group appears only when the listing is non-empty; a per-item row renders the right operator list and value input for its kind; chips read as specified; a missing-key row shows the notice.
- [ ] **Step 2: Implement; keep the accessible names ("Condition N, field", ...) unchanged.**
- [ ] **Step 3: Visual check** on the isolated e2e stack only, light and dark at 1280×800 and 390×844; view the screenshots.
- [ ] **Step 4:** lint, typecheck, `test-frontend`.

**Checkpoint:** user may commit.

---

### Task 6: End-to-end test, documentation and spec

**Files:**
- Modify: `frontend/tests/e2e/advanced-search.spec.ts`
- Modify: `docs/DECISIONS.md`, `backend/README.md` (one line on the listing read), the spec (phase 1b status)

- [ ] **Step 1: e2e.** Seed through the API: an item with an overlay field (use the existing helpers; if none create overlay fields, add one to `helpers.ts`). One test: open Filters, choose the field from "Per-item fields", set the value, expect only the matching item; reload keeps the filter; the same key on a type with a different value is not matched.
- [ ] **Step 2: DECISIONS entry** (Decision / Rationale / Consequence): per-item conditions by key and kind (no version bump); the scope predicate (`@>` on the overlay with an explicit kind, archived excluded); R14-R16; the new GIN index and the `EXPLAIN` finding; the listing read and its 200-row cap.
- [ ] **Step 3: Spec:** mark phase 1b implemented and keep the "Until then, Promote to type" sentence accurate.
- [ ] **Step 4: Full gates:** `uv run poe lint && uv run poe typecheck && uv run poe test && uv run poe coverage`, and the new e2e spec three times on the isolated stack. Revert any formatter-touched unrelated docs.
- [ ] **Step 5: Stop for review.** Then a whole-phase review on the strongest model, scoped to the diff from Task 1 onwards, with the Review Focus list above as its checklist.

**Checkpoint:** user may commit.

---

## Self-Review

**Spec coverage (phase 1b).** Condition addressed by key and kind → Tasks 1-2; backend read of per-item fields with kinds and counts → Task 3; "Per-item fields" group in the builder → Tasks 4-5; unambiguous `attributes[key]` → Task 2's scope predicate (the spec's claim that a per-item key cannot clash with a type key holds only per node, so the predicate checks the item's own overlay; recorded in DECISIONS in Task 6).

**Placeholders.** None intended. Adapter code is given as exact predicates and the surrounding functions are named; implementers read those two files.

**Type consistency.** `FieldCondition` (Task 1) is the type every later task uses; `ItemFieldUse` (Task 3, Python) and `ItemField` (Task 4, TypeScript) carry the same four fields `key, kind, label, count`.

**Review Focus.** Each of the six has a named test: type-key clash and same key different kinds (Task 2 scenarios), archived (Task 2), complements and NULL overlay (Task 2), hostile input (Task 1 parser tests), listing scope and kinds (Task 3).
