# Menagerist — Computed Fields, Expressions & Aggregations

**Document:** High-Level Design (HLD)
**Status:** Proposal for review
**Version:** 0.1
**Code reference:** `samcorky/menagerist`, `feature/initial-implementation`, inspected and corrected against the code 2026-10-31
**Scope:** Design only; no repository changes

## 1. Summary

Introduce a small, typed, read-only expression system that extends Menagerist's existing query capabilities. Users will be able to derive values from item attributes (e.g. age), filter and sort on derived values, aggregate matching items (e.g. sum, average, distinct count), and eventually compute relationship-based values (e.g. number of signatures on a poster). Expressions will be reusable across query conditions, item display, and collection statistics without allowing arbitrary executable formulas.

**Recommended approach:** built-in typed functions first; aggregate queries second; reusable user-defined computed fields and relationship rollups later. Evaluate on demand, not as persisted copies of source data.

## 2. Motivation and outcomes

A collector should be able to ask questions such as:

- Which people have a birthday today, or turn 70 this year?
- Which films have fewer than two connected signatures?
- What is the total purchase value of items in this collection?
- How many distinct manufacturers occur in my electronics inventory?
- What is the total quantity of components across boxes?
- Can I display an item's calculated age or number of related items without manually maintaining a redundant attribute?

Success means the same expression has the same meaning wherever it is used, respects access control, and can be compiled to efficient SQL for queries over many items.

## 3. Current architecture and extension points

Observed on `feature/initial-implementation`:

| Existing component | Responsibility | Extension |
|---|---|---|
| `modules/graph/domain/query.py` | Versioned query AST, conditions, sort, relative dates, field references, limits | Typed expression nodes and expression-backed conditions/sorts |
| `modules/graph/application/prepare_query.py` | Parse, resolve schemas/relationships/collections, establish `today` and actor scope | Resolve function signatures, field types, dependencies, evaluation context |
| `modules/graph/application/query_resolution.py` | Resolve fields and stale references | Resolve computed expression dependencies and warnings |
| `modules/graph/adapters/persistence/query_eval.py` | Python reference evaluation | Reference expression evaluator |
| `modules/graph/adapters/persistence/query_sql.py` | SQLAlchemy query compilation | SQL expression compiler, preserving null/type semantics |
| `modules/graph/application/count_nodes.py` | Exact matching-item count via `ListNodes.count_exact`, `Content(ITEM_READ)` | Reuse filtering semantics for aggregates; keep existing API |
| `modules/graph/application/search_node_counts.py`, `count_node_types.py` | `POST /api/v1/node/search/counts` (count with a ceiling and a `capped` flag) and `GET /api/v1/node/count/types` (per-type counts), used by the dashboard | Precedent for an actor-scoped read-only count; aggregates sit beside them, not inside them |
| `modules/collections/application/count_collection_items.py` | Counts manual live members or dynamic collection matches | Collection aggregation adapter with equivalent membership semantics |
| `frontend/src/lib/query/fields.ts` | Field catalogue, sortable/filterable kinds, reference candidates | Discover supported functions and computed field definitions |
| `frontend/src/lib/components/query-builder.svelte` | Advanced query editor | Progressive function UI, not a free-text formula editor |

The current query AST has `QUERY_VERSION = 1`, nested boolean groups (`and`/`or`/`not`), `FieldCondition` (an item-type `type` or a per-item `field_kind`, plus an optional `sub_key`) and `ConnectionCondition`. `FieldCondition.value` is an `Operand`: a scalar, `Money`, `RelativeDate` (an offset such as minus seven days, resolved against `today`), `FieldReference` (another top-level field on the same item) or a tuple of these. `SortKey` can already sort by a field, nulls last. `ConnectionCondition` already covers `exists`/`none`/`to`, `direction` `out`/`in`/`any`, a nested `where`, and live, in-scope far items, so relationship counts extend it rather than start from nothing. Counts already distinguish exact and capped results. SQL compilation guards JSONB casts and avoids SQL three-valued logic leaking into boolean filters. Preserve these invariants.

