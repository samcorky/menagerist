# Field-to-field conditions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a field condition compare a field with another field of the same item (`in_stock <= reorder_at`), then use it to make the Parts pack's *Running low* a smart collection.

**Architecture:** An additive extension of `FieldCondition`: instead of `value`, a condition may carry `other`, the key of a second field on the same item type. Resolution checks both fields, the evaluator and the SQL compiler compare the two stored values, and the builder gets a "compare with a field" choice. The query format stays version 1.

**Tech Stack:** FastAPI, SQLAlchemy on Postgres (JSONB attributes), SvelteKit 5 runes, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-14-smart-collections-advanced-search-design.md` (condition kinds, "Semantics worth fixing now") and `docs/DECISIONS.md` ("Smart collections: a stored search, resolved through bridges", "Connection conditions (2026-10-24)").

## Global Constraints

- Never create, stage or push commits; the user commits at the checkpoints.
- British English; comments short and factual; the UI never says node, edge or graph.
- `entrypoints → adapters → application → domain`; `graph` and `collections` never import each other; `examples` imports neither.
- `.svelte` and `.svelte.ts` files go through the `svelte-file-editor` subagent. UI follows `frontend/DESIGN_GUIDELINES.md`.
- Subagents: Sonnet 5.5 at medium effort at most; always pass `model` and `effort`.
- Coverage floors: domain, application, shared_kernel 100%; adapters 80%; platform 70%.
- The query format changes only additively; `v` stays 1. Limits stay depth 4, 50 conditions.

## Rulings

- **E1 (shape):** a field condition has exactly one of `value` and `other`. `other` is the key of another field on the same `type` (so `type` is required, `field_kind` and `sub_key` are not allowed with it). Operators are the comparison ones the field kind already supports for a value (`=`, `!=`, `<`, `<=`, `>`, `>=`); operators that need no operand or a list (`is_empty`, `in`, `contains` and the like) are rejected with `other`.
- **E2 (which fields):** both fields must be of the same comparable kind. For this plan: number, rating, and the date kinds (date, partial date, datetime). Other kinds (text, money, select, checklist and so on) are refused with the query-format error naming the path. Money is excluded because currencies may differ.
- **E3 (missing values):** an item missing either value never matches, including under `!=`; under `not` the whole condition inverts as for any field condition. This matches how a typed value behaves for a missing field today (confirm in the code and follow it exactly).
- **E4 (stale):** if either field is removed or changes to a different kind, the condition is stale: false, with a warning on its path, as for existing field conditions.
- **E5 (pack use):** a pack definition may use `other` (it names a field key, portable like any field key).

## Review Focus

1. A missing value on either side never matches, on both adapters, with `=`, `!=`, `<` and under `not`.
2. Dates and partial dates compare correctly (a year-only date against a full date) and numbers compare as numbers, not strings, in SQL.
3. A field changed to another kind after saving degrades to stale with a warning, never a 500 (both adapters).
4. Stored definitions without `other` behave exactly as before.

---

### Task 1: Backend (domain, resolution, both adapters)

**Files:**
- Modify: `backend/src/app/modules/graph/domain/query.py` (`FieldCondition.other`, parser keys, validation per E1), `application/query_resolution.py` (resolve both fields, E2 and E4), `adapters/persistence/query_eval.py`, `adapters/persistence/query_sql.py`
- Test: `backend/tests/modules/graph/domain/test_query_field_other.py`, `backend/tests/modules/graph/application/test_query_resolution_field_other.py`, a shared scenario table `backend/tests/modules/graph/adapters/persistence/test_query_field_other_scenarios.py` on both adapters (Postgres variant `integration`-marked)

**Interfaces:**
- Produces: `FieldCondition(key, op, type, field_kind, value, sub_key, other: str | None = None)`; the parser accepts `other` and rejects it with `value`, `field_kind`, `sub_key`, a list or no-operand operator, or a missing `type`, each naming the path; resolution marks the condition stale (with a warning) when either field is missing or the kinds differ or are not comparable.

- [ ] **Step 1: Failing tests.** Parser: valid number, rating and date forms; each rejection above. Resolution: kinds match and are comparable; a removed field, a different kind and a non-comparable kind (text, money) warn and are stale. Scenarios on both adapters: `<=` over numbers; ratings; dates; a year-only date against a full date; missing on either side never matches (including `!=`); `not`; combined with a type condition, sort, paging and `Total-Count`; a definition without `other` unchanged.
- [ ] **Step 2: Run, expect failure.**
- [ ] **Step 3: Implement** following how `FieldCondition` with `value` is parsed, resolved, evaluated and compiled; compile to a comparison of the two JSONB values cast to the kind's SQL type, using the same casts as the value form.
- [ ] **Step 4: Run** lint, mypy, `poe test-backend`, the Postgres tests for the repository and search, architecture tests; domain and application 100%.

### Task 2: Frontend model and builder

**Files:**
- Modify: `frontend/src/lib/query/*` (types, codec, tree, summary, warnings, narrow, fields as needed), `frontend/src/lib/components/query-condition-row.svelte` and the field-value input component (via `svelte-file-editor`), `shared/contracts/query-shapes.json` (add `other` forms; the backend contract test reads it)
- Test: Vitest beside each module; one e2e case in `frontend/tests/e2e/smart-collections.spec.ts`

**Interfaces:**
- Consumes: Task 1's shape (`other`).
- Produces: a field row with a "Value" / "Another field" choice shown only when the field kind is comparable (E2); "Another field" shows a select of the other comparable fields of the same kind on that item type (not the field itself); summaries such as "In stock is at most Reorder at"; warnings map to the row.

- [ ] **Step 1: Failing tests** for decode/encode round trip, malformed forms into the "can't be shown" state, summary wording, the field list excluding the field itself and other kinds, and the stale warning path.
- [ ] **Step 2: Implement** (plain TS first, then the Svelte rows through the subagent); lint-frontend, typecheck-frontend, test-frontend; check desktop and phone width in light and dark.

### Task 3: Pack, e2e, docs and gates

**Files:**
- Modify: `backend/src/app/modules/examples/packs/parts.json` (*Running low* becomes a definition; bump Parts to version 6), `backend/tests/modules/examples/packs/` (content test asserting the exact three items today's list holds), `frontend/tests/e2e/` (install Parts, open *Running low*, see those items with the Smart badge), `docs/DECISIONS.md` (E1 to E5), `backend/README.md`, `frontend/README.md`, `shared/README.md` where they list condition forms

- [ ] **Step 1:** convert *Running low* to `in_stock <= reorder_at` on `parts-part`; the content test installs the pack on the in-memory adapters and asserts the exact item names; confirm they equal the old list, otherwise report the difference.
- [ ] **Step 2: E2E** three runs in a row; DECISIONS entry and spec status.
- [ ] **Step 3: Full gates:** `poe lint`, `poe typecheck`, `poe test`, `poe coverage`.

**Checkpoint:** user commits Part E.