**Boundary:** Do not embed new calculation rules directly into UI components or duplicate them in every query handler. Introduce a shared expression domain and evaluators that existing query paths consume.

## 4. Goals and non-goals

### Goals

1. Built-in, type-checked functions for dates and numbers.
2. Computed conditions and (subsequently) computed sorts in existing search/smart collections.
3. Actor-scoped aggregate queries over filtered items.
4. Reusable, read-only computed field definitions for item types.
5. Relationship aggregations with explicit direction, edge-versus-target semantics, and visibility filtering.
6. Consistent Python and SQL behaviour, including missing data and date boundaries.
7. Incremental rollout with each stage independently useful.

### Non-goals (initially)

- Arbitrary Python, JavaScript, SQL, or spreadsheet-style expression strings.
- Writing computed results into item attributes.
- Recursive graph traversal, recursive formulas, or cross-instance references.
- Materialized rollups or background recomputation.
- Unbounded joins, cross-currency arithmetic, or user-defined plugin functions in the MVP.
- Dashboard/chart design, though aggregation outputs should be usable by dashboards later.

## 5. User stories and acceptance criteria

| ID | Story | Acceptance criteria |
|---|---|---|
| CF-01 | As a collector, I can filter People whose birthday is today. | Compares month/day against evaluation date; leap-day policy is documented; no annual manual updates. |
| CF-02 | As a collector, I can filter People aged 70 or older. | Correct age at reference date, including birthday boundary; missing/invalid date does not match. |
| CF-03 | As a collector, I can see age on a Person item. | Read-only and clearly derived; changes with date without modifying the item. |
| CF-04 | As a collector, I can total numeric values across filtered items. | SQL-backed, actor-scoped, documented null/empty behaviour. |
| CF-05 | As a collector, I can count distinct manufacturers. | Ignores missing values; defined handling for multi-valued fields. |
| CF-06 | As a collector, I can count signatures linked to a poster. | Respects direction, relationship type, deleted edges, and visible target items. |
| CF-07 | As a collector, I can filter films with fewer than two signatures. | Works in saved smart collections without loading all films into application memory. |
| CF-08 | As a schema editor, I can define a reusable computed field. | Typed definition, validated references, no arbitrary code, clear stale-field warnings. |
| CF-09 | As a user, I see only aggregates over content I can access. | No counts or values leaked from invisible items or edges. |
| CF-10 | As a user, I can rely on the same result in search, item view, and collection summary. | Cross-adapter parity tests and shared function semantics. |

## 6. Conceptual design

### 6.1 Expression model

Introduce a typed expression AST, distinct from the boolean query tree but embeddable within it:

```text
Expression
  Literal(value, kind)
  FieldRef(key, type?, sub_key?)
  FunctionCall(function, args[])
  AggregateExpression(function, source, field?, distinct?)  [later]
```

Example (illustrative, not a final API contract):

```json
{
  "fn": "age",
  "args": [{ "key": "birthday", "type": "person" }]
}
```

Field references use the same `key`, `type` and optional `sub_key` members as `FieldCondition`, so one resolver serves both. A query condition can compare an expression with a typed operand:

```json
{
  "expression": { "fn": "age", "args": [{ "key": "birthday", "type": "person" }] },
  "op": ">=",
  "value": 70
}
```

Keep the existing v1 wire query valid. Introduce a versioned extension (likely v2) only when persisted query shapes actually change; provide explicit parsing/migration and backward-compatible reading for stored smart collection definitions. Do not silently reinterpret old conditions.

### 6.2 Function catalogue

Each function declares identifier, input kinds, output kind, null policy, date/context dependencies, supported execution backends, and cost/complexity classification. Function signatures are authoritative on the backend; frontend receives a safe capability description rather than maintaining an independent list of logic.

Initial examples:

| Function | Input | Output | Notes |
|---|---|---|---|
| `age` | full date | number | Completed years at evaluation date |
| `is_anniversary_today` | full date | boolean | Month/day comparison, leap-day policy |
| `days_until_anniversary` | full date | number | Next occurrence; 0 today |
| `year` / `month` / `day` | full date | number | Calendar components |
| `date_diff_days` | date, date | number | Explicit sign convention |
| `coalesce` | same-kind operands | same kind | Optional later; controlled missing-value handling |

**Partial dates:** `partialdate` is not a full birthday. Do not infer missing year/day. Functions requiring a full date reject partial-date fields unless a separate, explicitly specified operation supports them.

### 6.3 Evaluation context and time

Use a single immutable evaluation context per request, containing `today`, timezone, and actor/scope. The existing `prepare_query` uses `utc_today()`; preserve current behaviour for old queries, but define a documented timezone policy for new anniversary functions. An instance timezone already exists (`SchedulerSettings.timezone`, from `MENAGERIST_TIMEZONE` or `TZ`, default UTC), so use it as the default and add a per-user preference only if needed. Resolve `today` once and pass it into Python and SQL; do not call database `now()` independently for each row.

Define a consistent 29 February anniversary policy (proposed: celebrate on 28 February in non-leap years; make configurable only if a real use case emerges). `age` must calculate completed years using the same policy. Avoid ambiguous daylight-saving assumptions by operating on local calendar dates, not elapsed seconds.

### 6.4 Missing values, types and errors

- Missing/null/invalid field values produce a typed missing result, not zero or `false` by default.
- A positive comparison against missing returns no match; `NOT` and inequality must follow existing query complement semantics deliberately.
- `sum` ignores missing numeric values; `count` counts matching rows; `count(field)` counts present values; `avg` ignores missing values. Decide whether empty sum returns `null` or zero in the public contract (recommend `null` for no numeric observations, plus an explicit `observations` count).
- `count_distinct` ignores nulls. Text equality/collation must match the existing engine's normalization policy or be separately documented.
- Mixed currencies must never be silently summed. `Money` is already a query operand (`value`, `currency`); initially reject cross-currency money aggregation or group by currency.
- A stale referenced field yields a warning and non-matching expression, rather than silently substituting a different field.

### 6.5 Aggregate query model

Add a dedicated read-side aggregate query/use case; reuse prepared filters and scope. Do not overload the existing count endpoints or item-list response. Unlike `search/counts`, which stops at a ceiling and reports `capped`, a sum or average over a capped set would be silently wrong, so aggregates either run over the whole matching set (bounded by a statement timeout) or fail with a clear error; they never return a partial total.

Illustrative request:

```json
{
  "query": { "where": { "op": "and", "children": [] } },
  "metrics": [
    { "as": "items", "fn": "count" },
    { "as": "total_value", "fn": "sum", "field": { "key": "purchase_price", "type": "poster" } },
    { "as": "manufacturers", "fn": "count_distinct", "field": { "key": "manufacturer", "type": "component" } }
  ]
}
```

Initial aggregate functions: `count`, `sum`, `avg`, `min`, `max`, `count_distinct`. `distinct` returning a list and `group_by` returning rows are separate later capabilities requiring result-size and cardinality limits. Decide semantics for arrays and repeating-group columns explicitly; do not accidentally multiply item counts by unnested rows.

For collections, dynamic collections aggregate the same filtered set as their stored definition; manual collections aggregate live, visible membership items. Apply the caller's scope before aggregation.

### 6.6 Relationship aggregates

Extend `ConnectionCondition` concepts with an explicit relationship source specification:

```json
{
  "fn": "count",
  "source": {
    "relationship": "signed_by",
    "direction": "out",
    "count": "distinct_targets"
  }
}
```

Define `edges` versus `distinct_targets` as separate modes. For directional relationships, use the current item's endpoint appropriately; for non-directional relationships, allow either endpoint. Count only live edges with live, actor-visible opposite nodes. A future nested `where` on target items should reuse the existing connection-condition query grammar, within strict depth and complexity limits.

Implement with SQL correlated subqueries or grouped joins; avoid N+1 per-item queries. A relation-based expression can be used in a filter or display after the SQL compiler supports it.

### 6.7 Named computed field definitions

Later, store read-only computed field definitions on the item-type schema or in a dedicated schema-owned definition table (decision deferred). They should have a stable identifier, label, output kind, expression AST, owner/scope, and revision. Prefer type-scoped definitions first; built-in operations can still work on per-item fields. Prevent circular computed-field dependencies; define behaviour when source fields are renamed, archived or deleted. Do not place computed results in the regular mutable `attributes` JSONB.

## 7. Architecture and responsibilities

```text
Frontend query builder / item view / collection summary
                  |
          API request schemas
                  |
       Application query handlers
          |             |
    Query preparation   AggregateNodes
          |
   Typed expression validation / resolution
          |
     Resolved expression AST
          |             |
   Python evaluator   SQLAlchemy compiler
          |             |
    parity tests     PostgreSQL query
```

Suggested conceptual module ownership:

- `modules/graph/domain/expressions.py`: immutable AST, types, validation primitives.
- `modules/graph/application/expression_resolution.py`: schema lookup, dependencies, function/type checks.
- `modules/graph/adapters/persistence/expression_sql.py`: SQLAlchemy compilation.
- `modules/graph/adapters/persistence/expression_eval.py`: Python reference evaluator.
- `modules/graph/application/aggregate_nodes.py`: CQRS read handler. It declares `access = Content(GraphPermission.ITEM_READ)`, fetches through `self.scope(actor)`, and is added to the pinned `Content` set in `tests/architecture/test_access_stances.py`.
- Existing query preparation, repository ports and SQL query compiler integrate these pieces rather than being replaced.

These are proposed paths, not assertions that files exist today. Use the existing CQRS handler, ports, UOW and permission conventions. Prefer pure domain logic for function signatures and date semantics; adapters own SQL-specific expressions.

## 8. API and UI strategy

**API:** retain existing list/count routes. Add an aggregate endpoint (`POST /api/v1/node/aggregate`; the node router is mounted at `/node`, beside `/node/search/counts`). Use validated Pydantic request/response models, bounded metric counts, typed results, and normal auth checks. Computed condition syntax should be introduced through a versioned query contract rather than a second filter language.

**UI:** begin with contextual options in existing date and numeric field pickers, e.g. Birthday → Age → greater than 70; Birthday → Anniversary today. Later add a collection summary showing count, sum and distinct count. Only after these are stable add a computed-field editor and relationship rollups. Surface whether a value is derived, and optionally its expression and evaluation date. Avoid a free-text expression box in the initial UI.

## 9. Security, performance and operational constraints

1. Resolve the actor's content scope before query evaluation and aggregation; apply visibility to related nodes as well as source nodes.
2. Compile from a whitelist of registered functions; never evaluate user-authored source code.
3. Bound expression depth, function count, aggregate count, nested relationship depth, and grouped result cardinality.
4. Use typed, guarded JSONB extraction and safe SQL parameter binding; preserve existing SQL/Python parity rules.
5. Reuse existing query indexes where possible; assess expression-specific indexes only from measured query plans.
6. Compute at read time initially. Add caching only with explicit invalidation rules and date-boundary expiration for time-dependent functions.
7. Avoid scanning entire collections in Python for list filters. SQL is authoritative for set-wide filtering and aggregation.
8. Log function identifiers, execution duration and query shape without logging private field values unnecessarily.
9. Consider database statement timeouts and rate limits for expensive aggregates.

## 10. Incremental delivery plan

| Stage | Deliverable | Usable outcome |
|---|---|---|
| 1 | Typed expression AST, function registry, Python/SQL parity; `age`, `is_anniversary_today` | Birthday and age filtering in advanced search/smart collections |
| 2 | Expression-backed sorting and item-view evaluation | Display and sort by derived date values |
| 3 | `AggregateNodes` with count/sum/avg/min/max/count_distinct | Collection totals and distinct counts through API and simple UI |
| 4 | Relationship count expressions | Signature/appearance counts and filters |
| 5 | Saved type-scoped computed definitions | Reusable read-only derived fields across views |
| 6 | Relationship sums, grouped aggregations, distinct value lists | Rollups, breakdowns, richer collection statistics |

Every stage requires schema validation, actor-scope tests, SQL/Python parity tests, and UI/API contract coverage. Stages 2 and 3 may be swapped if aggregate summaries are more valuable than display fields.

## 11. Test strategy

- Unit tests for functions and type checking: birthday boundaries, 29 February, nulls, bad field types, negative/zero values.
- Property/parameterized tests comparing Python evaluator with PostgreSQL for the same resolved expression.
- Integration tests for smart collections and manual membership semantics.
- Access-control tests proving aggregates cannot infer invisible items or edges.
- Regression tests for v1 query parsing, complement operators, stale fields, sorting and cursor pagination.
- Query-plan/performance tests on realistic JSONB attributes and dense relationships; ensure no N+1.
- UI tests for function discovery, input widgets, error/warning display and saved query round-tripping.

## 12. Decisions to review

| Decision | Recommendation | Alternative/trade-off |
|---|---|---|
| Expression syntax | Typed JSON AST | String formulas are more familiar but substantially harder to validate securely |
| Persist results | No, compute on read | Materialization improves expensive reads but creates invalidation complexity |
| Function exposure | Backend-defined catalogue | Hardcoded frontend list is simpler initially but risks drift |
| Named field scope | Item-type scoped first | Per-item definitions increase flexibility and resolution complexity |
| Aggregation API | Separate read endpoint/use case | Embedding in list queries reduces round trips but complicates pagination/contracts |
| Query version | Preserve v1; introduce v2 when wire shape changes | Mutating v1 is simpler but risks saved-query compatibility |
| Date timezone | Explicit request context, default the existing instance timezone (`MENAGERIST_TIMEZONE`) | UTC everywhere is simpler but surprising for birthdays; `prepare_query` uses UTC today |
| Leap-day anniversary | 28 February in non-leap years | 1 March is also defensible; settle before implementation |
| Money totals | Same currency only initially | Currency conversion requires exchange-rate source and as-of semantics |
| Relationship counts | Distinct targets and edge counts both explicit | One implicit count mode is simpler but ambiguous |
| Python evaluator | Keep as parity reference | SQL-only would reduce duplication but loses an existing correctness oracle |

## 13. Open questions

1. Should birthday and age operations be exposed as special date operators before the full expression-backed query wire format ships?
2. Should computed values appear automatically in item views, or only when explicitly configured?
3. Should `distinct` on multichoice fields count individual selections or whole arrays? Recommend individual selections, explicitly documented.
4. For group/table columns, should sum operate per row or per item? Require an explicit unnest/row aggregation mode rather than guessing.
5. Do users need aggregate conditions across all items in a collection, or primarily per-item relationship aggregates? These are different query levels.
6. Is the first user-visible aggregate surface a collection header, a dedicated statistics panel, or query-builder results?
7. How should a computed definition respond to changes in the referenced schema: warning, disabled state, or migration assistance?

## 14. Recommendation

Approve the typed expression foundation, starting with date-derived conditions. Keep set-wide aggregations in a separate actor-scoped read use case, and treat relationship rollups as a later extension using existing connection-query semantics. Build function definitions once and share their semantics across Python, SQL and frontend capability metadata. Defer arbitrary formulas, persistence of results and generalized grouped analytics until real use cases justify their complexity.

**Repository:** https://github.com/samcorky/menagerist/tree/feature/initial-implementation
