# Query Engine and Advanced Search Implementation Plan (phase 1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let people filter and sort their items with a saved-able condition tree (AND/OR/NOT groups; text, type, favourite, tag, date and per-field conditions; field references and relative dates), through `POST /node/search` and a visual filter builder on the items page.

**Architecture:** A versioned JSON condition tree is parsed into frozen domain dataclasses (`graph/domain/query.py`), validated against item-type schemas in the application layer (stale fields become warnings, wrong operators become 400s), and evaluated by two adapters that must agree: an in-memory Python evaluator and a SQLAlchemy compiler. Paging is keyset on `(sort values…, id)` with an opaque cursor. The frontend keeps the tree as the only state, in the URL, and renders it in a builder.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy 2 async + Postgres JSONB (GIN, `pg_trgm`, `unaccent`), Alembic, pytest; SvelteKit 2 / Svelte 5 runes, TypeScript strict, shadcn-svelte, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-14-smart-collections-advanced-search-design.md` (this plan is phase 1 only: no connection conditions, no smart collections, no pack changes).

## Global Constraints

- Python 3.14+; `mypy --strict` must pass (`poe typecheck-backend`). TypeScript strict (`poe typecheck-frontend`).
- Dependency direction `entrypoints → adapters → application → domain`; `graph` must not import `collections` and vice versa (architecture tests).
- Every port ships an in-memory adapter; application and router tests use it. Only real-adapter tests are `@pytest.mark.integration`.
- Coverage floors: domain 100%, application 100%, shared_kernel 100%, adapters 80%.
- British English in code, comments and copy. Comments short and only where intent is unclear. Google-style docstrings, sections only when useful.
- No new dependencies (base64url, JSON and `btoa` are built in).
- UI copy never says node, edge or graph. Phase 1 UI says "Filters", "condition", "match all / any".
- Internal hrefs use `resolve()` from `$app/paths`. API calls go through `src/lib/api/client.ts`; never edit `src/lib/api/generated/`.
- Every `.svelte` or `.svelte.ts` file is written by the `svelte-file-editor` subagent.
- **Never run `git add` or `git commit`.** Each task ends at a checkpoint where the user may commit.
- The access scope is combined with the compiled query last, as one `AND`, so an `OR` group can never escape it.

## Review Focus

The five failure modes the spec implies but a straight reading would miss. Each is pinned by a test in the task named.

1. **`NOT` over missing, stale or wrong-typed values** (Tasks 3, 4, 6). `not(rating >= 4)` must include items with no rating and items whose stored rating is the string `"abc"`, in both adapters, and no query may error because a stored value has the wrong JSON type.
2. **Partial dates under a locale collation** (Task 6). Postgres' default collation can ignore hyphens when comparing text; `"1982-06"` vs `"1982"` and `between 1980 and 1989` must compare as plain code points (`COLLATE "C"`), matching Python.
3. **Keyset paging with ties, nulls and `desc`** (Tasks 4, 6, 8). Walking pages of 2 over a sort with ties and nulls must visit every item exactly once, and a cursor whose row was deleted must still continue correctly.
4. **Cross-user isolation inside `OR` groups** (Tasks 4, 6, 9). A saved or posted `or` group matching another user's items returns none of them.
5. **LIKE wildcards and accents in values** (Task 4). `~ "50%"` and `~ "café"` must match literally and accent-insensitively; `_` and `%` in input are never wildcards.

---

## File Structure

**Create (backend, under `backend/src/app/modules/graph/`)**

| File | Responsibility |
|---|---|
| `domain/query.py` | Tree dataclasses, limits, `parse_query`, `walk_conditions`, `Cursor`, `ResolvedQuery`, `SearchHit`, `InvalidQueryError` |
| `application/field_kinds.py` | `KIND_OPERATORS`, `REF_KINDS`, `kind_of(prop)` |
| `application/query_resolution.py` | `resolve_fields(query, schemas)` → `FieldResolution` (kinds map + `QueryWarning`s); value and operator validation. `QueryWarning` and `FieldResolution` live in `domain/query.py`: the CQRS architecture test allows only handlers and `*Command/*Query/*Result/*Permission` classes in `application/` |
| `application/query_cursor.py` | `encode_cursor` / `decode_cursor` |
| `application/search_nodes.py` | `SearchNodes` use case |
| `application/type_catalogue.py` | `load_node_types(repos)` (paged read of all types, shared with `ListNodes`) |
| `adapters/persistence/text_match.py` | `fold`, `sort_key`, `text_matches` (moved out of the in-memory repo) |
| `adapters/persistence/query_eval.py` | Python evaluator: `matches`, `sort_values`, `is_after` |
| `adapters/persistence/search_sql.py` | Text-search SQL helpers moved out of `node_repository.py` |
| `adapters/persistence/query_sql.py` | Tree → SQLAlchemy `WHERE`, sort expressions, keyset clause |
| `src/app/alembic/versions/q8f9a0b1c2d3_query_indexes.py` | GIN indexes, `immutable_unaccent`, trigram indexes |

**Create (shared, tests, frontend)**

| File | Responsibility |
|---|---|
| `shared/contracts/query-operators.json` | Operators per field kind; both suites read it |
| `backend/tests/modules/graph/domain/test_query.py` | Parser, limits, relative dates |
| `backend/tests/modules/graph/application/test_field_kinds.py` | Kind inference, operator contract |
| `backend/tests/modules/graph/application/test_query_resolution.py` | Warnings and 400s |
| `backend/tests/modules/graph/application/test_search_nodes.py` | Use case, paging, warnings |
| `backend/tests/modules/graph/adapters/persistence/test_node_search.py` | The shared scenarios, both adapters |
| `backend/tests/modules/graph/adapters/api/test_node_search_router.py` | `POST /node/search` |
| `frontend/src/lib/query/{types,operators,codec,tree,summary}.ts` | Pure TypeScript model |
| `frontend/src/lib/components/query-*.svelte` | Builder UI (Task 11) |
| `frontend/tests/query-*.test.ts`, `frontend/tests/e2e/advanced-search.spec.ts` | Tests |

**Modify:** `ports/node_repository.py`, both node repositories, `adapters/api/node/{router,schemas}.py`, `adapters/api/dependencies.py`, `application/list_nodes.py` (use `load_node_types`), `adapters/persistence/models.py` (declare indexes), `frontend/src/routes/items/+page.svelte`, `shared/README.md`, `docs/DECISIONS.md`, the spec (reconciliation, Task 12).

**Reconciliation with the spec** (apply in Task 12): the repository gains separate `search` / `search_count` methods rather than extending `list` / `count` (the paging key differs; `GET /node` is untouched); the operator table lives in the backend because the backend has no `FieldTypeDescriptor`; the URL carries plain base64url JSON, not compressed.

---

### Task 1: Operator contract and kind table

**Files:**
- Create: `shared/contracts/query-operators.json`
- Create: `backend/src/app/modules/graph/application/field_kinds.py`
- Create: `backend/tests/modules/graph/application/test_field_kinds.py`
- Modify: `shared/README.md` (contracts table row)

**Interfaces:**
- Produces: `KIND_OPERATORS: Mapping[str, frozenset[str]]`, `REF_KINDS: frozenset[str]`, `NO_VALUE_OPERATORS: frozenset[str]`, `kind_of(prop: Mapping[str, Any]) -> str | None`.

- [ ] **Step 1: Write the contract file**

`shared/contracts/query-operators.json`:

```json
{
  "text": ["=", "!=", "~", "in", "empty", "not_empty"],
  "url": ["=", "!=", "~", "in", "empty", "not_empty"],
  "email": ["=", "!=", "~", "in", "empty", "not_empty"],
  "phone": ["=", "!=", "~", "in", "empty", "not_empty"],
  "longtext": ["~", "empty", "not_empty"],
  "number": ["=", "!=", ">", ">=", "<", "<=", "between", "empty", "not_empty"],
  "duration": ["=", "!=", ">", ">=", "<", "<=", "between", "empty", "not_empty"],
  "rating": ["=", "!=", ">", ">=", "<", "<=", "between", "empty", "not_empty"],
  "money": ["=", "!=", ">", ">=", "<", "<=", "between", "empty", "not_empty"],
  "date": ["=", "!=", ">", ">=", "<", "<=", "between", "empty", "not_empty"],
  "partialdate": ["=", "!=", ">", ">=", "<", "<=", "between", "empty", "not_empty"],
  "boolean": ["=", "!="],
  "choice": ["=", "!=", "in", "empty", "not_empty"],
  "multichoice": ["has", "empty", "not_empty"],
  "checklist": ["incomplete", "complete", "empty", "not_empty"]
}
```

- [ ] **Step 2: Write the failing test**

`backend/tests/modules/graph/application/test_field_kinds.py`:

```python
import json
from typing import Any

import pytest

from app.modules.graph.application.field_kinds import KIND_OPERATORS, kind_of
from app.platform.shared_data import shared_data_path


def test_operator_table_matches_the_shared_contract() -> None:
    """Backend and frontend read one operator table per field kind."""
    contract = json.loads(
        shared_data_path("contracts/query-operators.json").read_text("utf-8")
    )
    assert {kind: set(ops) for kind, ops in contract.items()} == {
        kind: set(ops) for kind, ops in KIND_OPERATORS.items()
    }


@pytest.mark.parametrize(
    ("prop", "expected"),
    [
        ({"type": "number", "x-menagerist": {"kind": "duration"}}, "duration"),
        ({"type": "string", "x-menagerist": {"kind": "partialdate"}}, "partialdate"),
        ({"type": "number"}, "number"),
        ({"type": "integer"}, "number"),
        ({"type": "boolean"}, "boolean"),
        ({"type": "string"}, "text"),
        ({"type": "string", "enum": ["a"]}, "choice"),
        ({"type": "string", "format": "date"}, "date"),
        ({"type": "array", "items": {"type": "string", "enum": ["a"]}}, "multichoice"),
        ({"type": "array", "items": {"type": "object"}}, None),
        ({"type": "object", "x-menagerist": {"kind": "opaque"}}, None),
        ({"type": "string", "x-menagerist": {"kind": "no-such-kind"}}, "text"),
    ],
)
def test_kind_of(prop: dict[str, Any], expected: str | None) -> None:
    assert kind_of(prop) == expected
```

(`shared_data_path` is already used by `test_text_constraints.py`; read its import there to confirm the module path.)

- [ ] **Step 3: Run it to verify it fails**

Run: `cd backend && pytest tests/modules/graph/application/test_field_kinds.py -q`
Expected: FAIL, `ModuleNotFoundError: ...field_kinds`.

- [ ] **Step 4: Write the implementation**

`backend/src/app/modules/graph/application/field_kinds.py`:

```python
"""Which operators each field kind supports, and how a property's kind is read."""

from collections.abc import Mapping
from typing import Any, Final

from app.modules.graph.application.schema_meta import NAMESPACE

_ORDERED = frozenset({"=", "!=", ">", ">=", "<", "<=", "between", "empty", "not_empty"})
_TEXT = frozenset({"=", "!=", "~", "in", "empty", "not_empty"})

KIND_OPERATORS: Final[Mapping[str, frozenset[str]]] = {
    "text": _TEXT,
    "url": _TEXT,
    "email": _TEXT,
    "phone": _TEXT,
    "longtext": frozenset({"~", "empty", "not_empty"}),
    "number": _ORDERED,
    "duration": _ORDERED,
    "rating": _ORDERED,
    "money": _ORDERED,
    "date": _ORDERED,
    "partialdate": _ORDERED,
    "boolean": frozenset({"=", "!="}),
    "choice": frozenset({"=", "!=", "in", "empty", "not_empty"}),
    "multichoice": frozenset({"has", "empty", "not_empty"}),
    "checklist": frozenset({"incomplete", "complete", "empty", "not_empty"}),
}

# Kinds whose conditions may compare with another field of the same kind.
REF_KINDS: Final = frozenset({"number", "duration", "rating", "money", "date"})
NO_VALUE_OPERATORS: Final = frozenset({"empty", "not_empty", "incomplete", "complete"})


def kind_of(prop: Mapping[str, Any]) -> str | None:
    """Return the filterable kind of a schema property, or None if it has none.

    An explicit `x-menagerist.kind` wins when it is filterable. Otherwise the
    kind is inferred from the JSON Schema shape, as the frontend does.
    """
    meta = prop.get(NAMESPACE)
    explicit = meta.get("kind") if isinstance(meta, Mapping) else None
    if isinstance(explicit, str) and explicit in KIND_OPERATORS:
        return explicit
    if isinstance(explicit, str) and explicit in {
        "opaque",
        "group",
        "list",
        "quantity",
    }:
        return None
    declared = prop.get("type")
    if declared == "string":
        if prop.get("format") == "date":
            return "date"
        return "choice" if "enum" in prop else "text"
    if declared in {"number", "integer"}:
        return "number"
    if declared == "boolean":
        return "boolean"
    if declared == "array":
        items = prop.get("items")
        if (
            isinstance(items, Mapping)
            and items.get("type") == "string"
            and "enum" in items
        ):
            return "multichoice"
    return None
```

- [ ] **Step 5: Run it to verify it passes**

Run: `cd backend && pytest tests/modules/graph/application/test_field_kinds.py -q`
Expected: PASS (13 tests).

- [ ] **Step 6: Document the contract**

Add a row to the `contracts/` table in `shared/README.md`: `contracts/query-operators.json` pins "the filter operators each field kind supports". It is read by backend `test_field_kinds.py` and frontend `tests/query-operators.test.ts` (Task 10). Add a one-line "when to change" note: edit this file, then both tables.

**Checkpoint:** `cd backend && pytest tests/modules/graph/application -q` is green. The user may commit.

---

### Task 2: Domain query tree and parser

**Files:**
- Create: `backend/src/app/modules/graph/domain/query.py`
- Create: `backend/tests/modules/graph/domain/test_query.py`

**Interfaces:**
- Consumes: `app.shared_kernel.errors.ValidationError`.
- Produces (used by every later task):
  - Conditions: `TextCondition(q)`, `TypeCondition(slugs)`, `FavouriteCondition(value)`, `TagCondition(mode, tags)`, `DateCondition(on, op, value)`, `FieldCondition(type, key, op, value=None, sub_key=None)`.
  - `Group(op, children)`, `SortKey(by, dir, type, key)`, `Query(where, sort)`.
  - Operands: `RelativeDate(amount, unit).resolve(today) -> date`, `FieldReference(key)`, `Money(value, currency)`.
  - `parse_query(data: object) -> Query`, `walk_conditions(group, path="where") -> Iterator[tuple[str, Condition]]`.
  - `FieldKey = tuple[str, str, str | None]`, `SortValue = str | float | None`, `Cursor(sort_values, id)`, `SearchHit(node, sort_values)`, `ResolvedQuery(query, field_kinds, search_exclusions, today)`.
  - `InvalidQueryError(message, *, path="")` with `.path`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/modules/graph/domain/test_query.py`:

```python
from datetime import date
from typing import Any

import pytest

from app.modules.graph.domain.query import (
    MAX_CONDITIONS,
    MAX_DEPTH,
    FieldCondition,
    FieldReference,
    Group,
    InvalidQueryError,
    Money,
    RelativeDate,
    SortKey,
    TagCondition,
    parse_query,
    walk_conditions,
)


def _query(where: dict[str, Any] | None, **extra: Any) -> dict[str, Any]:  # noqa: ANN401
    return {"v": 1, "where": where, **extra}


def _field(**kwargs: Any) -> dict[str, Any]:  # noqa: ANN401
    return {
        "kind": "field",
        "type": "film",
        "key": "rating",
        "op": ">=",
        "value": 4,
        **kwargs,
    }


def test_parses_a_nested_tree() -> None:
    query = parse_query(
        _query(
            {
                "op": "and",
                "children": [
                    {"kind": "favourite", "value": True},
                    {
                        "op": "or",
                        "children": [
                            _field(),
                            {"kind": "tag", "mode": "any", "tags": ["noir"]},
                        ],
                    },
                ],
            },
            sort=[{"by": "field", "type": "film", "key": "rating", "dir": "desc"}],
        )
    )
    assert isinstance(query.where, Group)
    assert query.sort == (SortKey(by="field", dir="desc", type="film", key="rating"),)
    paths = [path for path, _ in walk_conditions(query.where)]
    assert paths == [
        "where.children[0]",
        "where.children[1].children[0]",
        "where.children[1].children[1]",
    ]


def test_no_where_means_everything() -> None:
    assert parse_query(_query(None)).where is None


def _and(*children: dict[str, Any]) -> dict[str, Any]:
    return {"op": "and", "children": list(children)}


def test_operand_forms_parse() -> None:
    cases = [
        ({"rel": "-30d"}, RelativeDate(amount=-30, unit="d")),
        ({"ref": "reorder_at"}, FieldReference(key="reorder_at")),
        ({"value": 3.5, "currency": "GBP"}, Money(value=3.5, currency="GBP")),
    ]
    for raw, expected in cases:
        query = parse_query(_query(_and(_field(op="=", value=raw))))
        assert isinstance(query.where, Group)
        condition = query.where.children[0]
        assert isinstance(condition, FieldCondition)
        assert condition.value == expected


def test_between_and_in_and_has_take_lists() -> None:
    query = parse_query(
        _query(
            _and(
                _field(op="between", value=[1, 5]),
                _field(key="g", op="has", value="scifi"),
                _field(key="c", op="in", value=["a", "b"]),
            )
        )
    )
    assert isinstance(query.where, Group)
    between, has, in_ = query.where.children
    assert isinstance(between, FieldCondition) and between.value == (1, 5)
    assert isinstance(has, FieldCondition) and has.value == ("scifi",)
    assert isinstance(in_, FieldCondition) and in_.value == ("a", "b")


def test_no_value_operators_reject_a_value() -> None:
    with pytest.raises(InvalidQueryError, match=r"where\.children\[0\]"):
        parse_query(_query(_and(_field(op="empty", value=1))))


@pytest.mark.parametrize(
    "bad",
    [
        "not an object",
        {"v": 2, "where": None},
        {"v": 1, "where": {"op": "xor", "children": [_field()]}},
        {"v": 1, "where": {"op": "and", "children": []}},
        {"v": 1, "where": {"op": "not", "children": [_field(), _field()]}},
        {"v": 1, "where": _and({"kind": "nope"})},
        {"v": 1, "where": _and(_field(op="between", value=[1]))},
        {"v": 1, "where": _and(_field(op="~~"))},
        {"v": 1, "where": _and({"kind": "tag", "mode": "some", "tags": ["a"]})},
        {"v": 1, "where": _and(_field(value={"rel": "soon"}))},
        {"v": 1, "where": _and(_field(value=[1, 2]))},
        {"v": 1, "where": _and(_field(value=None))},
        {"v": 1, "where": None, "sort": [{"by": "field"}]},
        {"v": 1, "where": None, "sort": [{"by": "name"}] * 4},
    ],
)
def test_rejects_malformed_queries(bad: object) -> None:
    with pytest.raises(InvalidQueryError):
        parse_query(bad)


def test_depth_limit() -> None:
    where: dict[str, Any] = _and(_field())
    for _ in range(MAX_DEPTH):
        where = _and(where)
    with pytest.raises(InvalidQueryError, match="nested"):
        parse_query(_query(where))


def test_condition_limit() -> None:
    where = _and(*[_field() for _ in range(MAX_CONDITIONS + 1)])
    with pytest.raises(InvalidQueryError, match=str(MAX_CONDITIONS)):
        parse_query(_query(where))


def test_overlong_text_is_rejected() -> None:
    with pytest.raises(InvalidQueryError):
        parse_query(_query(_and({"kind": "text", "q": "x" * 201})))


def test_tag_condition_shape() -> None:
    query = parse_query(
        _query(_and({"kind": "tag", "mode": "none", "tags": ["a", "b"]}))
    )
    assert isinstance(query.where, Group)
    assert query.where.children[0] == TagCondition(mode="none", tags=("a", "b"))


@pytest.mark.parametrize(
    ("today", "rel", "expected"),
    [
        (date(2026, 10, 14), RelativeDate(amount=-30, unit="d"), date(2026, 9, 14)),
        (date(2026, 10, 14), RelativeDate(amount=1, unit="w"), date(2026, 10, 21)),
        (date(2026, 3, 31), RelativeDate(amount=-1, unit="m"), date(2026, 2, 28)),
        (date(2024, 3, 31), RelativeDate(amount=-1, unit="m"), date(2024, 2, 29)),
        (date(2024, 2, 29), RelativeDate(amount=-1, unit="y"), date(2023, 2, 28)),
    ],
)
def test_relative_dates_resolve_and_clamp(
    today: date, rel: RelativeDate, expected: date
) -> None:
    assert rel.resolve(today) == expected
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && pytest tests/modules/graph/domain/test_query.py -q`
Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

`backend/src/app/modules/graph/domain/query.py`:

```python
"""The condition tree behind advanced search: structure, limits and parsing.

A query is plain JSON on the wire and in storage. `parse_query` turns it into
frozen dataclasses, rejecting anything malformed with the path of the problem.
Checking fields against item types happens in the application layer.
"""

import calendar
import re
import uuid
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING, Final, Literal

from app.shared_kernel.errors import ValidationError

if TYPE_CHECKING:
    from app.modules.graph.domain.node import Node

QUERY_VERSION: Final = 1
MAX_DEPTH: Final = 4
MAX_CONDITIONS: Final = 50
MAX_TEXT_LENGTH: Final = 200
MAX_LIST_LENGTH: Final = 50
MAX_SORT_KEYS: Final = 3

_OPERATORS: Final = frozenset(
    {
        "=",
        "!=",
        "~",
        ">",
        ">=",
        "<",
        "<=",
        "between",
        "in",
        "empty",
        "not_empty",
        "has",
        "incomplete",
        "complete",
    }
)
_NO_VALUE: Final = frozenset({"empty", "not_empty", "incomplete", "complete"})
_DATE_OPERATORS: Final = frozenset({"=", ">", ">=", "<", "<=", "between"})
_GROUP_OPS: Final = ("and", "or", "not")
_REL: Final = re.compile(r"^([+-]?\d{1,3})([dwmy])$")


class InvalidQueryError(ValidationError):
    """Raised when a query is malformed or does not fit the item types."""

    def __init__(self, message: str, *, path: str = "") -> None:
        super().__init__(f"{path}: {message}" if path else message)
        self.path = path


def _add_months(day: date, months: int) -> date:
    index = day.year * 12 + (day.month - 1) + months
    year, month = divmod(index, 12)
    month += 1
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(day.day, last))


@dataclass(frozen=True, kw_only=True)
class RelativeDate:
    """A date as an offset from today, evaluated at read time."""

    amount: int
    unit: Literal["d", "w", "m", "y"]

    def resolve(self, today: date) -> date:
        """Return the date `amount` units from `today`, clamping month ends."""
        if self.unit == "d":
            return today + timedelta(days=self.amount)
        if self.unit == "w":
            return today + timedelta(weeks=self.amount)
        months = self.amount * (12 if self.unit == "y" else 1)
        return _add_months(today, months)


@dataclass(frozen=True, kw_only=True)
class FieldReference:
    """Another top-level field on the same item, as the value to compare with."""

    key: str


@dataclass(frozen=True, kw_only=True)
class Money:
    """An amount in one currency."""

    value: float
    currency: str


type Scalar = str | int | float | bool
type Operand = Scalar | Money | RelativeDate | FieldReference | tuple[Operand, ...]


@dataclass(frozen=True, kw_only=True)
class TextCondition:
    """Free text across name, description and searchable values."""

    q: str


@dataclass(frozen=True, kw_only=True)
class TypeCondition:
    """The item is one of these types."""

    slugs: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class FavouriteCondition:
    """The item is, or is not, a favourite."""

    value: bool


@dataclass(frozen=True, kw_only=True)
class TagCondition:
    """The item carries any, all or none of these tags."""

    mode: Literal["any", "all", "none"]
    tags: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class DateCondition:
    """Compare the day an item was created or last updated."""

    on: Literal["created", "updated"]
    op: str
    value: Operand


@dataclass(frozen=True, kw_only=True)
class FieldCondition:
    """Compare a field of one item type; `sub_key` addresses a table column."""

    type: str
    key: str
    op: str
    value: Operand | None = None
    sub_key: str | None = None


type Condition = (
    TextCondition
    | TypeCondition
    | FavouriteCondition
    | TagCondition
    | DateCondition
    | FieldCondition
)


@dataclass(frozen=True, kw_only=True)
class Group:
    """`and` / `or` over its children, or `not` over exactly one."""

    op: Literal["and", "or", "not"]
    children: tuple[Group | Condition, ...]


@dataclass(frozen=True, kw_only=True)
class SortKey:
    """One ordering key; nulls always sort last."""

    by: Literal["name", "created", "updated", "field"]
    dir: Literal["asc", "desc"] = "asc"
    type: str | None = None
    key: str | None = None


@dataclass(frozen=True, kw_only=True)
class Query:
    """A filter tree and an ordering. An empty ordering means creation order."""

    where: Group | None
    sort: tuple[SortKey, ...] = ()


type FieldKey = tuple[str, str, str | None]
type SortValue = str | float | None


@dataclass(frozen=True, kw_only=True)
class Cursor:
    """Where a page ended: the last row's sort values and id."""

    sort_values: tuple[SortValue, ...]
    id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class SearchHit:
    """A matching node with the sort values the repository ordered it by."""

    node: Node
    sort_values: tuple[SortValue, ...]


@dataclass(frozen=True, kw_only=True)
class ResolvedQuery:
    """A query plus everything adapters need to evaluate it.

    `field_kinds` holds only fields that still exist; a field condition whose
    key is absent is stale and matches nothing.
    """

    query: Query
    field_kinds: Mapping[FieldKey, str]
    search_exclusions: Mapping[str, Sequence[str]]
    today: date


def walk_conditions(
    group: Group | None, path: str = "where"
) -> Iterator[tuple[str, Condition]]:
    """Yield every condition with its JSON path, depth first, in order."""
    if group is None:
        return
    for index, child in enumerate(group.children):
        child_path = f"{path}.children[{index}]"
        if isinstance(child, Group):
            yield from walk_conditions(child, child_path)
        else:
            yield child_path, child


def _string(raw: object, path: str, *, name: str) -> str:
    if not isinstance(raw, str) or not 1 <= len(raw) <= MAX_TEXT_LENGTH:
        msg = f"'{name}' must be text of 1 to {MAX_TEXT_LENGTH} characters."
        raise InvalidQueryError(msg, path=path)
    return raw


def _string_list(raw: object, path: str, *, name: str) -> tuple[str, ...]:
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_LIST_LENGTH:
        msg = f"'{name}' must be a list of 1 to {MAX_LIST_LENGTH} texts."
        raise InvalidQueryError(msg, path=path)
    return tuple(_string(item, path, name=name) for item in raw)


def _number(raw: object) -> bool:
    return isinstance(raw, int | float) and not isinstance(raw, bool)


def _operand(raw: object, path: str) -> Operand:
    if isinstance(raw, bool | int | float):
        return raw
    if isinstance(raw, str):
        if len(raw) > MAX_TEXT_LENGTH:
            raise InvalidQueryError("That value is too long.", path=path)
        return raw
    if isinstance(raw, Mapping):
        keys = set(raw)
        if keys == {"rel"}:
            match = _REL.match(str(raw["rel"]))
            if match is None:
                raise InvalidQueryError("Use a relative date like -30d.", path=path)
            return RelativeDate(
                amount=int(match.group(1)),
                unit=match.group(2),  # type: ignore[arg-type]
            )
        if keys == {"ref"}:
            return FieldReference(key=_string(raw["ref"], path, name="ref"))
        if keys == {"value", "currency"} and _number(raw["value"]):
            return Money(
                value=float(raw["value"]),
                currency=_string(raw["currency"], path, name="currency"),
            )
    raise InvalidQueryError("That is not a valid value.", path=path)


def _value(op: str, data: Mapping[str, object], path: str) -> Operand | None:
    if op in _NO_VALUE:
        if "value" in data:
            raise InvalidQueryError(f"'{op}' takes no value.", path=path)
        return None
    if "value" not in data:
        raise InvalidQueryError(f"'{op}' needs a value.", path=path)
    raw = data["value"]
    if op == "between":
        if not isinstance(raw, list) or len(raw) != 2:  # noqa: PLR2004
            raise InvalidQueryError("'between' needs [low, high].", path=path)
        return tuple(_operand(item, path) for item in raw)
    if op in {"in", "has"}:
        if op == "has" and not isinstance(raw, list):
            return (_operand(raw, path),)
        if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_LIST_LENGTH:
            msg = f"'{op}' needs 1 to {MAX_LIST_LENGTH} values."
            raise InvalidQueryError(msg, path=path)
        return tuple(_operand(item, path) for item in raw)
    return _operand(raw, path)


class _Parser:
    def __init__(self) -> None:
        self._conditions = 0

    def group(self, data: object, path: str, depth: int) -> Group:
        if depth > MAX_DEPTH:
            raise InvalidQueryError(
                f"Groups can be nested up to {MAX_DEPTH} deep.", path=path
            )
        if not isinstance(data, Mapping) or data.get("op") not in _GROUP_OPS:
            raise InvalidQueryError("Expected a group: and, or or not.", path=path)
        children = data.get("children")
        if not isinstance(children, list) or not children:
            raise InvalidQueryError("A group needs at least one child.", path=path)
        if data["op"] == "not" and len(children) != 1:
            raise InvalidQueryError("'not' takes exactly one child.", path=path)
        return Group(
            op=data["op"],
            children=tuple(
                self.child(child, f"{path}.children[{index}]", depth)
                for index, child in enumerate(children)
            ),
        )

    def child(self, data: object, path: str, depth: int) -> Group | Condition:
        if isinstance(data, Mapping) and "kind" not in data:
            return self.group(data, path, depth + 1)
        return self.condition(data, path)

    def condition(self, data: object, path: str) -> Condition:
        self._conditions += 1
        if self._conditions > MAX_CONDITIONS:
            raise InvalidQueryError(
                f"A query can have up to {MAX_CONDITIONS} conditions.", path=path
            )
        if not isinstance(data, Mapping):
            raise InvalidQueryError("Expected a condition.", path=path)
        match data.get("kind"):
            case "text":
                return TextCondition(q=_string(data.get("q"), path, name="q"))
            case "type":
                return TypeCondition(
                    slugs=_string_list(data.get("in"), path, name="in")
                )
            case "favourite":
                if not isinstance(data.get("value"), bool):
                    raise InvalidQueryError("'value' must be true or false.", path=path)
                return FavouriteCondition(value=data["value"])
            case "tag":
                if data.get("mode") not in {"any", "all", "none"}:
                    raise InvalidQueryError(
                        "'mode' must be any, all or none.", path=path
                    )
                return TagCondition(
                    mode=data["mode"],
                    tags=_string_list(data.get("tags"), path, name="tags"),
                )
            case "date":
                op = data.get("op")
                if (
                    data.get("on") not in {"created", "updated"}
                    or op not in _DATE_OPERATORS
                ):
                    raise InvalidQueryError(
                        "Use on: created or updated with a comparison.", path=path
                    )
                return DateCondition(on=data["on"], op=op, value=_value(op, data, path))  # type: ignore[arg-type]
            case "field":
                op = data.get("op")
                if not isinstance(op, str) or op not in _OPERATORS:
                    raise InvalidQueryError("Unknown operator.", path=path)
                sub_key = data.get("sub_key")
                return FieldCondition(
                    type=_string(data.get("type"), path, name="type"),
                    key=_string(data.get("key"), path, name="key"),
                    sub_key=None
                    if sub_key is None
                    else _string(sub_key, path, name="sub_key"),
                    op=op,
                    value=_value(op, data, path),
                )
        raise InvalidQueryError("Unknown condition kind.", path=path)

    def sort(self, raw: object) -> tuple[SortKey, ...]:
        if not isinstance(raw, list) or len(raw) > MAX_SORT_KEYS:
            raise InvalidQueryError(f"Sort by up to {MAX_SORT_KEYS} keys.", path="sort")
        keys: list[SortKey] = []
        for index, item in enumerate(raw):
            path = f"sort[{index}]"
            if not isinstance(item, Mapping) or item.get("by") not in {
                "name",
                "created",
                "updated",
                "field",
            }:
                raise InvalidQueryError(
                    "Sort by name, created, updated or field.", path=path
                )
            if item.get("dir", "asc") not in {"asc", "desc"}:
                raise InvalidQueryError("'dir' must be asc or desc.", path=path)
            type_ = key = None
            if item["by"] == "field":
                type_ = _string(item.get("type"), path, name="type")
                key = _string(item.get("key"), path, name="key")
            keys.append(
                SortKey(by=item["by"], dir=item.get("dir", "asc"), type=type_, key=key)  # type: ignore[arg-type]
            )
        return tuple(keys)


def parse_query(data: object) -> Query:
    """Parse a query from its JSON form.

    Raises:
        InvalidQueryError: If the shape, a limit or a value is wrong; the error
            carries the JSON path of the first problem.
    """
    if not isinstance(data, Mapping):
        raise InvalidQueryError("The query must be an object.")
    if data.get("v") != QUERY_VERSION:
        raise InvalidQueryError(
            f"Unsupported query version; expected {QUERY_VERSION}.", path="v"
        )
    parser = _Parser()
    raw_where = data.get("where")
    where = None if raw_where is None else parser.group(raw_where, "where", 1)
    return Query(where=where, sort=parser.sort(data.get("sort", [])))
```

The root group is depth 1 and `child()` passes `depth + 1` to each nested group, so `test_depth_limit` (which nests `MAX_DEPTH + 1` groups) fails exactly when a fifth level appears. Keep `MAX_DEPTH = 4`, as the spec says. Run `ruff format` on the file afterwards; it wraps the long lines above.

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && pytest tests/modules/graph/domain/test_query.py -q && cd .. && poe lint-backend`
Expected: PASS; lint clean (fix any `PLR2004` / `C901` by extracting helpers, not by adding `noqa` beyond the one shown).

- [ ] **Step 5: Coverage and types**

Run: `poe typecheck-backend`
Expected: PASS. Every branch of `query.py` should be covered; add a test for any miss (domain is 100%).

**Checkpoint:** user may commit.

---

### Task 3: Field resolution and validation (application)

**Files:**
- Create: `backend/src/app/modules/graph/application/query_resolution.py`
- Create: `backend/tests/modules/graph/application/test_query_resolution.py`

**Interfaces:**
- Consumes: `parse_query`, `walk_conditions`, `FieldCondition`, `DateCondition`, `Money`, `RelativeDate`, `FieldReference`, `FieldKey`, `InvalidQueryError` (Task 2); `KIND_OPERATORS`, `REF_KINDS`, `NO_VALUE_OPERATORS`, `kind_of` (Task 1); `NAMESPACE` from `schema_meta`.
- Produces: `QueryWarning(path: str, message: str)`, `FieldResolution(kinds: dict[FieldKey, str], warnings: list[QueryWarning])`, `resolve_fields(query: Query, schemas: Mapping[str, Mapping[str, Any]]) -> FieldResolution`, `SORTABLE_KINDS: frozenset[str]`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/modules/graph/application/test_query_resolution.py`:

```python
from typing import Any

import pytest

from app.modules.graph.application.query_resolution import resolve_fields
from app.modules.graph.domain.query import InvalidQueryError, Query, parse_query

SCHEMAS: dict[str, dict[str, Any]] = {
    "film": {
        "type": "object",
        "properties": {
            "rating": {"type": "number", "x-menagerist": {"kind": "rating"}},
            "year": {"type": "string", "x-menagerist": {"kind": "partialdate"}},
            "old": {"type": "string", "x-menagerist": {"archived": True}},
            "genres": {"type": "array", "items": {"type": "string", "enum": ["a"]}},
            "stock": {"type": "number"},
            "reorder_at": {"type": "number"},
            "title_en": {"type": "string"},
            "cast": {
                "type": "array",
                "items": {"type": "object", "properties": {"role": {"type": "string"}}},
                "x-menagerist": {"kind": "group"},
            },
        },
    }
}


def _where(*children: dict[str, Any]) -> Query:
    return parse_query({"v": 1, "where": {"op": "and", "children": list(children)}})


def _f(key: str, op: str, value: Any = None, **extra: Any) -> dict[str, Any]:  # noqa: ANN401
    cond = {"kind": "field", "type": "film", "key": key, "op": op, **extra}
    if value is not None:
        cond["value"] = value
    return cond


def test_resolves_known_fields() -> None:
    result = resolve_fields(
        _where(_f("rating", ">=", 4), _f("cast", "~", "x", sub_key="role")), SCHEMAS
    )
    assert result.kinds == {
        ("film", "rating", None): "rating",
        ("film", "cast", "role"): "text",
    }
    assert result.warnings == []


@pytest.mark.parametrize(
    ("condition", "fragment"),
    [
        (_f("old", "=", "x"), "no longer exists"),
        (_f("missing", "=", "x"), "no longer exists"),
        (
            {"kind": "field", "type": "gone", "key": "rating", "op": ">=", "value": 1},
            "no longer exists",
        ),
        (_f("cast", "=", "x", sub_key="gone"), "no longer exists"),
    ],
)
def test_stale_fields_warn_instead_of_failing(
    condition: dict[str, Any], fragment: str
) -> None:
    result = resolve_fields(_where(condition), SCHEMAS)
    assert result.kinds == {}
    assert [w.path for w in result.warnings] == ["where.children[0]"]
    assert fragment in result.warnings[0].message


@pytest.mark.parametrize(
    "condition",
    [
        _f("rating", "~", "x"),  # operator not offered for the kind
        _f("rating", ">=", "high"),  # text value for a number
        _f("year", "=", 1984),  # number for a partial date
        _f("year", "=", "19x4"),  # not a partial date
        _f("genres", "has", 3),
        _f("rating", "=", {"ref": "title_en"}),  # reference of a different kind
        _f("year", "=", {"ref": "year"}),  # kind that cannot take references
    ],
)
def test_wrong_operator_or_value_is_an_error(condition: dict[str, Any]) -> None:
    with pytest.raises(InvalidQueryError, match=r"where\.children\[0\]"):
        resolve_fields(_where(condition), SCHEMAS)


def test_field_reference_to_a_stale_field_warns() -> None:
    result = resolve_fields(_where(_f("stock", "<=", {"ref": "gone"})), SCHEMAS)
    assert result.kinds == {}
    assert len(result.warnings) == 1


def test_field_reference_of_the_same_kind_resolves() -> None:
    result = resolve_fields(_where(_f("stock", "<=", {"ref": "reorder_at"})), SCHEMAS)
    assert result.kinds == {("film", "stock", None): "number"}


def test_sort_keys_resolve_and_must_be_sortable() -> None:
    sort_rating = {
        "v": 1,
        "where": None,
        "sort": [{"by": "field", "type": "film", "key": "rating"}],
    }
    assert resolve_fields(parse_query(sort_rating), SCHEMAS).kinds == {
        ("film", "rating", None): "rating"
    }
    sort_genres = {
        "v": 1,
        "where": None,
        "sort": [{"by": "field", "type": "film", "key": "genres"}],
    }
    with pytest.raises(InvalidQueryError, match=r"sort\[0\]"):
        resolve_fields(parse_query(sort_genres), SCHEMAS)
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && pytest tests/modules/graph/application/test_query_resolution.py -q`
Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

`backend/src/app/modules/graph/application/query_resolution.py`:

```python
"""Check a parsed query against item-type schemas.

A field that no longer exists is a warning and the condition matches nothing.
A wrong operator or value for a field that does exist is a 400.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any, Final

from app.modules.graph.application.field_kinds import (
    KIND_OPERATORS,
    NO_VALUE_OPERATORS,
    REF_KINDS,
    kind_of,
)
from app.modules.graph.application.schema_meta import NAMESPACE
from app.modules.graph.domain.query import (
    FieldCondition,
    FieldKey,
    FieldReference,
    InvalidQueryError,
    Money,
    Operand,
    Query,
    RelativeDate,
    walk_conditions,
)

SORTABLE_KINDS: Final = frozenset(
    {
        "text",
        "url",
        "email",
        "phone",
        "number",
        "duration",
        "rating",
        "money",
        "date",
        "partialdate",
        "choice",
    }
)
_PARTIAL_DATE: Final = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")
_TEXT_KINDS: Final = frozenset(
    {"text", "url", "email", "phone", "longtext", "choice", "multichoice"}
)


@dataclass(frozen=True)
class QueryWarning:
    """A part of a query that no longer applies."""

    path: str
    message: str


@dataclass(frozen=True)
class FieldResolution:
    """Kinds of the fields that still exist, and what went stale."""

    kinds: dict[FieldKey, str]
    warnings: list[QueryWarning]


def _meta(prop: object) -> Mapping[str, Any]:
    meta = prop.get(NAMESPACE) if isinstance(prop, Mapping) else None
    return meta if isinstance(meta, Mapping) else {}


def _find(
    schemas: Mapping[str, Mapping[str, Any]],
    type_slug: str,
    key: str,
    sub_key: str | None,
) -> tuple[Mapping[str, Any] | None, str | None]:
    """Return the live property, or None plus the reason it is gone."""
    schema = schemas.get(type_slug)
    if schema is None:
        return None, f"The item type '{type_slug}' no longer exists."
    properties = schema.get("properties")
    prop = properties.get(key) if isinstance(properties, Mapping) else None
    if not isinstance(prop, Mapping) or _meta(prop).get("archived") is True:
        return None, f"The field '{key}' no longer exists on '{type_slug}'."
    if sub_key is None:
        return prop, None
    items = prop.get("items")
    inner = items.get("properties") if isinstance(items, Mapping) else None
    sub = inner.get(sub_key) if isinstance(inner, Mapping) else None
    if not isinstance(sub, Mapping) or _meta(sub).get("archived") is True:
        return None, f"The column '{sub_key}' no longer exists on '{key}'."
    return sub, None


def _fits(kind: str, operand: Operand) -> bool:
    if isinstance(operand, RelativeDate):
        return kind in {"date", "partialdate"}
    if kind in {"number", "duration", "rating"}:
        return isinstance(operand, int | float) and not isinstance(operand, bool)
    if kind == "money":
        return isinstance(operand, Money)
    if kind == "date":
        if not isinstance(operand, str):
            return False
        try:
            date.fromisoformat(operand)
        except ValueError:
            return False
        return True
    if kind == "partialdate":
        return isinstance(operand, str) and _PARTIAL_DATE.match(operand) is not None
    if kind == "boolean":
        return isinstance(operand, bool)
    if kind in _TEXT_KINDS:
        return isinstance(operand, str)
    return False


def _operands(value: Operand | None) -> tuple[Operand, ...]:
    if value is None:
        return ()
    return value if isinstance(value, tuple) else (value,)


class _Resolver:
    def __init__(self, schemas: Mapping[str, Mapping[str, Any]]) -> None:
        self._schemas = schemas
        self.kinds: dict[FieldKey, str] = {}
        self.warnings: list[QueryWarning] = []

    def field(self, condition: FieldCondition, path: str) -> None:
        prop, gone = _find(
            self._schemas, condition.type, condition.key, condition.sub_key
        )
        if prop is None:
            self.warnings.append(QueryWarning(path, gone or ""))
            return
        kind = kind_of(prop)
        if kind is None:
            raise InvalidQueryError(
                f"The field '{condition.key}' cannot be filtered.", path=path
            )
        if condition.op not in KIND_OPERATORS[kind]:
            raise InvalidQueryError(
                f"'{condition.op}' is not available for {kind} fields.", path=path
            )
        stale_ref = False
        if condition.op not in NO_VALUE_OPERATORS:
            for operand in _operands(condition.value):
                if isinstance(operand, FieldReference):
                    stale_ref |= self._reference(condition, operand, kind, path)
                elif not _fits(kind, operand):
                    raise InvalidQueryError(
                        f"That value does not fit a {kind} field.", path=path
                    )
        if not stale_ref:
            self.kinds[(condition.type, condition.key, condition.sub_key)] = kind

    def _reference(
        self, condition: FieldCondition, ref: FieldReference, kind: str, path: str
    ) -> bool:
        """Check a field reference; return True when its target is gone."""
        if kind not in REF_KINDS or condition.sub_key is not None:
            raise InvalidQueryError(
                f"A {kind} field cannot be compared with another field.", path=path
            )
        target, gone = _find(self._schemas, condition.type, ref.key, None)
        if target is None:
            self.warnings.append(QueryWarning(path, gone or ""))
            return True
        if kind_of(target) != kind:
            raise InvalidQueryError(
                f"'{ref.key}' is not a {kind} field, so it cannot be compared.",
                path=path,
            )
        return False

    def sort(self, index: int, type_slug: str, key: str) -> None:
        path = f"sort[{index}]"
        prop, gone = _find(self._schemas, type_slug, key, None)
        if prop is None:
            self.warnings.append(QueryWarning(path, gone or ""))
            return
        kind = kind_of(prop)
        if kind not in SORTABLE_KINDS:
            raise InvalidQueryError(
                f"The field '{key}' cannot be sorted on.", path=path
            )
        self.kinds[(type_slug, key, None)] = kind


def resolve_fields(
    query: Query, schemas: Mapping[str, Mapping[str, Any]]
) -> FieldResolution:
    """Resolve every field the query names against `schemas` (slug to schema).

    Raises:
        InvalidQueryError: For an operator or value that does not fit a field
            that exists. Fields that are gone become warnings.
    """
    resolver = _Resolver(schemas)
    for path, condition in walk_conditions(query.where):
        if isinstance(condition, FieldCondition):
            resolver.field(condition, path)
    for index, key in enumerate(query.sort):
        if key.by == "field" and key.type and key.key:
            resolver.sort(index, key.type, key.key)
    return FieldResolution(kinds=resolver.kinds, warnings=resolver.warnings)
```

`DateCondition` values are checked in the domain (operator set) and at evaluation (strings must parse): add to `Resolver` a `date_condition` check that each operand is an ISO date string or `RelativeDate`, raising `InvalidQueryError` with the path, and a test `test_date_condition_value_must_be_a_date` using `{"kind": "date", "on": "created", "op": ">=", "value": "soon"}`.

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && pytest tests/modules/graph/application/test_query_resolution.py -q && cd .. && poe typecheck-backend`
Expected: PASS. Application layer is 100%, so add tests for any uncovered branch.

**Checkpoint:** user may commit.

---

### Task 4: Port, in-memory evaluator and the shared scenarios

**Files:**
- Create: `adapters/persistence/text_match.py`, `adapters/persistence/query_eval.py`
- Modify: `adapters/persistence/in_memory_node_repository.py`, `ports/node_repository.py`
- Create: `backend/tests/modules/graph/adapters/persistence/test_node_search.py`

**Interfaces:**
- Consumes: Task 2 types.
- Produces (the port, used by Tasks 6 and 8):

```python
async def search(
    self,
    *,
    scope: AccessScope,
    resolved: ResolvedQuery,
    after: Cursor | None,
    limit: int,
) -> builtins.list[SearchHit]: ...
async def search_count(self, *, scope: AccessScope, resolved: ResolvedQuery) -> int: ...
```

  Results are ordered by the query's sort keys (nulls last), then by id. `after` returns only rows strictly later in that order.
- Produces in `query_eval.py`: `matches(node, group, ctx) -> bool`, `sort_values(node, ctx) -> tuple[SortValue, ...]`, `is_after(hit, cursor, sort) -> bool`.

- [ ] **Step 1: Move the text helpers**

Create `text_match.py` containing the existing `_fold`, `_scalar_values` and `_matches` from `in_memory_node_repository.py`, renamed `fold`, `scalar_values`, `text_matches` (bodies unchanged), plus:

```python
def sort_key(text: str) -> str:
    """Lower-case `text` and strip accents: the order names are sorted in."""
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()
```

Update `in_memory_node_repository.py` to import them. Run `cd backend && pytest tests/modules/graph -q -m "not integration"`; expected PASS (pure move).

- [ ] **Step 2: Write the shared scenario tests (failing)**

`backend/tests/modules/graph/adapters/persistence/test_node_search.py`. This file is the contract between the two adapters: the same scenarios run against both, as in `test_node_repository_scope.py`.

```python
import uuid
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

import pytest

from app.modules.graph.adapters.persistence.in_memory_node_repository import (
    InMemoryNodeRepository,
)
from app.modules.graph.adapters.persistence.node_repository import (
    SqlAlchemyNodeRepository,
)
from app.modules.graph.application.query_resolution import resolve_fields
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.query import Cursor, ResolvedQuery, parse_query
from app.shared_kernel.access_scope import AccessScope

if TYPE_CHECKING:
    from app.modules.graph.ports.node_repository import NodeRepository

ALICE = uuid.UUID(int=201)
BOB = uuid.UUID(int=202)
TODAY = date(2026, 10, 14)

SCHEMAS: dict[str, dict[str, Any]] = {
    "film": {
        "type": "object",
        "properties": {
            "year": {"type": "string", "x-menagerist": {"kind": "partialdate"}},
            "runtime": {"type": "number", "x-menagerist": {"kind": "duration"}},
            "rating": {"type": "number", "x-menagerist": {"kind": "rating"}},
            "seen": {"type": "boolean"},
            "genres": {
                "type": "array",
                "items": {"type": "string", "enum": ["scifi", "horror", "drama"]},
            },
            "director": {"type": "string"},
            "notes": {"type": "string"},
        },
    },
    "part": {
        "type": "object",
        "properties": {
            "stock": {"type": "number"},
            "reorder_at": {"type": "number"},
            "price": {"type": "object", "x-menagerist": {"kind": "money"}},
            "steps": {"type": "array", "x-menagerist": {"kind": "checklist"}},
        },
    },
}

_DATA: list[tuple[str, str, dict[str, Any], dict[str, Any]]] = [
    (
        "Alien",
        "film",
        {
            "year": "1979",
            "runtime": 7020,
            "rating": 5,
            "seen": True,
            "genres": ["scifi", "horror"],
        },
        {"tags": ["classic"], "favourite": True},
    ),
    (
        "Blade Runner",
        "film",
        {
            "year": "1982-06",
            "runtime": 7020,
            "rating": 4,
            "seen": False,
            "genres": ["scifi"],
        },
        {},
    ),
    (
        "Casablanca",
        "film",
        {
            "year": "1942",
            "runtime": 6120,
            "rating": 5,
            "seen": True,
            "genres": ["drama"],
        },
        {"tags": ["classic"]},
    ),
    (
        "Café Society",
        "film",
        {"year": "2016-05-13", "director": "Woody Allen", "notes": "50% off_day"},
        {},
    ),
    ("Bad data", "film", {"year": 1999, "rating": "abc", "runtime": "long"}, {}),
    (
        "Resistor",
        "part",
        {
            "stock": 3,
            "reorder_at": 10,
            "price": {"value": 0.1, "currency": "GBP"},
            "steps": [{"text": "a", "done": True}],
        },
        {},
    ),
    (
        "Capacitor",
        "part",
        {
            "stock": 50,
            "reorder_at": 10,
            "price": {"value": 0.3, "currency": "USD"},
            "steps": [{"text": "a", "done": True}, {"text": "b", "done": False}],
        },
        {},
    ),
]


@pytest.fixture(
    params=["in_memory", pytest.param("postgres", marks=pytest.mark.integration)]
)
async def repository(request: pytest.FixtureRequest) -> NodeRepository:
    """The same scenarios run against both adapters, seeded with the same items."""
    repo: NodeRepository
    if request.param == "in_memory":
        repo = InMemoryNodeRepository()
    else:
        repo = SqlAlchemyNodeRepository(request.getfixturevalue("db_session"))
    for name, type_slug, attributes, extra in _DATA:
        node = Node.create(
            owner_id=ALICE, name=name, type=type_slug, attributes=attributes
        )
        node.tags = extra.get("tags", [])
        node.favourite = extra.get("favourite", False)
        await repo.add(node)
    await repo.add(
        Node.create(owner_id=BOB, name="Secret", type="film", attributes={"rating": 5})
    )
    return repo


def _resolve(raw: dict[str, Any]) -> ResolvedQuery:
    query = parse_query(raw)
    resolution = resolve_fields(query, SCHEMAS)
    return ResolvedQuery(
        query=query, field_kinds=resolution.kinds, search_exclusions={}, today=TODAY
    )


def _where(*children: dict[str, Any], op: str = "and", **extra: Any) -> dict[str, Any]:  # noqa: ANN401
    return {"v": 1, "where": {"op": op, "children": list(children)}, **extra}


def _f(
    type_: str, key: str, op: str, value: Any = None, **extra: Any
) -> dict[str, Any]:  # noqa: ANN401
    cond: dict[str, Any] = {
        "kind": "field",
        "type": type_,
        "key": key,
        "op": op,
        **extra,
    }
    if value is not None:
        cond["value"] = value
    return cond


async def _names(
    repo: NodeRepository, raw: dict[str, Any], scope: AccessScope | None = None
) -> list[str]:
    hits = await repo.search(
        scope=scope or AccessScope.of(ALICE),
        resolved=_resolve(raw),
        after=None,
        limit=100,
    )
    return [hit.node.name for hit in hits]


_FILM = {"kind": "type", "in": ["film"]}

CASES: list[tuple[str, dict[str, Any], set[str]]] = [
    (
        "rating at least 4",
        _where(_f("film", "rating", ">=", 4)),
        {"Alien", "Blade Runner", "Casablanca"},
    ),
    (
        "not rating 4+ among films includes missing and wrong-typed",
        _where(_FILM, {"op": "not", "children": [_f("film", "rating", ">=", 4)]}),
        {"Café Society", "Bad data"},
    ),
    (
        "partial date year equals",
        _where(_f("film", "year", "=", "1982")),
        {"Blade Runner"},
    ),
    (
        "partial date between decades",
        _where(_f("film", "year", "between", ["1980", "1989"])),
        {"Blade Runner"},
    ),
    (
        "partial date at or after a month",
        _where(_f("film", "year", ">=", "2016-05")),
        {"Café Society"},
    ),
    (
        "field reference",
        _where(_f("part", "stock", "<=", {"ref": "reorder_at"})),
        {"Resistor"},
    ),
    (
        "multichoice has one",
        _where(_f("film", "genres", "has", "scifi")),
        {"Alien", "Blade Runner"},
    ),
    (
        "multichoice has all",
        _where(_f("film", "genres", "has", ["scifi", "horror"])),
        {"Alien"},
    ),
    (
        "money matches only its currency",
        _where(_f("part", "price", ">=", {"value": 0.05, "currency": "GBP"})),
        {"Resistor"},
    ),
    (
        "text is accent-insensitive",
        _where({"kind": "text", "q": "cafe"}),
        {"Café Society"},
    ),
    (
        "text treats % and _ literally",
        _where({"kind": "text", "q": "50% off_day"}),
        {"Café Society"},
    ),
    (
        "text does not treat _ as a wildcard",
        _where({"kind": "text", "q": "off_d_y"}),
        set(),
    ),
    (
        "tag any",
        _where({"kind": "tag", "mode": "any", "tags": ["classic"]}),
        {"Alien", "Casablanca"},
    ),
    (
        "tag none",
        _where(_FILM, {"kind": "tag", "mode": "none", "tags": ["classic"]}),
        {"Blade Runner", "Café Society", "Bad data"},
    ),
    ("favourite", _where({"kind": "favourite", "value": True}), {"Alien"}),
    (
        "or across types",
        _where(_f("film", "rating", "=", 5), _f("part", "stock", "<", 5), op="or"),
        {"Alien", "Casablanca", "Resistor"},
    ),
    ("empty means missing", _where(_f("film", "rating", "empty")), {"Café Society"}),
    ("not empty", _where(_f("film", "director", "not_empty")), {"Café Society"}),
    ("boolean", _where(_f("film", "seen", "=", True)), {"Alien", "Casablanca"}),
    (
        "boolean not equal includes missing",
        _where(_FILM, _f("film", "seen", "!=", True)),
        {"Blade Runner", "Café Society", "Bad data"},
    ),
    ("duration at most", _where(_f("film", "runtime", "<=", 6500)), {"Casablanca"}),
    (
        "wrong-typed value never matches or errors",
        _where(_f("film", "runtime", ">", 0)),
        {"Alien", "Blade Runner", "Casablanca"},
    ),
    ("checklist incomplete", _where(_f("part", "steps", "incomplete")), {"Capacitor"}),
    ("checklist complete", _where(_f("part", "steps", "complete")), {"Resistor"}),
    (
        "created within the last day",
        _where({"kind": "date", "on": "created", "op": ">=", "value": {"rel": "-1d"}}),
        {
            "Alien",
            "Blade Runner",
            "Casablanca",
            "Café Society",
            "Bad data",
            "Resistor",
            "Capacitor",
        },
    ),
    (
        "created before yesterday",
        _where({"kind": "date", "on": "created", "op": "<", "value": {"rel": "-1d"}}),
        set(),
    ),
    (
        "or group cannot reach another user's items",
        _where(_FILM, {"kind": "text", "q": "secret"}, op="or"),
        {"Alien", "Blade Runner", "Casablanca", "Café Society", "Bad data"},
    ),
    ("stale field matches nothing", _where(_f("film", "gone", "=", "x")), set()),
    (
        "not of a stale field matches everything",
        {"v": 1, "where": {"op": "not", "children": [_f("film", "gone", "=", "x")]}},
        {n for n, *_ in _DATA},
    ),
]


@pytest.mark.parametrize(("label", "raw", "expected"), CASES, ids=[c[0] for c in CASES])
async def test_scenario(
    repository: NodeRepository, label: str, raw: dict[str, Any], expected: set[str]
) -> None:
    del label
    assert set(await _names(repository, raw)) == expected
    resolved = _resolve(raw)
    assert await repository.search_count(
        scope=AccessScope.of(ALICE), resolved=resolved
    ) == len(expected)


async def test_no_where_returns_everything_in_creation_order(
    repository: NodeRepository,
) -> None:
    assert await _names(repository, {"v": 1, "where": None}) == [n for n, *_ in _DATA]


async def test_everyone_scope_sees_every_owner(repository: NodeRepository) -> None:
    assert "Secret" in await _names(
        repository, {"v": 1, "where": None}, AccessScope.everyone()
    )


async def test_sort_by_field_puts_nulls_last_and_breaks_ties_by_creation(
    repository: NodeRepository,
) -> None:
    raw = _where(
        _FILM, sort=[{"by": "field", "type": "film", "key": "rating", "dir": "desc"}]
    )
    assert await _names(repository, raw) == [
        "Alien",
        "Casablanca",
        "Blade Runner",
        "Café Society",
        "Bad data",
    ]


async def test_sort_by_name_ignores_case_and_accents(
    repository: NodeRepository,
) -> None:
    names = await _names(repository, _where(_FILM, sort=[{"by": "name"}]))
    assert names == ["Alien", "Bad data", "Blade Runner", "Café Society", "Casablanca"]


@pytest.mark.parametrize("direction", ["asc", "desc"])
async def test_paging_visits_every_item_once(
    repository: NodeRepository, direction: str
) -> None:
    raw = _where(
        _FILM, sort=[{"by": "field", "type": "film", "key": "rating", "dir": direction}]
    )
    resolved = _resolve(raw)
    seen: list[str] = []
    after: Cursor | None = None
    while True:
        hits = await repository.search(
            scope=AccessScope.of(ALICE), resolved=resolved, after=after, limit=2
        )
        seen += [hit.node.name for hit in hits]
        if len(hits) < 2:
            break
        last = hits[-1]
        after = Cursor(sort_values=last.sort_values, id=last.node.id)
    assert sorted(seen) == sorted(
        ["Alien", "Blade Runner", "Casablanca", "Café Society", "Bad data"]
    )
    assert len(seen) == len(set(seen))


async def test_paging_continues_after_the_cursor_row_is_deleted(
    repository: NodeRepository,
) -> None:
    raw = _where(_FILM, sort=[{"by": "name"}])
    resolved = _resolve(raw)
    first = await repository.search(
        scope=AccessScope.of(ALICE), resolved=resolved, after=None, limit=2
    )
    victim = first[-1].node
    victim.deleted_at = datetime.now(UTC)
    await repository.save(victim)
    cursor = Cursor(sort_values=first[-1].sort_values, id=victim.id)
    rest = await repository.search(
        scope=AccessScope.of(ALICE), resolved=resolved, after=cursor, limit=10
    )
    assert [hit.node.name for hit in rest] == ["Café Society", "Casablanca"]
```

(`Node.create` argument names and `deleted_at` handling: check `domain/node.py` and adapt: if the entity exposes `soft_delete()`, use it. Scenario expectations are the contract; do not weaken them to make an adapter pass.)

- [ ] **Step 3: Run to verify failure**

Run: `cd backend && pytest tests/modules/graph/adapters/persistence/test_node_search.py -q -m "not integration"`
Expected: FAIL, `AttributeError: 'InMemoryNodeRepository' object has no attribute 'search'` (or collection errors until the port types exist).

- [ ] **Step 4: Extend the port**

In `ports/node_repository.py` add (under TYPE_CHECKING imports `Cursor`, `ResolvedQuery`, `SearchHit`):

```python
async def search(
    self,
    *,
    scope: AccessScope,
    resolved: ResolvedQuery,
    after: Cursor | None,
    limit: int,
) -> builtins.list[SearchHit]:
    """Return live nodes matching the query, in its order, one page.

    Order is the query's sort keys (nulls last) then id. `after` keeps only
    rows strictly later in that order. A field condition whose key is not in
    `resolved.field_kinds` matches nothing. Stored values of the wrong JSON
    type never match and never raise.
    """
    ...


async def search_count(self, *, scope: AccessScope, resolved: ResolvedQuery) -> int:
    """Return how many live nodes in `scope` match the query."""
    ...
```

- [ ] **Step 5: Write the evaluator**

`adapters/persistence/query_eval.py`:

```python
"""Evaluate a query tree against a node in Python.

The reference semantics: `query_sql.py` must agree with this module on every
scenario in `test_node_search.py`.
"""

from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, date
from typing import TYPE_CHECKING, Any

from app.modules.graph.adapters.persistence.text_match import (
    fold,
    sort_key,
    text_matches,
)
from app.modules.graph.domain.query import (
    Condition,
    Cursor,
    DateCondition,
    FavouriteCondition,
    FieldCondition,
    FieldReference,
    Group,
    Money,
    Operand,
    RelativeDate,
    ResolvedQuery,
    SearchHit,
    SortKey,
    SortValue,
    TagCondition,
    TextCondition,
    TypeCondition,
)

if TYPE_CHECKING:
    from app.modules.graph.domain.node import Node

_NUMERIC = frozenset({"number", "duration", "rating"})
_TEXTUAL = frozenset({"text", "url", "email", "phone", "longtext"})
_MISSING = object()


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _compare(op: str, left: Any, right: Any) -> bool:  # noqa: ANN401
    match op:
        case "=":
            return bool(left == right)
        case ">":
            return bool(left > right)
        case ">=":
            return bool(left >= right)
        case "<":
            return bool(left < right)
        case "<=":
            return bool(left <= right)
    raise AssertionError(op)


def _is_empty(value: object) -> bool:
    return value is None or value in ("", [])


def _resolve(operand: Operand, node: Node, kind: str, today: date) -> Any:  # noqa: ANN401
    """Turn an operand into a plain comparable value, or `_MISSING`."""
    if isinstance(operand, tuple):
        parts = [_resolve(item, node, kind, today) for item in operand]
        return _MISSING if any(p is _MISSING for p in parts) else tuple(parts)
    if isinstance(operand, RelativeDate):
        return operand.resolve(today).isoformat()
    if isinstance(operand, FieldReference):
        other = node.attributes.get(operand.key)
        if kind == "money":
            amount = _number(other.get("value")) if isinstance(other, Mapping) else None
            if amount is None:
                return _MISSING
            return Money(value=amount, currency=str(other.get("currency")))
        if kind == "date":
            return other if isinstance(other, str) else _MISSING
        number = _number(other)
        return _MISSING if number is None else number
    return operand


def _test(kind: str, op: str, value: object, operand: Any) -> bool:  # noqa: ANN401, C901, PLR0911, PLR0912
    """Whether a present, non-null `value` satisfies `op` against `operand`."""
    if kind in _NUMERIC:
        number = _number(value)
        if number is None:
            return False
        if op == "between":
            return bool(operand[0] <= number <= operand[1])
        return _compare(op, number, operand)
    if kind == "money":
        if not isinstance(value, Mapping):
            return False
        amount = _number(value.get("value"))
        if amount is None:
            return False
        if op == "between":
            low, high = operand
            return (
                value.get("currency") == low.currency == high.currency
                and low.value <= amount <= high.value
            )
        return value.get("currency") == operand.currency and _compare(
            op, amount, operand.value
        )
    if kind == "date":
        if not isinstance(value, str):
            return False
        if op == "between":
            return bool(operand[0] <= value <= operand[1])
        return _compare(op, value, operand)
    if kind == "partialdate":
        if not isinstance(value, str):
            return False
        if op == "between":
            low, high = operand
            return value[: len(low)] >= low and value[: len(high)] <= high
        return _compare(op, value[: len(operand)], operand)
    if kind in _TEXTUAL or kind == "choice":
        if not isinstance(value, str):
            return False
        folded = fold(value)
        match op:
            case "~":
                return fold(operand) in folded
            case "in":
                return folded in {fold(item) for item in operand}
            case "=":
                return folded == fold(operand) if kind != "choice" else value == operand
        if op == "in":
            return value in operand
        return False
    if kind == "boolean":
        return value is operand
    if kind == "multichoice":
        return isinstance(value, list) and all(item in value for item in operand)
    if kind == "checklist":
        if not isinstance(value, list):
            return False
        rows = [row for row in value if isinstance(row, Mapping)]
        open_rows = any(row.get("done") is not True for row in rows)
        return open_rows if op == "incomplete" else bool(rows) and not open_rows
    return False


def _candidates(node: Node, condition: FieldCondition) -> list[object]:
    value = node.attributes.get(condition.key)
    if condition.sub_key is None:
        return [value]
    if not isinstance(value, list):
        return []
    return [row.get(condition.sub_key) for row in value if isinstance(row, Mapping)]


def _field_matches(node: Node, condition: FieldCondition, ctx: ResolvedQuery) -> bool:
    kind = ctx.field_kinds.get((condition.type, condition.key, condition.sub_key))
    if kind is None or node.type != condition.type:
        return False
    if condition.op == "!=":
        return not _field_matches(node, replace(condition, op="="), ctx)
    operand: Any = None
    if condition.value is not None:
        operand = _resolve(condition.value, node, kind, ctx.today)
        if operand is _MISSING:
            return False
    for value in _candidates(node, condition):
        if condition.op == "empty":
            hit = _is_empty(value)
        elif condition.op == "not_empty":
            hit = not _is_empty(value)
        else:
            hit = value is not None and _test(kind, condition.op, value, operand)
        if hit:
            return True
    return False


def _date_matches(node: Node, condition: DateCondition, ctx: ResolvedQuery) -> bool:
    stamp = node.created_at if condition.on == "created" else node.updated_at
    day = stamp.astimezone(UTC).date().isoformat()
    operand = _resolve(condition.value, node, "date", ctx.today)
    if condition.op == "between":
        return bool(operand[0] <= day <= operand[1])
    return _compare(condition.op, day, operand)


def _condition(node: Node, condition: Condition, ctx: ResolvedQuery) -> bool:
    if isinstance(condition, TextCondition):
        return text_matches(node, fold(condition.q), ctx.search_exclusions)
    if isinstance(condition, TypeCondition):
        return node.type in condition.slugs
    if isinstance(condition, FavouriteCondition):
        return node.favourite == condition.value
    if isinstance(condition, TagCondition):
        held = set(node.tags)
        wanted = set(condition.tags)
        return {
            "any": bool(held & wanted),
            "all": wanted <= held,
            "none": not held & wanted,
        }[condition.mode]
    if isinstance(condition, DateCondition):
        return _date_matches(node, condition, ctx)
    return _field_matches(node, condition, ctx)


def matches(node: Node, group: Group, ctx: ResolvedQuery) -> bool:
    """Whether `node` satisfies the filter tree."""
    results = (
        matches(node, child, ctx)
        if isinstance(child, Group)
        else _condition(node, child, ctx)
        for child in group.children
    )
    if group.op == "and":
        return all(results)
    if group.op == "or":
        return any(results)
    return not next(iter(results))


def _field_sort_value(node: Node, key: SortKey, ctx: ResolvedQuery) -> SortValue:
    kind = ctx.field_kinds.get((key.type or "", key.key or "", None))
    if kind is None or node.type != key.type:
        return None
    value = node.attributes.get(key.key or "")
    if kind in _NUMERIC:
        return _number(value)
    if kind == "money":
        return _number(value.get("value")) if isinstance(value, Mapping) else None
    if not isinstance(value, str):
        return None
    return value if kind in {"date", "partialdate"} else sort_key(value)


def sort_values(node: Node, ctx: ResolvedQuery) -> tuple[SortValue, ...]:
    """The value of each sort key for `node` (None sorts last)."""
    values: list[SortValue] = []
    for key in ctx.query.sort:
        if key.by == "name":
            values.append(sort_key(node.name))
        elif key.by == "created":
            values.append(node.created_at.timestamp())
        elif key.by == "updated":
            values.append(node.updated_at.timestamp())
        else:
            values.append(_field_sort_value(node, key, ctx))
    return tuple(values)


def _order(left: SortValue, right: SortValue, *, desc: bool) -> int:
    """Negative when `left` sorts first; None is always last."""
    if left is None and right is None:
        return 0
    if left is None:
        return 1
    if right is None:
        return -1
    result = (left > right) - (left < right)  # type: ignore[operator]
    return -result if desc else result


def is_after(hit: SearchHit, cursor: Cursor, sort: tuple[SortKey, ...]) -> bool:
    """Whether `hit` sorts strictly after the cursor row."""
    for index, key in enumerate(sort):
        order = _order(
            hit.sort_values[index], cursor.sort_values[index], desc=key.dir == "desc"
        )
        if order:
            return order > 0
    return hit.node.id > cursor.id
```

Fix any `ruff` / `mypy` complaints by simplifying (for example split `_test` into per-kind helpers if `C901` fires), not by silencing.

- [ ] **Step 6: Implement the in-memory repository methods**

In `in_memory_node_repository.py`:

```python
def _matching(self, scope: AccessScope, resolved: ResolvedQuery) -> list[SearchHit]:
    where = resolved.query.where
    hits = [
        SearchHit(node=node, sort_values=sort_values(node, resolved))
        for node in sorted(self._visible(scope), key=lambda n: n.id)
        if where is None or matches(node, where, resolved)
    ]
    for index in reversed(range(len(resolved.query.sort))):
        desc = resolved.query.sort[index].dir == "desc"
        present = [h for h in hits if h.sort_values[index] is not None]
        absent = [h for h in hits if h.sort_values[index] is None]
        present.sort(key=lambda h, i=index: h.sort_values[i], reverse=desc)  # type: ignore[arg-type, return-value]
        hits = present + absent
    return hits


async def search(self, *, scope, resolved, after, limit):
    hits = self._matching(scope, resolved)
    if after is not None:
        hits = [h for h in hits if is_after(h, after, resolved.query.sort)]
    return hits[:limit]


async def search_count(self, *, scope, resolved):
    return len(self._matching(scope, resolved))
```

(Write full signatures with annotations matching the port. Python's sort is stable even with `reverse=True`, which is what makes the multi-pass sort correct.)

- [ ] **Step 7: Run to verify pass**

Run: `cd backend && pytest tests/modules/graph -q -m "not integration" && cd .. && poe typecheck-backend && poe lint-backend`
Expected: all PASS, the `postgres` params deselected. Fix the in-memory evaluator, never the scenarios, if a case fails. If you believe a scenario is wrong, stop and raise it.

**Checkpoint:** user may commit. (Integration params stay red until Task 6.)

---

### Task 5: Migration and model indexes

**Files:**
- Create: `backend/src/app/alembic/versions/q8f9a0b1c2d3_query_indexes.py`
- Modify: `adapters/persistence/models.py` (declare the indexes so `test_model_definitions_match_ddl` stays green)

**Interfaces:**
- Produces: SQL function `immutable_unaccent(text) RETURNS text` (used by Task 6); GIN indexes on `nodes.attributes`, `nodes.tags`, and trigram indexes on `immutable_unaccent(name)` and `immutable_unaccent(description)`.

- [ ] **Step 1: Confirm the head revision**

Run: `cd backend && alembic heads` (use the invocation in `pyproject.toml`'s `migrate` task if the bare command needs a config flag). Expected: `p7e8f9a0b1c2`. Use whatever it prints as `down_revision` below.

- [ ] **Step 2: Write the migration**

```python
"""query_indexes

Revision ID: q8f9a0b1c2d3
Revises: p7e8f9a0b1c2
Create Date: 2026-10-14 15:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "q8f9a0b1c2d3"
down_revision: str | None = "p7e8f9a0b1c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    # `unaccent` is only STABLE, so it cannot back an index; this wrapper pins
    # the dictionary and is declared IMMUTABLE.
    op.execute(
        "CREATE OR REPLACE FUNCTION immutable_unaccent(text) RETURNS text "
        "AS $$ SELECT public.unaccent('public.unaccent', $1) $$ "
        "LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT"
    )
    op.execute(
        "CREATE INDEX ix_nodes_attributes_gin ON nodes USING gin (attributes jsonb_path_ops)"
    )
    op.execute(
        "CREATE INDEX ix_nodes_tags_gin ON nodes USING gin (tags jsonb_path_ops)"
    )
    op.execute(
        "CREATE INDEX ix_nodes_name_trgm ON nodes "
        "USING gin (immutable_unaccent(name) gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_nodes_description_trgm ON nodes "
        "USING gin (immutable_unaccent(description) gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_nodes_description_trgm")
    op.execute("DROP INDEX IF EXISTS ix_nodes_name_trgm")
    op.execute("DROP INDEX IF EXISTS ix_nodes_tags_gin")
    op.execute("DROP INDEX IF EXISTS ix_nodes_attributes_gin")
    op.execute("DROP FUNCTION IF EXISTS immutable_unaccent(text)")
    # pg_trgm stays installed, as with `unaccent`: it may be shared.
```

- [ ] **Step 3: Declare the indexes in the model**

In `models.py`, extend `NodeModel.__table_args__` (it currently holds `Index("ix_nodes_owner_id_id", "owner_id", "id")`):

```python
(
    Index(
        "ix_nodes_attributes_gin",
        "attributes",
        postgresql_using="gin",
        postgresql_ops={"attributes": "jsonb_path_ops"},
    ),
)
(
    Index(
        "ix_nodes_tags_gin",
        "tags",
        postgresql_using="gin",
        postgresql_ops={"tags": "jsonb_path_ops"},
    ),
)
(
    Index(
        "ix_nodes_name_trgm",
        text("immutable_unaccent(name)"),
        postgresql_using="gin",
        postgresql_ops={"immutable_unaccent(name)": "gin_trgm_ops"},
    ),
)
(
    Index(
        "ix_nodes_description_trgm",
        text("immutable_unaccent(description)"),
        postgresql_using="gin",
        postgresql_ops={"immutable_unaccent(description)": "gin_trgm_ops"},
    ),
)
```

(`text` is already imported there. Wrap long lines with the formatter.)

- [ ] **Step 4: Run the migration tests**

Run: `cd backend && pytest tests/platform/test_migrations.py -q` (needs Docker/Postgres, as `poe test-backend-integration` does).
Expected: PASS for `test_upgrade`, `test_up_down_consistency`, `test_single_head_revision` and `test_model_definitions_match_ddl`. If the drift test objects to the expression indexes, adjust only the model declaration (alembic ignores expression indexes in comparison in most versions; exclude them from the model if it complains, and say so in a comment).

**Checkpoint:** user may commit.

---

### Task 6: SQL compiler and repository search

> **Rulings that bind this task (made during Task 4; the Python evaluator `query_eval.py` is the reference).**
> - **R4:** wrap every leaf produced by `_condition` in `COALESCE(..., false)` centrally (type IN on a NULL type, NULL description in text search, the field type check). Add a separate small test, own seed, both adapters: `NOT(type in [film])` includes an untyped item and `NOT(text)` includes an item with a NULL description.
> - **R5:** `!=` is **type-scoped**: `field(type=T, key, !=, v)` is true only when `node.type = T` AND NOT(`=`). So `_field` must return `and_(coalesce(type == T, false), not_(coalesce(inner, false)))`, not `not_(<whole eq including the type test>)`. For a table column it is type-scoped NOT(any row equals). A stale key is always false.
> - **R6:** for a table column (`sub_key`), `not_empty` = some row has a non-empty value in that column (not NULL, `""`, `[]`); `empty` = type-scoped NOT(`not_empty`), true for an item with no table, a non-array value, an empty array, or only blank cells. Top-level `empty`/`not_empty` are complements within the type.
> - Task 4 left placeholder `search` / `search_count` stubs raising `NotImplementedError` (`# pragma: no cover`) in `SqlAlchemyNodeRepository`; replace them.
> - The scenario table in `test_node_search.py` (including the un-scoped `!=` and `bom` column scenarios added in Task 4) is the contract: make SQL pass it; do not edit expectations.

**Files:**
- Create: `adapters/persistence/search_sql.py` (text-search helpers moved), `adapters/persistence/query_sql.py`
- Modify: `adapters/persistence/node_repository.py`

**Interfaces:**
- Consumes: Task 4 port and scenarios; Task 5's `immutable_unaccent`.
- Produces: `compile_where(resolved) -> ColumnElement[bool] | None`, `sort_expressions(resolved) -> list[ColumnElement[Any]]`, `after_clause(resolved, exprs, cursor) -> ColumnElement[bool]`; `SqlAlchemyNodeRepository.search` / `search_count`.

- [ ] **Step 1: Run the scenarios to see them fail**

Run: `cd backend && pytest tests/modules/graph/adapters/persistence/test_node_search.py -q -m integration`
Expected: FAIL, `AttributeError: 'SqlAlchemyNodeRepository' object has no attribute 'search'`.

- [ ] **Step 2: Move the text-search SQL helpers**

Move `_LIKE_ESCAPE`, `_like_pattern`, `_unaccent_ilike`, `_has_matching_row`, `_has_matching_value`, `_search_clause` from `node_repository.py` into `search_sql.py`, made public (`LIKE_ESCAPE`, `like_pattern`, `unaccent_ilike`, `has_matching_row`, `has_matching_value`, `search_clause`), importing `NodeModel`. In `unaccent_ilike` switch `func.unaccent` to `func.immutable_unaccent` so name and description matches can use the trigram indexes. `node_repository.py` imports them. Run `grep -rn "_search_clause\|_like_pattern\|_unaccent_ilike\|_has_matching" backend/tests` and update any test that imports the old private names.

Run: `cd backend && pytest tests/modules/graph -q` (including integration). Expected: PASS (behaviour unchanged).

- [ ] **Step 3: Write the compiler**

`adapters/persistence/query_sql.py`:

```python
"""Compile a query tree to SQLAlchemy.

`query_eval.py` is the reference: every scenario in `test_node_search.py`
must give the same answer here. Two rules keep it honest:

* each leaf is wrapped in COALESCE(..., false), so NOT never sees SQL NULL;
* every cast sits inside a CASE on `jsonb_typeof`, so a value of the wrong JSON
  type yields NULL instead of an error.
"""

from typing import Any

from sqlalchemy import (
    Date,
    Float,
    Numeric,
    Text,
    and_,
    case,
    cast,
    column,
    exists,
    false,
    func,
    literal,
    not_,
    or_,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql.elements import ColumnElement

from app.modules.graph.adapters.persistence.models import NodeModel
from app.modules.graph.adapters.persistence.search_sql import (
    like_pattern,
    search_clause,
    unaccent_ilike,
)
from app.modules.graph.domain.query import (
    Condition,
    Cursor,
    DateCondition,
    FavouriteCondition,
    FieldCondition,
    FieldReference,
    Group,
    Money,
    Operand,
    RelativeDate,
    ResolvedQuery,
    SortKey,
    TagCondition,
    TextCondition,
    TypeCondition,
)

_NUMERIC = frozenset({"number", "duration", "rating"})
_TEXTUAL = frozenset({"text", "url", "email", "phone", "longtext"})
_C = "C"  # byte-wise collation: matches Python's code-point string order


def _typed(
    j: ColumnElement[Any], json_type: str, value: ColumnElement[Any]
) -> ColumnElement[Any]:
    return case((func.jsonb_typeof(j) == json_type, value), else_=None)


def _num(j: ColumnElement[Any]) -> ColumnElement[Any]:
    return _typed(j, "number", cast(j.astext, Numeric))  # type: ignore[attr-defined]


def _str(j: ColumnElement[Any]) -> ColumnElement[Any]:
    return _typed(j, "string", j.astext)  # type: ignore[attr-defined]


def _folded(expression: ColumnElement[Any]) -> ColumnElement[Any]:
    return func.lower(func.immutable_unaccent(expression))


def _json_literal(text: str) -> ColumnElement[Any]:
    return cast(literal(text), JSONB)


def _array_or_empty(j: ColumnElement[Any]) -> ColumnElement[Any]:
    return case((func.jsonb_typeof(j) == "array", j), else_=_json_literal("[]"))


def _is_empty(j: ColumnElement[Any]) -> ColumnElement[bool]:
    return or_(
        j.is_(None),
        func.jsonb_typeof(j) == "null",
        j == _json_literal('""'),
        j == _json_literal("[]"),
    )


def _cmp(op: str, left: ColumnElement[Any], right: Any) -> ColumnElement[bool]:  # noqa: ANN401
    return {
        "=": left == right,
        ">": left > right,
        ">=": left >= right,
        "<": left < right,
        "<=": left <= right,
    }[op]


def _operand(operand: Operand, kind: str, ctx: ResolvedQuery) -> Any:  # noqa: ANN401
    """A bind value, or a column expression for a field reference."""
    if isinstance(operand, tuple):
        return [_operand(item, kind, ctx) for item in operand]
    if isinstance(operand, RelativeDate):
        return operand.resolve(ctx.today).isoformat()
    if isinstance(operand, FieldReference):
        other = NodeModel.attributes[operand.key]
        if kind == "money":
            return other
        return _str(other) if kind == "date" else _num(other)
    return operand


def _scalar_predicate(  # noqa: C901, PLR0911, PLR0912
    kind: str,
    op: str,
    j: ColumnElement[Any],
    operand: Any,  # noqa: ANN401
) -> ColumnElement[bool]:
    if kind in _NUMERIC:
        value = _num(j)
        if op == "between":
            return and_(value >= operand[0], value <= operand[1])
        return _cmp(op, value, operand)
    if kind == "money":
        amount = _num(j["value"])  # type: ignore[index]
        currency = _typed(j, "object", j["currency"].astext)  # type: ignore[index]
        if isinstance(operand, list):
            low, high = operand
            return and_(
                currency == low.currency,
                currency == high.currency,
                amount >= low.value,
                amount <= high.value,
            )
        if isinstance(operand, Money):
            return and_(currency == operand.currency, _cmp(op, amount, operand.value))
        other = _num(operand["value"])
        return and_(
            currency == _typed(operand, "object", operand["currency"].astext),
            _cmp(op, amount, other),
        )
    if kind == "date":
        value = _str(j).collate(_C)
        if op == "between":
            return and_(value >= operand[0], value <= operand[1])
        return _cmp(op, value, operand)
    if kind == "partialdate":
        text_ = _str(j)
        if op == "between":
            low, high = operand
            return and_(
                func.left(text_, len(low)).collate(_C) >= low,
                func.left(text_, len(high)).collate(_C) <= high,
            )
        return _cmp(op, func.left(text_, len(operand)).collate(_C), operand)
    if kind in _TEXTUAL:
        text_ = _str(j)
        if op == "~":
            return unaccent_ilike(text_, like_pattern(operand))
        if op == "in":
            return or_(*(_folded(text_) == _folded(literal(item)) for item in operand))
        return _folded(text_) == _folded(literal(operand))
    if kind == "choice":
        if op == "in":
            return _str(j).in_(operand)
        return _str(j) == operand
    if kind == "boolean":
        return j.contains(operand)  # type: ignore[attr-defined]
    if kind == "multichoice":
        return j.contains(list(operand))  # type: ignore[attr-defined]
    raise AssertionError(kind)


def _checklist_predicate(op: str, j: ColumnElement[Any]) -> ColumnElement[bool]:
    rows = func.jsonb_array_elements(_array_or_empty(j)).table_valued(
        column("value", JSONB), name="step"
    )
    open_row = exists(
        select(literal(1))
        .select_from(rows)
        .where(not_(rows.c.value.contains({"done": True})))
    )
    any_row = exists(select(literal(1)).select_from(rows))
    return open_row if op == "incomplete" else and_(any_row, not_(open_row))


def _field(condition: FieldCondition, ctx: ResolvedQuery) -> ColumnElement[bool]:
    kind = ctx.field_kinds.get((condition.type, condition.key, condition.sub_key))
    if kind is None:
        return false()
    if condition.op == "!=":
        return not_(_field_eq(condition, kind, ctx))
    return _field_eq(condition, kind, ctx)


def _field_eq(  # noqa: C901
    condition: FieldCondition, kind: str, ctx: ResolvedQuery
) -> ColumnElement[bool]:
    op = "=" if condition.op == "!=" else condition.op
    operand = None if condition.value is None else _operand(condition.value, kind, ctx)
    top = NodeModel.attributes[condition.key]

    def predicate(j: ColumnElement[Any]) -> ColumnElement[bool]:
        if op == "empty":
            return _is_empty(j)
        if op == "not_empty":
            return not_(_is_empty(j))
        if op in {"incomplete", "complete"}:
            return _checklist_predicate(op, j)
        return _scalar_predicate(kind, op, j, operand)

    if condition.sub_key is None:
        inner: ColumnElement[bool] = predicate(top)
        # Equality-shaped tests use containment so the GIN index can serve them.
        if (
            kind in {"choice", "boolean"}
            and op == "="
            and not isinstance(operand, ColumnElement)
        ):
            inner = NodeModel.attributes.contains({condition.key: operand})
        elif kind == "multichoice" and op == "has":
            inner = NodeModel.attributes.contains({condition.key: list(operand)})
    else:
        rows = func.jsonb_array_elements(_array_or_empty(top)).table_valued(
            column("value", JSONB), name="row"
        )
        inner = exists(
            select(literal(1))
            .select_from(rows)
            .where(predicate(rows.c.value[condition.sub_key]))  # type: ignore[index]
        )
    return and_(NodeModel.type == condition.type, func.coalesce(inner, false()))


def _date(condition: DateCondition, ctx: ResolvedQuery) -> ColumnElement[bool]:
    stamp = NodeModel.created_at if condition.on == "created" else NodeModel.updated_at
    day = cast(func.timezone("UTC", stamp), Date)
    operand = _operand(condition.value, "date", ctx)
    if condition.op == "between":
        return and_(day >= cast(operand[0], Date), day <= cast(operand[1], Date))
    return _cmp(condition.op, day, cast(operand, Date))


def _tag(condition: TagCondition) -> ColumnElement[bool]:
    tags = NodeModel.tags
    if condition.mode == "all":
        return tags.contains(list(condition.tags))
    any_of = or_(*(tags.contains([tag]) for tag in condition.tags))
    return any_of if condition.mode == "any" else not_(any_of)


def _condition(condition: Condition, ctx: ResolvedQuery) -> ColumnElement[bool]:
    if isinstance(condition, TextCondition):
        return search_clause(condition.q, ctx.search_exclusions)
    if isinstance(condition, TypeCondition):
        return NodeModel.type.in_(condition.slugs)
    if isinstance(condition, FavouriteCondition):
        return NodeModel.favourite == condition.value
    if isinstance(condition, TagCondition):
        return _tag(condition)
    if isinstance(condition, DateCondition):
        return _date(condition, ctx)
    return _field(condition, ctx)


def _group(group: Group, ctx: ResolvedQuery) -> ColumnElement[bool]:
    parts = [
        _group(child, ctx) if isinstance(child, Group) else _condition(child, ctx)
        for child in group.children
    ]
    if group.op == "and":
        return and_(*parts)
    if group.op == "or":
        return or_(*parts)
    return not_(parts[0])


def compile_where(ctx: ResolvedQuery) -> ColumnElement[bool] | None:
    """The filter as one boolean expression, or None for "everything"."""
    where = ctx.query.where
    return None if where is None else _group(where, ctx)


def _sort_expression(key: SortKey, ctx: ResolvedQuery) -> ColumnElement[Any]:
    if key.by == "name":
        return _folded(NodeModel.name).collate(_C)
    if key.by in {"created", "updated"}:
        stamp = NodeModel.created_at if key.by == "created" else NodeModel.updated_at
        return cast(func.extract("epoch", stamp), Float)
    kind = ctx.field_kinds.get((key.type or "", key.key or "", None))
    if kind is None:
        return literal(None, type_=Text)
    j = NodeModel.attributes[key.key]
    if kind in _NUMERIC:
        value: ColumnElement[Any] = cast(_num(j), Float)
    elif kind == "money":
        value = cast(_num(j["value"]), Float)  # type: ignore[index]
    elif kind in {"date", "partialdate"}:
        value = _str(j).collate(_C)
    else:
        value = _folded(_str(j)).collate(_C)
    return case((NodeModel.type == key.type, value), else_=None)


def sort_expressions(ctx: ResolvedQuery) -> list[ColumnElement[Any]]:
    """One expression per sort key, in order."""
    return [_sort_expression(key, ctx) for key in ctx.query.sort]


def order_by(ctx: ResolvedQuery, exprs: list[ColumnElement[Any]]) -> list[Any]:
    """ORDER BY terms: each key with nulls last, then id."""
    terms = [
        (expr.desc() if key.dir == "desc" else expr.asc()).nulls_last()
        for expr, key in zip(exprs, ctx.query.sort, strict=True)
    ]
    return [*terms, NodeModel.id]


def after_clause(
    ctx: ResolvedQuery, exprs: list[ColumnElement[Any]], cursor: Cursor
) -> ColumnElement[bool]:
    """Rows strictly after `cursor` in the order `order_by` produces."""
    branches: list[ColumnElement[bool]] = []
    equal: list[ColumnElement[bool]] = []
    for expr, key, value in zip(exprs, ctx.query.sort, cursor.sort_values, strict=True):
        if value is None:
            later: ColumnElement[bool] = false()
            same = expr.is_(None)
        else:
            beyond = expr < value if key.dir == "desc" else expr > value
            later = or_(beyond, expr.is_(None))
            same = expr == value
        branches.append(and_(*equal, later))
        equal.append(same)
    branches.append(and_(*equal, NodeModel.id > cursor.id))
    return or_(*branches)
```

- [ ] **Step 4: Add the repository methods**

In `node_repository.py`:

```python
async def search(
    self,
    *,
    scope: AccessScope,
    resolved: ResolvedQuery,
    after: Cursor | None,
    limit: int,
) -> builtins.list[SearchHit]:
    """Return one page of nodes matching the query, in its order."""
    logger.debug("searching nodes", limit=limit)
    exprs = sort_expressions(resolved)
    stmt = select(NodeModel, *exprs).where(_in_scope(scope))
    where = compile_where(resolved)
    if where is not None:
        stmt = stmt.where(where)
    if after is not None:
        stmt = stmt.where(after_clause(resolved, exprs, after))
    stmt = stmt.order_by(*order_by(resolved, exprs)).limit(limit)
    rows = (await self._session.execute(stmt)).all()
    return [
        SearchHit(node=_to_domain(row[0]), sort_values=tuple(row[1:])) for row in rows
    ]


async def search_count(self, *, scope: AccessScope, resolved: ResolvedQuery) -> int:
    """Return how many live nodes in `scope` match the query."""
    stmt = select(func.count()).select_from(NodeModel).where(_in_scope(scope))
    where = compile_where(resolved)
    if where is not None:
        stmt = stmt.where(where)
    return (await self._session.execute(stmt)).scalar_one()
```

`scope` and the compiled `where` are separate `.where()` calls, so SQLAlchemy ANDs them as two parenthesised terms; an `OR` group stays inside its own parentheses.

- [ ] **Step 5: Run the scenarios**

Run: `cd backend && pytest tests/modules/graph/adapters/persistence/test_node_search.py -q`
Expected: every scenario PASSES for both adapters. When SQL disagrees with Python, treat the in-memory evaluator as the reference unless the scenario itself is wrong; fix the compiler. Watch for these likely culprits:
- the partial-date cases (collation, Review Focus 2),
- `NOT` cases (a leaf escaped the `coalesce`),
- the `Bad data` item (a `CASE` guard is missing).

- [ ] **Step 6: Check the plan uses the indexes**

Run an `EXPLAIN` in a throwaway test or psql against a database with a few thousand generated nodes for: `tag any`, `genres has scifi`, `director = x`, and `name ~ "ali"`. Expected: `Bitmap Index Scan` on the GIN indexes for the containment and trigram forms. Number comparisons will not use an index; that is expected (see DECISIONS in Task 12). Record the finding in the Task 12 DECISIONS entry. Do not add code for this step.

- [ ] **Step 7: Full backend check**

Run: `poe lint-backend && poe typecheck-backend && poe test-backend && poe test-backend-integration`
Expected: PASS.

**Checkpoint:** user may commit.

---

### Task 7: Cursor codec and type catalogue

**Files:**
- Create: `application/query_cursor.py`, `application/type_catalogue.py`
- Modify: `application/list_nodes.py` (use `load_node_types` in `_search_exclusions`)
- Create: `backend/tests/modules/graph/application/test_query_cursor.py`

**Interfaces:**
- Produces: `encode_cursor(cursor: Cursor) -> str`, `decode_cursor(token: str, *, sort_count: int) -> Cursor`, `async load_node_types(repos: GraphRepos) -> list[NodeType]`.

- [ ] **Step 1: Write the failing tests**

```python
import uuid

import pytest

from app.modules.graph.application.query_cursor import decode_cursor, encode_cursor
from app.modules.graph.domain.query import Cursor, InvalidQueryError


def test_round_trip() -> None:
    cursor = Cursor(sort_values=("alien", 4.5, None), id=uuid.uuid7())
    assert decode_cursor(encode_cursor(cursor), sort_count=3) == cursor


@pytest.mark.parametrize("token", ["", "!!!", "e30", "eyJzIjpbMV19"])
def test_rejects_garbage(token: str) -> None:
    with pytest.raises(InvalidQueryError, match="cursor"):
        decode_cursor(token, sort_count=1)


def test_rejects_a_cursor_from_a_different_sort() -> None:
    token = encode_cursor(Cursor(sort_values=("a",), id=uuid.uuid7()))
    with pytest.raises(InvalidQueryError, match="cursor"):
        decode_cursor(token, sort_count=2)
```

- [ ] **Step 2: Run, expect failure** (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

`query_cursor.py`:

```python
"""The opaque paging cursor: the last row's sort values and id, as base64url JSON."""

import base64
import binascii
import json
import uuid

from app.modules.graph.domain.query import Cursor, InvalidQueryError

_BAD = "Not a valid cursor."


def encode_cursor(cursor: Cursor) -> str:
    """Encode `cursor` as an unpadded base64url string."""
    raw = json.dumps(
        {"s": list(cursor.sort_values), "i": str(cursor.id)}, separators=(",", ":")
    )
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(token: str, *, sort_count: int) -> Cursor:
    """Decode a cursor made for a query with `sort_count` sort keys.

    Raises:
        InvalidQueryError: If the token is malformed or belongs to another sort.
    """
    try:
        data = json.loads(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)))
        values = data["s"]
        if not isinstance(values, list) or len(values) != sort_count:
            raise InvalidQueryError(_BAD, path="cursor")
        if any(not (v is None or isinstance(v, str | int | float)) for v in values):
            raise InvalidQueryError(_BAD, path="cursor")
        return Cursor(sort_values=tuple(values), id=uuid.UUID(data["i"]))
    except (binascii.Error, ValueError, KeyError, TypeError) as error:
        raise InvalidQueryError(_BAD, path="cursor") from error
```

`type_catalogue.py` (the paged loop currently inside `ListNodes._search_exclusions`):

```python
from app.modules.graph.domain.node_type import NodeType
from app.modules.graph.ports.unit_of_work import GraphRepos

_PAGE = 100


async def load_node_types(repos: GraphRepos) -> list[NodeType]:
    """Read every item type, a page at a time."""
    types: list[NodeType] = []
    after = None
    while True:
        page = await repos.node_types.list(after=after, limit=_PAGE)
        types.extend(page)
        if len(page) < _PAGE:
            return types
        after = page[-1].id
```

Then rewrite `ListNodes._search_exclusions` to loop over `await load_node_types(self._repos)` (same result), delete `_TYPE_PAGE_SIZE`.

- [ ] **Step 4: Run** `cd backend && pytest tests/modules/graph/application -q && poe typecheck-backend` and expect PASS (the existing list tests prove the refactor).

**Checkpoint:** user may commit.

---

### Task 8: `SearchNodes` use case

> **Ruling R7 (from the Task 4 review):** `decode_cursor` (Task 7) only checks that each sort value is `None`, a string or a number. `SearchNodes` must also check each cursor value's type against its sort key before querying: `name` is a string; `created` / `updated` are numbers; a field key is a number for number, duration, rating and money kinds and a string for the rest; `None` is always allowed. A mismatch is `InvalidQueryError(path="cursor")`, never a `TypeError` in the evaluator or a database error. Add a test for each mismatch direction.

**Files:**
- Create: `application/search_nodes.py`, `backend/tests/modules/graph/application/test_search_nodes.py`

**Interfaces:**
- Consumes: Tasks 2, 3, 4, 7.
- Produces:

```python
@dataclass(kw_only=True)
class SearchNodesQuery:
    query: Mapping[str, Any]
    limit: int = 50
    cursor: str | None = None


@dataclass(frozen=True)
class SearchNodesResult:
    items: list[Node]
    total: int
    next_cursor: str | None
    warnings: list[QueryWarning]


class SearchNodes(ScopedQueryHandler[GraphRepos, SearchNodesQuery, SearchNodesResult]):
    def __init__(
        self,
        repos: GraphRepos,
        policy: AccessPolicy,
        today: Callable[[], date] | None = None,
    ) -> None: ...
```

- [ ] **Step 1: Write the failing tests**

```python
import uuid
from datetime import date
from typing import Any

import pytest

from app.entrypoints.api.shared.access_policy import OwnerAccessPolicy
from app.modules.graph.adapters.persistence.in_memory_edge_repository import (
    InMemoryEdgeRepository,
)
from app.modules.graph.adapters.persistence.in_memory_edge_type_repository import (
    InMemoryEdgeTypeRepository,
)
from app.modules.graph.adapters.persistence.in_memory_node_repository import (
    InMemoryNodeRepository,
)
from app.modules.graph.adapters.persistence.in_memory_node_type_repository import (
    InMemoryNodeTypeRepository,
)
from app.modules.graph.application.search_nodes import SearchNodes, SearchNodesQuery
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.node_type import NodeType
from app.modules.graph.domain.query import InvalidQueryError
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.actor import SYSTEM_ACTOR, Actor

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"rating": {"type": "number", "x-menagerist": {"kind": "rating"}}},
}


async def _setup(count: int = 5) -> SearchNodes:
    repos = GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )
    await repos.node_types.add(
        NodeType.create(slug="film", label="Film", attributes_schema=SCHEMA)
    )
    for index in range(count):
        await repos.nodes.add(
            Node.create(
                owner_id=uuid.UUID(int=1),
                name=f"Film {index}",
                type="film",
                attributes={"rating": index % 3},
            )
        )
    return SearchNodes(repos, OwnerAccessPolicy(), today=lambda: date(2026, 10, 14))


def _body(*children: dict[str, Any], **extra: Any) -> dict[str, Any]:  # noqa: ANN401
    where = {"op": "and", "children": list(children)} if children else None
    return {"v": 1, "where": where, **extra}


def _rating(op: str, value: int) -> dict[str, Any]:
    return {"kind": "field", "type": "film", "key": "rating", "op": op, "value": value}


async def test_returns_matches_and_total() -> None:
    use_case = await _setup()
    result = await use_case.handle(
        SearchNodesQuery(query=_body(_rating(">=", 1))), SYSTEM_ACTOR
    )
    assert [n.name for n in result.items] == ["Film 1", "Film 2", "Film 4"]
    assert result.total == 3
    assert result.next_cursor is None
    assert result.warnings == []


async def test_pages_with_a_cursor() -> None:
    use_case = await _setup()
    body = _body(sort=[{"by": "name"}])
    first = await use_case.handle(SearchNodesQuery(query=body, limit=2), SYSTEM_ACTOR)
    assert [n.name for n in first.items] == ["Film 0", "Film 1"]
    assert first.total == 5
    assert first.next_cursor is not None
    second = await use_case.handle(
        SearchNodesQuery(query=body, limit=2, cursor=first.next_cursor), SYSTEM_ACTOR
    )
    assert [n.name for n in second.items] == ["Film 2", "Film 3"]
    last = await use_case.handle(
        SearchNodesQuery(query=body, limit=2, cursor=second.next_cursor), SYSTEM_ACTOR
    )
    assert [n.name for n in last.items] == ["Film 4"]
    assert last.next_cursor is None


async def test_stale_fields_are_reported() -> None:
    use_case = await _setup()
    stale = {"kind": "field", "type": "film", "key": "gone", "op": "=", "value": "x"}
    result = await use_case.handle(SearchNodesQuery(query=_body(stale)), SYSTEM_ACTOR)
    assert result.items == []
    assert [w.path for w in result.warnings] == ["where.children[0]"]


async def test_invalid_queries_are_rejected() -> None:
    use_case = await _setup()
    with pytest.raises(InvalidQueryError):
        await use_case.handle(SearchNodesQuery(query={"v": 9}), SYSTEM_ACTOR)
    with pytest.raises(InvalidQueryError, match="limit"):
        await use_case.handle(SearchNodesQuery(query=_body(), limit=0), SYSTEM_ACTOR)
    with pytest.raises(InvalidQueryError, match="cursor"):
        await use_case.handle(
            SearchNodesQuery(query=_body(), cursor="nope"), SYSTEM_ACTOR
        )


async def test_other_users_items_are_invisible() -> None:
    use_case = await _setup(count=0)
    alice = Actor(id=uuid.UUID(int=11), roles=frozenset({"member"}))
    bob = Actor(id=uuid.UUID(int=12), roles=frozenset({"member"}))
    for actor, name in ((alice, "Alice's film"), (bob, "Bob's film")):
        await use_case._repos.nodes.add(  # noqa: SLF001
            Node.create(owner_id=actor.id, name=name, type="film")
        )
    for actor, expected in ((alice, "Alice's film"), (bob, "Bob's film")):
        result = await use_case.handle(SearchNodesQuery(query=_body()), actor)
        assert [n.name for n in result.items] == [expected]
```

- [ ] **Step 2: Run, expect failure** (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

```python
"""Search items with a saved-able condition tree."""

import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import structlog

from app.modules.graph.application.query_cursor import decode_cursor, encode_cursor
from app.modules.graph.application.query_resolution import resolve_fields
from app.modules.graph.application.schema_meta import search_excluded_keys
from app.modules.graph.application.type_catalogue import load_node_types
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.query import (
    Cursor,
    InvalidQueryError,
    QueryWarning,
    ResolvedQuery,
    parse_query,
)
from app.modules.graph.ports.unit_of_work import GraphRepos

# Needed at runtime: the CQRS signature test evaluates __init__ annotations.
from app.shared_kernel.access_policy import AccessPolicy  # noqa: TC001
from app.shared_kernel.actor import Actor  # noqa: TC001
from app.shared_kernel.cqrs import ScopedQueryHandler

logger = structlog.get_logger()

MAX_LIMIT = 200


def _utc_today() -> date:
    return datetime.now(UTC).date()


@dataclass(kw_only=True)
class SearchNodesQuery:
    """A condition tree (as JSON), a page size and an optional cursor."""

    query: Mapping[str, Any]
    limit: int = 50
    cursor: str | None = None


@dataclass(frozen=True)
class SearchNodesResult:
    """One page of matches, the total, where to resume, and stale conditions."""

    items: list[Node]
    total: int
    next_cursor: str | None
    warnings: list[QueryWarning]


class SearchNodes(ScopedQueryHandler[GraphRepos, SearchNodesQuery, SearchNodesResult]):
    """Search items by condition tree, ordered and paged by keyset."""

    def __init__(
        self,
        repos: GraphRepos,
        policy: AccessPolicy,
        today: Callable[[], date] = _utc_today,
    ) -> None:
        super().__init__(repos, policy)
        self._today = today

    async def handle(self, query: SearchNodesQuery, actor: Actor) -> SearchNodesResult:
        """Return a page of matching items.

        Raises:
            InvalidQueryError: For a malformed query, limit or cursor, or an
                operator or value that does not fit a field.
        """
        if not 1 <= query.limit <= MAX_LIMIT:
            raise InvalidQueryError(
                f"The limit must be 1 to {MAX_LIMIT}.", path="limit"
            )
        parsed = parse_query(query.query)
        node_types = await load_node_types(self._repos)
        schemas = {str(t.slug): t.attributes_schema or {} for t in node_types}
        resolution = resolve_fields(parsed, schemas)
        resolved = ResolvedQuery(
            query=parsed,
            field_kinds=resolution.kinds,
            search_exclusions={
                slug: keys
                for slug, schema in schemas.items()
                if (keys := search_excluded_keys(schema))
            },
            today=self._today(),
        )
        after: Cursor | None = None
        if query.cursor is not None:
            after = decode_cursor(query.cursor, sort_count=len(parsed.sort))
        scope = self._policy.scope_for(actor)
        hits = await self._repos.nodes.search(
            scope=scope, resolved=resolved, after=after, limit=query.limit + 1
        )
        total = await self._repos.nodes.search_count(scope=scope, resolved=resolved)
        page = hits[: query.limit]
        next_cursor = None
        if len(hits) > query.limit:
            last = page[-1]
            next_cursor = encode_cursor(
                Cursor(sort_values=last.sort_values, id=last.node.id)
            )
        logger.debug("nodes searched", count=len(page), total=total)
        return SearchNodesResult(
            items=[hit.node for hit in page],
            total=total,
            next_cursor=next_cursor,
            warnings=resolution.warnings,
        )
```

Remove the unused `uuid` import. If `ScopedQueryHandler` passes `self._repos` under another name, follow `ListNodes`.

- [ ] **Step 4: Run** `cd backend && pytest tests/modules/graph/application -q && poe typecheck-backend && poe lint-backend` and expect PASS. Add the CQRS signature coverage if `tests/shared_kernel/test_cqrs.py` or an architecture test enumerates handlers.

**Checkpoint:** user may commit.

---

### Task 9: `POST /node/search` and the regenerated client

**Files:**
- Modify: `adapters/api/node/schemas.py`, `adapters/api/node/router.py`, `adapters/api/dependencies.py`
- Create: `backend/tests/modules/graph/adapters/api/test_node_search_router.py`
- Regenerate: `frontend/src/lib/api/generated/` (via the poe task; never by hand)

**Interfaces:**
- Consumes: `SearchNodes`, `SearchNodesQuery` (Task 8).
- Produces: `POST /node/search` with `operation_id="search_nodes"`; body `NodeSearchRequest{query: dict[str, Any], limit: int = 50 (1..200), cursor: str | None}`; response `NodeSearchResponse{items: list[NodeResponse], total: int, next_cursor: str | None, warnings: list[QueryWarningResponse{path, message}]}`.

- [ ] **Step 1: Write the failing router tests**

Follow `test_node_router.py` (`_app_with_in_memory_graph()`, `TestClient`) and `test_node_router_two_users.py` for the two-user pattern. Cover: 200 with a matching filter and `total`; paging through `next_cursor`; a stale field returns 200 with `warnings`; a malformed tree returns 400 whose body names the path (`where.children[0]`); `limit=0` returns 422; and a second user's items never appear, including through an `or` group (Review Focus 4).

```python
def test_search_returns_matches_total_and_warnings() -> None:
    client, repos = _client_with_films()  # helper built like the existing router tests
    body = {
        "query": {
            "v": 1,
            "where": {
                "op": "and",
                "children": [
                    {
                        "kind": "field",
                        "type": "film",
                        "key": "rating",
                        "op": ">=",
                        "value": 4,
                    }
                ],
            },
        },
        "limit": 10,
    }
    response = client.post("/api/node/search", json=body)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == len(data["items"])
    assert data["warnings"] == []
    assert data["next_cursor"] is None


def test_malformed_tree_is_a_400_naming_the_path() -> None:
    client, _ = _client_with_films()
    bad = {"query": {"v": 1, "where": {"op": "and", "children": [{"kind": "nope"}]}}}
    response = client.post("/api/node/search", json=bad)
    assert response.status_code == 400
    assert "where.children[0]" in response.json()["detail"]
```

(Check the existing router tests for the real URL prefix and helper names, and write `_client_with_films` the same way they seed data.)

- [ ] **Step 2: Run, expect failure** (404 for the route).

- [ ] **Step 3: Implement schemas, dependency and route**

In `schemas.py`, define `NodeSearchRequest`, `QueryWarningResponse` and `NodeSearchResponse` in the style of `NodeResponse` and the other request models (use the repo's `request_model` base so unknown fields are rejected; read `app/platform/request_model.py`). `NodeSearchResponse.from_result(result: SearchNodesResult)` builds the response with `NodeResponse.from_domain`.

In `dependencies.py` add, next to `get_list_nodes_use_case`:

```python
def get_search_nodes_use_case(
    repos: Annotated[GraphRepos, Depends(get_graph_repos)],
    policy: Annotated[AccessPolicy, Depends(get_access_policy)],
) -> SearchNodes:
    return SearchNodes(repos, policy)
```

In `router.py`, declare it **before** any `/{node_id}` route so the literal path wins:

```python
@router.post(
    "/search",
    response_model=NodeSearchResponse,
    operation_id="search_nodes",
    responses=error_response(
        InvalidQueryError,
        detail="where.children[0]: Unknown condition kind.",
    ),
)
async def search_nodes(
    body: NodeSearchRequest,
    use_case: Annotated[SearchNodes, Depends(get_search_nodes_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> NodeSearchResponse:
    """Search items with a condition tree (see the query model in the docs)."""
    result = await use_case.handle(
        SearchNodesQuery(query=body.query, limit=body.limit, cursor=body.cursor),
        actor,
    )
    return NodeSearchResponse.from_result(result)
```

(No `try/except`: `InvalidQueryError` is a `ValidationError`, which the global handler maps to 400 per the repo's rules. Confirm with the test.)

- [ ] **Step 4: Run, expect pass**

Run: `cd backend && pytest tests/modules/graph/adapters/api tests/architecture tests/entrypoints -q`
Expected: PASS, including the architecture tests and `test_cross_user_isolation.py`. If that isolation test enumerates endpoints, add `/node/search` to it.

- [ ] **Step 5: Regenerate the client**

Run: `poe generate-frontend-client`
Expected: `searchNodes` and its types appear under `frontend/src/lib/api/generated/`. Export them through `frontend/src/lib/api/client.ts` the way `listNodes` is.

- [ ] **Step 6: Full backend gate**

Run: `poe lint-backend && poe typecheck-backend && poe test-backend`
Expected: PASS.

**Checkpoint:** user may commit.

---

### Task 9b: Search performance: capped totals and sort indexes (name, created, updated)

Added after benchmarking Tasks 1-9 on a throwaway Postgres (100,000 items, page of 51, median of 7 warm runs; the script is `/home/sam/.claude/jobs/706d1499/tmp/bench_search.py`, run with `cd backend && uv run python <script> 10000 100000`, it starts its own container and never touches the dev stack). Baseline ("before") figures at 100,000 items: page 10-25 ms for every field filter; **sort by name 2,190 ms, deep page sorted by name 2,250 ms**; sort by rating desc 450 ms; **total count 60-500 ms for field filters, 13,949 ms for free text**; free-text page 824 ms.

**Files:**
- Modify: `backend/src/app/modules/graph/ports/node_repository.py`, `adapters/persistence/node_repository.py`, `adapters/persistence/in_memory_node_repository.py` (`search_count` gains `limit`)
- Modify: `backend/src/app/modules/graph/adapters/persistence/query_sql.py` (`order_by`: no `NULLS LAST` on keys that cannot be NULL)
- Modify: `backend/src/app/modules/graph/application/search_nodes.py` (`TOTAL_CAP`, `total_capped`)
- Modify: `backend/src/app/modules/graph/adapters/api/node/schemas.py` (`total_capped`, examples), regenerate the frontend client
- Create: `backend/src/app/alembic/versions/r9a0b1c2d3e4_sort_indexes.py` (confirm the head with `alembic heads`; it should be `q8f9a0b1c2d3`)
- Modify: `backend/src/app/modules/graph/adapters/persistence/models.py` (declare the index)
- Tests: `test_node_search.py`, `test_search_nodes.py`, `test_node_search_router.py`, `backend/tests/platform/test_query_indexes_migration.py` (or a sibling)

**Interfaces:**
- Consumes: Tasks 4, 6, 8, 9.
- Produces:
  - Port: `async def search_count(self, *, scope: AccessScope, resolved: ResolvedQuery, limit: int | None = None) -> int`. With `limit`, the result is the number of matches but never more than `limit`, and the database stops counting once it has found that many.
  - `search_nodes.py`: module constant `TOTAL_CAP = 1000`; `SearchNodes.__init__(self, repos, policy, today=..., total_cap: int = TOTAL_CAP)`; `SearchNodesResult` gains `total_capped: bool`. `total` is the exact count up to the cap; when more than `total_cap` items match, `total == total_cap` and `total_capped` is True ("1,000+").
  - API: `NodeSearchResponse.total_capped: bool` with a description saying `total` is a lower bound when True.

**Part A: capped total**
- [ ] **Step 1: Tests first (RED).**
  - Repository scenarios in `test_node_search.py` (both adapters): `search_count(..., limit=3)` over a query with 5 matches returns 3; over a query with exactly 3 matches returns 3; with 2 matches returns 2; `limit=None` is unchanged. Reuse the file's seed (for example the "rating at least 4" scenario has 3 matches and "created within the last day" has 7).
  - `test_search_nodes.py`: with `total_cap=3` and 5 matching items, `total == 3` and `total_capped` is True while the page still returns up to `limit` items; with exactly 3 matches `total_capped` is False; with 2 matches `total == 2`, not capped; default cap is 1000.
  - `test_node_search_router.py`: the response has `total_capped` (False for the small seeds).
- [ ] **Step 2: Implement.** SQL: count over a limited subquery, for example `select(func.count()).select_from(select(NodeModel.id).where(scope, filter).limit(limit).subquery())`; keep the unlimited path as it is. In-memory: `min(len(matches), limit)`. In the use case ask for `TOTAL_CAP + 1` (that is, `total_cap + 1`), then `total_capped = counted > total_cap` and `total = min(counted, total_cap)`. Update the port docstring, the response model, its OpenAPI examples (the schema test requires examples) and regenerate the client with `uv run poe generate-frontend-client`.

**Part B: name-sort index**
- [ ] **Step 3: Migration.** New revision with `down_revision` = the confirmed head:

```python
def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX ix_nodes_owner_name_sort ON nodes
        (owner_id, (lower(immutable_unaccent(name)) COLLATE "C"), id)
        WHERE deleted_at IS NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_nodes_owner_name_sort")
```

  Declare it on `NodeModel.__table_args__` the way the other expression indexes are declared (`text(...)`, `postgresql_where=text("deleted_at IS NULL")`), and keep `test_model_definitions_match_ddl` green (adjust only the model declaration if it objects, with a short comment).
- [ ] **Step 3b: Created and updated.** (User request, added after the first benchmark.) The same migration also creates `ix_nodes_owner_created_sort` and `ix_nodes_owner_updated_sort`: partial indexes on `(owner_id, (CAST(EXTRACT(epoch FROM <column>) AS DOUBLE PRECISION)), id) WHERE deleted_at IS NULL`, matching exactly what `_sort_expression` renders for those keys, declared on `NodeModel` and dropped in `downgrade`. Baseline: sorting by created or updated takes about 69 ms at 10,000 items.
- [ ] **Step 4: Make the planner able to use it.** The index orders by `lower(immutable_unaccent(name)) COLLATE "C"` then `id`, nulls last (name cannot be NULL). In `query_sql.order_by`, do not add `NULLS LAST` for the sort keys `name`, `created` and `updated` (they cannot be NULL), so an ascending key matches the index order and a descending key can use a backward scan. Keep `NULLS LAST` for field keys. `after_clause` already treats those values as non-NULL; confirm the paging scenarios still pass unchanged.
- [ ] **Step 5: Verify with EXPLAIN, not assumption.** Add an integration test (marked `integration`, same fixtures as `test_query_indexes_migration.py`) that inserts 20,000 nodes for one owner with `generate_series`, runs `ANALYZE nodes`, then asserts via `EXPLAIN` on the statement `SqlAlchemyNodeRepository.search` builds for `sort: [{"by":"name"}]` (ascending, descending, and with a mid-list cursor) that the plan mentions `ix_nodes_owner_name_sort` and contains no separate `Sort` node. If the planner will not use the index for the descending case, report it and propose the smallest change; do not weaken the assertion.
- [ ] **Step 6: Re-run the benchmark and record before/after.** Run the script at the top of this task for 10,000 and 100,000 items. Put the new numbers beside the baseline figures in the report. Expected: name sort and the mid-list name page drop from seconds to tens of milliseconds, and counts for broad filters are bounded by the cap (note that the benchmark script calls `search_count` without a limit, so also time `search_count(..., limit=1001)` for the broad queries by editing a copy of the script in the session temp directory, not the repo). Also report timings for sorting by `created` and `updated` (no index is required for them; report only).
- [ ] **Step 7: Limits to record, not fix.** The capped count helps broad filters but not selective ones, because a count that finds fewer matches than the cap still has to visit every row: a free-text query matching about 1,000 of 100,000 items still takes seconds. Sorting on a field (for example rating) is not indexable in general. Both go into the Task 12 DECISIONS entry as known limits with the numbers.
- [ ] **Step 8: Gates.** New and changed tests; `cd backend && uv run pytest tests/platform -q -m integration`; `uv run pytest tests/modules/graph -q -m integration`; architecture and CQRS tests; the full unit suite `uv run poe test-backend`; `uv run poe lint-backend`; `uv run poe typecheck-backend`; `uv run poe lint-frontend`, `typecheck-frontend`, `test-frontend` (the generated client changed).

### Task 9c: Faster free text: a trigram prefilter on the stored attributes

User-requested follow-up to the Task 9b benchmark. Baseline at 100,000 items (page of 51 / exact count): free text "alien" **824 ms / 13,949 ms**; "director 42" + type film **433 ms / 10,472 ms**; at 10,000 items 760 ms / 2,325 ms. Cause: the text condition walks every nested value of every item's `attributes` (`jsonb_path_query`) and runs the accent-stripping function on each, so nothing can use an index.

**Idea (semantics unchanged):** keep the exact check, but put a cheap, index-assisted *superset* test in front of it: `immutable_unaccent(attributes::text) ILIKE '%q%'`, backed by a trigram GIN index on that expression. Rows that fail the prefilter cannot contain the text in any value, so only a handful of candidates reach the exact walk, which still applies per-type exclusions (ratings, archived, `search: false`), so results are identical to today's. The in-memory evaluator is the reference and does not change.

**Files:**
- Create: `backend/src/app/alembic/versions/s0b1c2d3e4f5_attributes_text_trgm.py` (confirm the head with `alembic heads`; it should be `r9a0b1c2d3e4`)
- Modify: `backend/src/app/modules/graph/adapters/persistence/search_sql.py` (`search_clause`), `models.py` (declare the index)
- Tests: `backend/tests/modules/graph/adapters/persistence/test_node_search.py` (new scenarios, both adapters), `backend/tests/platform/test_text_search_index.py` (new, integration EXPLAIN test)

**Interfaces:**
- Consumes: `search_sql.search_clause(q, exclusions)` (used by both `GET /node?q=` through `list`/`count` and by the `text` condition of `/node/search`); `immutable_unaccent` and `pg_trgm` from the Task 5 migration; `like_pattern`.
- Produces: no signature changes. New index `ix_nodes_attributes_text_trgm` on `nodes USING gin (immutable_unaccent((attributes)::text) gin_trgm_ops)`.

- [ ] **Step 1: Write the new scenarios first (RED where they can be).** Add to `test_node_search.py`'s scenario table (both adapters; existing scenarios untouched): a text query containing a double quote that matches a value containing a double quote (seed an item with `notes: 'say "hi" twice'`; JSON stores it escaped, so a naive prefilter would miss it); a query containing a backslash against a value containing one; a 1-character and a 2-character query (below trigram size, so the prefilter is skipped); an accented and a differently cased query against stored values; a number query (`1.5`) matching a stored number; a `ß` query against `strasse`/`Straße` data if the in-memory fold and `unaccent` agree (otherwise leave `ß` out and say so). Add any new seed rows additively and verify no existing expected set changes. These should already pass on the current code (they pin behaviour the prefilter must preserve).
- [ ] **Step 2: Migration.**

```python
def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX ix_nodes_attributes_text_trgm ON nodes
        USING gin (immutable_unaccent((attributes)::text) gin_trgm_ops)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_nodes_attributes_text_trgm")
```

  Declare it on `NodeModel.__table_args__` the way the name/description trigram indexes are (reflected spelling so `test_model_definitions_match_ddl` stays green).
- [ ] **Step 3: Change `search_clause`.** The clause becomes `unaccent_ilike(name) OR unaccent_ilike(description) OR (attrs_prefilter AND attrs_exact_scan)` where `attrs_prefilter` is `immutable_unaccent(attributes::text) ILIKE <pattern> ESCAPE ...` and `attrs_exact_scan` is today's per-type-exclusion scan, unchanged. Skip the prefilter (use only the exact scan, as today) when the query could be missed by it: it contains `"` or `\` (JSON escapes these inside `attributes::text`), contains a control character (code point below 0x20, which JSON escapes), or is shorter than 3 characters (below trigram size, the index cannot help). Put that decision in one small, documented, unit-testable function (`_prefilter_is_safe(q)`), with direct tests for each skip rule. The pattern must be the same escaped pattern as the exact scan. Every user value stays a bind parameter.
- [ ] **Step 4: Prove it is a superset.** Add a randomised/parametrised test (Postgres, integration) that for a table of tricky values (quotes, backslashes, newlines/tabs in strings, unicode, accents, numbers, booleans, nested objects/arrays, empty strings) and a list of queries, the new clause returns exactly the rows the previous exact-only clause returns (compare against the in-memory evaluator's answer, which is the reference). Key names must still never match and booleans/nulls never match, as before.
- [ ] **Step 5: EXPLAIN test (integration).** Seed 20,000 nodes with `generate_series` (some with a rare word in `attributes`), `ANALYZE`, and assert the plan for a selective text query (via the statement `SqlAlchemyNodeRepository.search`/`list` builds) mentions `ix_nodes_attributes_text_trgm` (a `BitmapOr` over the name, description and attributes trigram indexes is expected), without an `enable_seqscan=off` crutch. If the planner will not combine the arms, report it and propose the smallest change (for example a UNION of the three arms) rather than weakening the assertion.
- [ ] **Step 6: Benchmark before/after.** Run `cd backend && uv run python /home/sam/.claude/jobs/706d1499/tmp/bench_search.py 10000 100000` (it starts its own container; filter log lines with `grep -v "\[debug"`). Report the text rows (page and count) beside the baseline above, plus the size of the new index versus the table (`pg_relation_size`) at 100,000 items and the time to build it. Also time the capped count (`search_count(..., limit=1001)`) for the text queries.
- [ ] **Step 7: Gates.** New tests; `cd backend && uv run pytest tests/platform tests/modules/graph -q -m integration`; architecture and CQRS tests; the full unit suite `uv run poe test-backend`; `uv run poe lint-backend`; `uv run poe typecheck-backend`.

### Task 10: Frontend query model (pure TypeScript)

**Files:**
- Create: `frontend/src/lib/query/types.ts`, `operators.ts`, `codec.ts`, `tree.ts`
- Create: `frontend/tests/query-operators.test.ts`, `query-codec.test.ts`, `query-tree.test.ts`

**Interfaces:**
- Produces:
  - `types.ts`: `Operand`, `Condition`, `Group`, `SortKey`, `Query`, `Path = number[]`.
  - `operators.ts`: `KIND_OPERATORS: Record<string, readonly string[]>`, `OPERATOR_LABELS: Record<string, string>`, `operatorTakesValue(op): boolean`, `operatorsForKind(kind): readonly string[]`.
  - `codec.ts`: `encodeQuery(q: Query): string`, `decodeQuery(s: string): Query | null`.
  - `tree.ts`: `emptyQuery()`, `addCondition(q, groupPath, c)`, `addGroup(q, groupPath, op)`, `removeAt(q, path)`, `replaceAt(q, path, node)`, `countConditions(q)`, `isFilterEmpty(q)`, `combine(q, basics: { type?: string | null; q?: string; favourite?: boolean })`.

These are plain `.ts` files, so they are written directly (no Svelte agent).

- [ ] **Step 1: Write the failing tests**

`frontend/tests/query-operators.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import contract from '$shared/contracts/query-operators.json';
import { KIND_OPERATORS } from '$lib/query/operators';

describe('operator table', () => {
	it('matches the shared contract', () => {
		const normalise = (table: Record<string, readonly string[]>) =>
			Object.fromEntries(Object.entries(table).map(([k, v]) => [k, [...v].sort()]));
		expect(normalise(KIND_OPERATORS)).toEqual(normalise(contract));
	});
});
```

`frontend/tests/query-codec.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { decodeQuery, encodeQuery } from '$lib/query/codec';
import type { Query } from '$lib/query/types';

const query: Query = {
	v: 1,
	where: {
		op: 'and',
		children: [
			{ kind: 'field', type: 'film', key: 'title', op: '~', value: 'café ✓' },
			{ op: 'or', children: [{ kind: 'favourite', value: true }] }
		]
	},
	sort: [{ by: 'name', dir: 'asc' }]
};

describe('query codec', () => {
	it('round-trips, including non-ASCII text', () => {
		expect(decodeQuery(encodeQuery(query))).toEqual(query);
	});
	it('produces URL-safe output', () => {
		expect(encodeQuery(query)).toMatch(/^[A-Za-z0-9_-]+$/);
	});
	it.each(['', '!!!', 'e30', btoa('{"v":2,"where":null,"sort":[]}')])(
		'rejects garbage %s',
		(input) => expect(decodeQuery(input)).toBeNull()
	);
});
```

`frontend/tests/query-tree.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import {
	addCondition, addGroup, combine, countConditions, emptyQuery, isFilterEmpty, removeAt, replaceAt
} from '$lib/query/tree';
import type { Condition } from '$lib/query/types';

const fav: Condition = { kind: 'favourite', value: true };
const text: Condition = { kind: 'text', q: 'alien' };

describe('query tree', () => {
	it('starts empty and adds conditions to the root', () => {
		const q = addCondition(emptyQuery(), [], fav);
		expect(q.where).toEqual({ op: 'and', children: [fav] });
		expect(countConditions(q)).toBe(1);
		expect(isFilterEmpty(emptyQuery())).toBe(true);
	});
	it('adds a nested group and puts conditions in it', () => {
		let q = addCondition(emptyQuery(), [], fav);
		q = addGroup(q, [], 'or');
		q = addCondition(q, [1], text);
		expect(q.where).toEqual({ op: 'and', children: [fav, { op: 'or', children: [text] }] });
	});
	it('removes a node, and prunes a group left empty', () => {
		let q = addGroup(addCondition(emptyQuery(), [], fav), [], 'or');
		q = addCondition(q, [1], text);
		q = removeAt(q, [1, 0]);
		expect(q.where).toEqual({ op: 'and', children: [fav] });
	});
	it('removing the last condition clears the filter', () => {
		expect(removeAt(addCondition(emptyQuery(), [], fav), [0]).where).toBeNull();
	});
	it('replaces a condition in place without mutating the input', () => {
		const q = addCondition(emptyQuery(), [], fav);
		const next = replaceAt(q, [0], text);
		expect(next.where).toEqual({ op: 'and', children: [text] });
		expect(q.where).toEqual({ op: 'and', children: [fav] });
	});
	it('combines the page basics with the filter as AND', () => {
		const q = combine(addCondition(emptyQuery(), [], fav), { type: 'film', q: 'ali' });
		expect(q.where).toEqual({
			op: 'and',
			children: [
				{ op: 'and', children: [fav] },
				{ kind: 'type', in: ['film'] },
				{ kind: 'text', q: 'ali' }
			]
		});
	});
	it('combine with no filter and no basics stays empty', () => {
		expect(combine(emptyQuery(), {}).where).toBeNull();
	});
});
```

- [ ] **Step 2: Run, expect failure**

Run: `cd frontend && npx vitest run tests/query-operators.test.ts tests/query-codec.test.ts tests/query-tree.test.ts`
Expected: FAIL (modules missing).

- [ ] **Step 3: Implement**

`types.ts`:

```ts
export type Operand =
	| string
	| number
	| boolean
	| { rel: string }
	| { ref: string }
	| { value: number; currency: string };

type Value = Operand | Operand[];

export type Condition =
	| { kind: 'text'; q: string }
	| { kind: 'type'; in: string[] }
	| { kind: 'favourite'; value: boolean }
	| { kind: 'tag'; mode: 'any' | 'all' | 'none'; tags: string[] }
	| { kind: 'date'; on: 'created' | 'updated'; op: string; value: Value }
	| { kind: 'field'; type: string; key: string; sub_key?: string; op: string; value?: Value };

export type Group = { op: 'and' | 'or' | 'not'; children: (Group | Condition)[] };
export type SortKey = {
	by: 'name' | 'created' | 'updated' | 'field';
	dir?: 'asc' | 'desc';
	type?: string;
	key?: string;
};
export type Query = { v: 1; where: Group | null; sort: SortKey[] };

/** Child indexes from the root group down. `[]` is the root. */
export type Path = number[];

export function isGroup(node: Group | Condition): node is Group {
	return !('kind' in node);
}
```

`operators.ts`:

```ts
const ordered = ['=', '!=', '>', '>=', '<', '<=', 'between', 'empty', 'not_empty'] as const;
const text = ['=', '!=', '~', 'in', 'empty', 'not_empty'] as const;

/** Keep in step with shared/contracts/query-operators.json (a test enforces it). */
export const KIND_OPERATORS: Record<string, readonly string[]> = {
	text, url: text, email: text, phone: text,
	longtext: ['~', 'empty', 'not_empty'],
	number: ordered, duration: ordered, rating: ordered, money: ordered,
	date: ordered, partialdate: ordered,
	boolean: ['=', '!='],
	choice: ['=', '!=', 'in', 'empty', 'not_empty'],
	multichoice: ['has', 'empty', 'not_empty'],
	checklist: ['incomplete', 'complete', 'empty', 'not_empty']
};

export const OPERATOR_LABELS: Record<string, string> = {
	'=': 'is', '!=': 'is not', '~': 'contains', '>': 'is more than', '>=': 'is at least',
	'<': 'is less than', '<=': 'is at most', between: 'is between', in: 'is one of',
	empty: 'is empty', not_empty: 'is not empty', has: 'includes',
	incomplete: 'has unticked items', complete: 'is all ticked'
};

const NO_VALUE = new Set(['empty', 'not_empty', 'incomplete', 'complete']);

export function operatorTakesValue(op: string): boolean {
	return !NO_VALUE.has(op);
}

export function operatorsForKind(kind: string): readonly string[] {
	return KIND_OPERATORS[kind] ?? [];
}
```

`codec.ts`:

```ts
import { isGroup, type Query } from './types';

function toBase64Url(text: string): string {
	let binary = '';
	for (const byte of new TextEncoder().encode(text)) binary += String.fromCharCode(byte);
	return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function fromBase64Url(token: string): string {
	const base64 = token.replace(/-/g, '+').replace(/_/g, '/');
	const binary = atob(base64 + '='.repeat((4 - (base64.length % 4)) % 4));
	return new TextDecoder('utf-8', { fatal: true }).decode(
		Uint8Array.from(binary, (c) => c.charCodeAt(0))
	);
}

/** The query as a URL-safe string. The server validates; this is only transport. */
export function encodeQuery(query: Query): string {
	return toBase64Url(JSON.stringify(query));
}

/** Parse a query from the URL, or null when it is not one. */
export function decodeQuery(token: string): Query | null {
	if (!token) return null;
	try {
		const data = JSON.parse(fromBase64Url(token)) as Partial<Query>;
		if (data.v !== 1 || !Array.isArray(data.sort)) return null;
		if (data.where !== null && (typeof data.where !== 'object' || isGroup(data.where) === false))
			return null;
		return data as Query;
	} catch {
		return null;
	}
}
```

(`isGroup(data.where)` for a non-null object: it is a group when it has no `kind`. Simplify the check if the type-narrowing fights `strict`.)

`tree.ts`:

```ts
import { isGroup, type Condition, type Group, type Path, type Query } from './types';

export function emptyQuery(): Query {
	return { v: 1, where: null, sort: [] };
}

function groupAt(root: Group, path: Path): Group {
	let node: Group = root;
	for (const index of path) {
		const next = node.children[index];
		if (!next || !isGroup(next)) throw new Error('Not a group');
		node = next;
	}
	return node;
}

function cloneGroup(group: Group): Group {
	return {
		op: group.op,
		children: group.children.map((c) => (isGroup(c) ? cloneGroup(c) : { ...c }))
	};
}

function withRoot(query: Query, edit: (root: Group) => void): Query {
	const root = query.where ? cloneGroup(query.where) : { op: 'and' as const, children: [] };
	edit(root);
	return { ...query, where: prune(root) };
}

/** Drop groups left with no children; an empty root becomes null. */
function prune(group: Group): Group | null {
	const children = group.children.flatMap((c) => {
		if (!isGroup(c)) return [c];
		const pruned = prune(c);
		return pruned ? [pruned] : [];
	});
	return children.length ? { op: group.op, children } : null;
}

export function addCondition(query: Query, groupPath: Path, condition: Condition): Query {
	return withRoot(query, (root) => groupAt(root, groupPath).children.push(condition));
}

export function addGroup(query: Query, groupPath: Path, op: 'and' | 'or' | 'not'): Query {
	// An empty group would be pruned straight away, so the builder adds the first
	// condition in the same step; keep the group alive until then.
	const root = query.where ? cloneGroup(query.where) : { op: 'and' as const, children: [] };
	groupAt(root, groupPath).children.push({ op, children: [] });
	return { ...query, where: root };
}

export function removeAt(query: Query, path: Path): Query {
	const parentPath = path.slice(0, -1);
	const index = path[path.length - 1];
	return withRoot(query, (root) => groupAt(root, parentPath).children.splice(index, 1));
}

export function replaceAt(query: Query, path: Path, node: Condition | Group): Query {
	const parentPath = path.slice(0, -1);
	const index = path[path.length - 1];
	return withRoot(query, (root) => {
		groupAt(root, parentPath).children[index] = node;
	});
}

export function countConditions(query: Query): number {
	const count = (g: Group): number =>
		g.children.reduce((n, c) => n + (isGroup(c) ? count(c) : 1), 0);
	return query.where ? count(query.where) : 0;
}

export function isFilterEmpty(query: Query): boolean {
	return countConditions(query) === 0;
}

/** AND the page's own type, text and favourite controls into the advanced filter. */
export function combine(
	query: Query,
	basics: { type?: string | null; q?: string; favourite?: boolean }
): Query {
	const extra: Condition[] = [];
	if (basics.type) extra.push({ kind: 'type', in: [basics.type] });
	if (basics.q) extra.push({ kind: 'text', q: basics.q });
	if (basics.favourite) extra.push({ kind: 'favourite', value: true });
	const children = [...(query.where ? [query.where] : []), ...extra];
	return { ...query, where: children.length ? { op: 'and', children } : null };
}
```

The `addGroup` comment reflects one real design point: the builder UI creates an empty group and shows it with an "Add condition" prompt, so `addGroup` is deliberately the one operation that does not prune; every other operation prunes. Adjust the `removes a node, and prunes…` test if you change this.

- [ ] **Step 4: Run, expect pass; then check**

Run: `cd frontend && npx vitest run tests/query-*.test.ts && cd .. && poe lint-frontend && poe typecheck-frontend`
Expected: PASS.

**Checkpoint:** user may commit.

---

### Task 10b: A shared fixture for query shapes (backend parser and frontend decoder agree)

User-requested follow-up to the Task 10 review. `shared/contracts/query-operators.json` pins which operators each field kind allows, but nothing pins what a *valid query tree* looks like. The frontend decoder (`decodeQuery`, Task 10) is looser than the server's `parse_query`: it accepts any date operator string, any field operator, `between` with other than two operands, no-value operators carrying a value, malformed relative dates and empty strings or lists, and it rejects `"sub_key": null` and a missing `sort`, which the server accepts. A hand-edited link can therefore decode in the browser and still be rejected by the server. This task makes one fixture the arbiter and brings the decoder to parity with the server's *structural* rules.

**Scope:** structure only, i.e. what `parse_query` (`backend/src/app/modules/graph/domain/query.py`) accepts or rejects. Whether an operator suits a particular field kind or a value fits a field is resolved against item-type schemas on the server (`resolve_fields`) and is out of scope.

**Files:**
- Create: `shared/contracts/query-shapes.json`
- Create: `backend/tests/modules/graph/domain/test_query_shapes_contract.py`
- Modify: `frontend/src/lib/query/codec.ts` (decoder parity), `frontend/tests/query-codec.test.ts` (existing expectations that assert the old looseness are updated deliberately, with a note), create `frontend/tests/query-shapes-contract.test.ts`
- Modify: `shared/README.md` (new contracts row; fix the operators row, whose frontend test now exists rather than being "added in a later task")

**Fixture format** (`shared/contracts/query-shapes.json`):

```json
{
  "valid": [
    { "name": "empty query", "query": { "v": 1, "where": null } }
  ],
  "invalid": [
    { "name": "between with one operand", "path": "where.children[0]",
      "query": { "v": 1, "where": { "op": "and", "children": [
        { "kind": "field", "type": "film", "key": "year", "op": "between", "value": [1980] } ] } } }
  ]
}
```

`path` is the JSON path the server reports for the first problem (`InvalidQueryError.path`); the backend test asserts it, the frontend test ignores it (the decoder only returns null). Extra unknown keys on a node are ignored by the server and dropped by the decoder: include a valid case.

- [ ] **Step 1: Write the fixture.** Cover every structural rule in `parse_query`, each as its own named case, both sides of every boundary:
  - Version: `v` missing, `v` wrong, `where` absent vs null; `sort` absent (valid), `sort: []`, non-list sort, 3 keys (valid) vs 4, unknown `by`, bad `dir`, `by: field` without `type` or `key`, `type`/`key` over 200 characters or empty.
  - Groups: unknown `op`, empty `children`, `not` with 0, 1 (valid) and 2 children, nested to depth 4 (valid) and 5, a non-object child, a child that is neither group nor condition.
  - Conditions by kind: `text` (`q` empty, 1 and 200 characters valid, 201 invalid, non-string); `type` (`in` empty, 1..50 valid, 51, non-list, non-string items); `favourite` (`value` true/false valid, missing, non-bool); `tag` (bad `mode`, empty `tags`, 1..50 valid, 51); `date` (`on` created/updated valid, other invalid; `op` each of `= > >= < <= between` valid, `empty`/`~`/unknown invalid; `between` needs exactly two; value missing); `field` (`type`/`key` empty/201 chars, `sub_key` string valid, **null valid**, empty string invalid; every operator in the server's list valid, unknown invalid).
  - Operands: literal string/int/float/bool valid; null invalid; nested list in a scalar slot invalid; `{rel:"-30d"}` valid, `{rel:"30"}`, `{rel:"-1000d"}`, `{rel:"-30x"}`, `{rel:"-30d\n"}` invalid (server regex is fully anchored); `{ref:"k"}` valid, `{ref:""}`, `{ref:5}` invalid; money `{value: 3.5, currency: "GBP"}` valid, `{value:true,currency:"GBP"}` (bool is not a number) invalid, missing currency invalid; an object with other keys invalid.
  - Arity by operator: `between` exactly 2 (1 and 3 invalid); `in` list 1..50 (scalar invalid, empty invalid, 51 invalid); `has` scalar or list 1..50; no-value operators `empty`, `not_empty`, `incomplete`, `complete` with and without a `value` key (with it: invalid); every other operator needs a scalar `value` (missing invalid, list invalid).
  - Totals that need generation (51 conditions, strings of 201 characters) may be written inline in the tests instead of the file; say which in the test.
  Read `parse_query` closely; the fixture must be derived from the server's code, not from the frontend's, and every `invalid` case must really fail on the server and every `valid` one really parse.
- [ ] **Step 2: Backend contract test (RED first, then fix any fixture case the server disagrees with).** `test_query_shapes_contract.py` loads the fixture through `shared_data_path("contracts/query-shapes.json")`; parametrised over `valid` (must parse without error) and `invalid` (must raise `InvalidQueryError` whose `.path` equals the fixture's `path`). A fixture case the server disagrees with is a fixture bug, fix the case, never the server.
- [ ] **Step 3: Frontend contract test (RED).** `frontend/tests/query-shapes-contract.test.ts` imports the fixture through `$shared/contracts/query-shapes.json` and, for each case, runs `decodeQuery(encodeQuery(query as Query))` (encode accepts any object; use a cast): `valid` must return a non-null query, `invalid` must return null. Many `invalid` cases will fail on the current decoder: that is the point.
- [ ] **Step 4: Bring `decodeQuery` to parity.** Tighten the decoder in `codec.ts` so every fixture case agrees: lower bounds as well as upper bounds (strings 1..200, lists 1..50), the date operator set, the global operator set for fields, exact arity per operator, the no-value operators, the anchored relative-date regex `^[+-]?\d{1,3}[dwmy]$`, money shape (number that is not a boolean, non-empty currency), `{ref}` non-empty, `sub_key: null` accepted and normalised to absent, missing `sort` accepted as `[]`. Keep the sanitising rebuild, depth and condition limits, and the never-throws guarantee. Update the existing `query-codec.test.ts` expectations that asserted the old looseness (for example the test that a missing `sort` is rejected), explaining each change in the report.
- [ ] **Step 5: Gates.** Backend: the new test, `cd backend && uv run pytest tests/modules/graph/domain tests/architecture -q`, `uv run poe lint-backend`, `uv run poe typecheck-backend` (and the full unit suite `uv run poe test-backend`, since it runs in the user's pre-commit). Frontend: the three query test files plus the new one, `uv run poe lint-frontend`, `uv run poe typecheck-frontend`, `uv run poe test-frontend`.

### Task 11: Filter builder UI and items-page integration

All `.svelte` and `.svelte.ts` files in this task are written by the **`svelte-file-editor` subagent**. Give it this task text, the spec's Frontend section, `frontend/README.md` and `frontend/DESIGN_GUIDELINES.md`.

**Files:**
- Create: `frontend/src/lib/components/query-builder.svelte` (the panel; a `responsive-dialog` or `popover` per the guidelines), `query-group.svelte` (recursive), `query-condition-row.svelte`, `query-value-input.svelte`, `query-chips.svelte`
- Create: `frontend/src/lib/query/summary.ts` (plain TS: `describeCondition`) and `frontend/tests/query-summary.test.ts`
- Create: `frontend/src/lib/query/search.ts` (plain TS: `runSearch`, wraps `searchNodes` and returns `{ items, total, nextCursor, warnings }`) and `frontend/tests/query-search.test.ts`
- Modify: `frontend/src/routes/items/+page.svelte`

**Interfaces:**
- Consumes: Task 10 modules; `searchNodes` from `$lib/api/client`; `getDescriptor` / `descriptorForProp` and each descriptor's `InputWidget` and `formatSummary`; the item-type list the page already loads (`NodeTypeResponse[]` with `attributes_schema`); `readPropMeta` for archived and kind.
- Produces: `runSearch` returns `{ items, total, totalCapped, nextCursor, warnings }` (mapping the response's `total_capped`); `describeCondition(c: Condition, lookup: { typeLabel(slug: string): string; fieldLabel(type: string, key: string): string }): string`.

- [ ] **Step 1: Pure parts first (TDD, written directly, not by the agent)**

`describeCondition` tests, in `frontend/tests/query-summary.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { describeCondition } from '$lib/query/summary';

const lookup = {
	typeLabel: (slug: string) => (slug === 'film' ? 'Film' : slug),
	fieldLabel: (_type: string, key: string) => (key === 'rating' ? 'Rating' : key)
};

describe('describeCondition', () => {
	it.each([
		[{ kind: 'field', type: 'film', key: 'rating', op: '>=', value: 4 }, 'Film: Rating is at least 4'],
		[{ kind: 'field', type: 'film', key: 'rating', op: 'between', value: [3, 5] }, 'Film: Rating is between 3 and 5'],
		[{ kind: 'field', type: 'film', key: 'rating', op: 'empty' }, 'Film: Rating is empty'],
		[{ kind: 'field', type: 'film', key: 'stock', op: '<=', value: { ref: 'reorder_at' } }, 'Film: stock is at most reorder_at'],
		[{ kind: 'tag', mode: 'any', tags: ['noir', 'classic'] }, 'Tag is any of noir, classic'],
		[{ kind: 'favourite', value: true }, 'Is a favourite'],
		[{ kind: 'text', q: 'alien' }, 'Contains “alien”'],
		[{ kind: 'date', on: 'created', op: '>=', value: { rel: '-30d' } }, 'Added in the last 30 days']
	] as const)('%j', (condition, expected) => {
		expect(describeCondition(condition, lookup)).toBe(expected);
	});
});
```

Implement `summary.ts` until it passes (relative dates read "in the last N days/weeks/months/years" for `>=` with a negative offset, "more than N … ago" for `<` , and "N … from now" otherwise; plain values use the field type's `formatSummary` when the kind is known, else `String`). `runSearch` wraps the generated `searchNodes` call, throwing through `networkAwareError` like the other API helpers; test it with the mocks in `frontend/tests/mocks` (see `collections.test.ts` for the pattern).

Run: `cd frontend && npx vitest run tests/query-summary.test.ts tests/query-search.test.ts`
Expected: PASS.

- [ ] **Step 2: Delegate the components to `svelte-file-editor`**

Behaviour the subagent must deliver (acceptance list; each point gets a component test or an e2e assertion):

1. **Items page.** A "Filters" button beside the search box, showing the number of conditions as a badge. State lives in the URL: `?f=<encodeQuery(query)>`. The result count shows the exact total, or "1,000+ items" when the response has `total_capped` (never imply an exact number then). An unparsable `f` is ignored with a toast "That filter link isn't valid." When `f` holds at least one condition, the list is loaded with `runSearch` (cursor paging replaces `after`); otherwise the existing `listNodes` path is untouched. The page's type select, search box and favourite state are folded in with `combine(...)`, so they keep working together with the filter. The "Matched in …" context still shows for text.
2. **Builder panel.** A dialog on desktop and full-height on mobile (follow `responsive-dialog`). Contents: the root group as "Match **all** / **any** of these" (a segmented control mapping to `and` / `or`); rows `field / operator / value`; "Add condition" and "Add group" buttons per group; per-row remove; a sort control (name, added, changed, or a field of a chosen type) with direction; "Clear all" and "Done". Edits apply live to the URL (debounce 250 ms).
3. **Row.** First choose what the condition is about, from one grouped list: "Type", "Favourite", "Tags", "Added / Changed", then each item type's non-archived, filterable fields as "Film › Rating". The operator list is `operatorsForKind(kind)` with `OPERATOR_LABELS`. The value input is `query-value-input.svelte`: it reuses the field type's `InputWidget` for single values (number, duration, rating, date, partial date, money, choice, yes/no), a two-input range for `between`, a multi-select for `in` / `has` over the field's options, a chip input for tags, a text box for `~`, and a "compare with another field" toggle (offered only for kinds in `REF_KINDS`: number, duration, rating, money, date) that shows a select of same-kind fields on that type. Dates offer "a date" or "N days / weeks / months / years ago".
4. **Chips.** Active conditions render as removable chips using `describeCondition`; clicking a chip opens the panel scrolled to that row. A condition the server reported in `warnings` (match by `path`) shows a warning icon and the text "This field no longer exists, so nothing matches."
5. **States.** Loading uses the existing delayed-skeleton pattern; empty results show the existing empty state with "Clear filters"; a 400 response shows the server's `detail` in an inline alert in the panel, not a toast.
6. **Accessibility.** The panel is a labelled dialog with focus trapping and Escape to close; every row control has an accessible name ("Condition 2, field", "operator", "value"); add and remove announce through the existing live region; the whole builder works by keyboard alone; the `/` and filter shortcuts follow `shortcuts.svelte.ts` (register "Filters" on `f`, shown in the shortcuts help dialog).
7. **Copy.** British English; never node, edge or graph. Use "item", "type", "field", "filter".
8. **No new dependencies.** Reuse shadcn-svelte components already in `components/ui`; add a missing one with the shadcn-svelte CLI per `frontend/README.md` only if truly needed (for example `toggle-group` for all/any).

- [ ] **Step 3: Component tests**

Ask the subagent to add Vitest component tests (see `attributes-editor.test.ts` for the harness) covering: adding a condition produces the expected tree; switching a field kind resets the operator and value; `between` renders two inputs; the reference toggle is absent for text fields; removing the last condition clears the filter and falls back to `listNodes`.

- [ ] **Step 4: Run the frontend gate**

Run: `poe lint-frontend && poe typecheck-frontend && poe test-frontend`
Expected: PASS (`svelte-check` clean).

- [ ] **Step 5: Manual check in the browser**

Run `poe serve`, install the Games example pack from the Examples page, then build: Games › Play time is at most 45 minutes AND Games › Weight is one of Light, Medium; confirm the list narrows, the URL changes, a reload restores it, a copied link opens the same filter, and the mobile layout (narrow the window) works. Report what you saw; do not claim success from tests alone.

**Checkpoint:** user may commit.

---

### Task 12: End-to-end test, documentation and spec reconciliation

**Files:**
- Create: `frontend/tests/e2e/advanced-search.spec.ts`
- Modify: `docs/DECISIONS.md`, `shared/README.md` (already touched in Task 1), `backend/README.md` (one paragraph under persistence: the search methods), the spec (reconciliation)

- [ ] **Step 1: Write the e2e spec**

Follow `collections.spec.ts` and `helpers.ts` for sign-in, fixtures and API seeding. Create an item type with a number field and a choice field through the API helpers, seed four items, then through the UI:

```ts
test('filter items by a field and share the link', async ({ page, request }) => {
	// seed via helpers: type "Tool" with number "weight" and choice "grade"; items A(2,"a"), B(5,"a"), C(8,"b"), D(none)
	await page.goto('/items');
	await page.getByRole('button', { name: 'Filters' }).click();
	await page.getByRole('button', { name: 'Add condition' }).click();
	// choose Tool › weight, "is at least", 5
	// ... (use accessible names from the builder: "Condition 1, field", "operator", "value")
	await expect(page.getByRole('link', { name: /Item B/ })).toBeVisible();
	await expect(page.getByRole('link', { name: /Item A/ })).toHaveCount(0);
	const url = page.url();
	await page.reload();
	await expect(page.getByRole('link', { name: /Item B/ })).toBeVisible();
	await page.goto(url);
	await expect(page.getByRole('link', { name: /Item C/ })).toBeVisible();
});

test('a group can match any, and a stale condition shows a warning', async ({ page }) => { /* ... */ });
test('the builder works by keyboard alone', async ({ page }) => { /* Tab/Enter/Arrow through add, edit, remove */ });
```

Write all three tests in full using the helper functions; no placeholders remain when this task is done. The second test deletes the field via the API after saving the URL and expects the warning text.

- [ ] **Step 2: Run e2e**

Run the repo's e2e command (see `frontend/package.json` `test:e2e` and CONTRIBUTING.md for the stack it needs).
Expected: the new spec passes; the existing 149 e2e still pass.

- [ ] **Step 3: DECISIONS.md entries**

Add three entries in the file's existing style (Decision / Rationale / Consequence), British English:

1. **The condition tree is the only stored form of a search.** JSON, versioned (`v`), parsed into frozen domain types; text syntax later is a parser and printer over it. Limits: depth 4, 50 conditions. Stale fields warn and match nothing; wrong operators are 400s with a JSON path.
2. **Search is separate from the list, and pages by keyset on the sort values.** `NodeRepository.search` / `search_count` beside `list` / `count`; cursor is opaque base64url JSON; nulls last; ties by id. The Python evaluator is the reference and the SQL compiler must agree (scenario table in `test_node_search.py`, run against both). Also records the Task 9b benchmark (before/after figures at 10,000 and 100,000 items), the capped total (`TOTAL_CAP = 1000`, `total_capped`) the Task 9c trigram prefilter for free text (superset argument, skip rules, the `unaccent`-to-quote characters pinned by a whole-Unicode test, `SET LOCAL jit = off` for text queries only, before/after timings) and the remaining known limits: field sorts (rating) still scan, and a free-text query whose candidates are numerous still pays for the exact check ("director 42" about 500 ms at 100,000 items). Records the `EXPLAIN` findings from Task 6: containment forms (choice, yes/no, multi-choice, tags) and name/description trigram searches use the GIN indexes; numeric, date and partial-date comparisons and sorting on a field scan, which is acceptable at the sizes expected and is the first thing to measure if search feels slow.
3. **Operators per field kind are one shared table.** `shared/contracts/query-operators.json`, read by backend and frontend tests, because the backend has no field-type descriptors of its own.

- [ ] **Step 4: Reconcile the spec**

In `docs/superpowers/specs/2026-10-14-smart-collections-advanced-search-design.md`: change `Status` to "phase 1 planned (`docs/superpowers/plans/2026-10-14-query-engine-advanced-search.md`)"; in Architecture replace "`NodeRepository.list` and `count` take an optional `query`" with the separate `search` / `search_count` methods (with the reason); replace "the backend `FieldTypeDescriptor` declares each type's operators" with the backend operator table keyed by field kind; and in Frontend replace "compressed, base64url" with "base64url".

- [ ] **Step 5: Final gates**

Run: `poe lint && poe typecheck && poe test && poe coverage`
Expected: PASS; domain, application and shared_kernel at 100%, adapters ≥ 80%. Then `poe test-backend-integration` once more.

- [ ] **Step 6: Stop for review**

Report: files changed, the final gate output, the Task 6 `EXPLAIN` findings, and anything that deviated from this plan. Leave the commit to the user.

---

## Self-Review

**Spec coverage (phase 1).** Query model and operators → Tasks 1–3; text/type/favourite/tag/date/field conditions → Tasks 2, 4, 6; field references and relative dates → Tasks 2, 3, 4, 6; repeating-group rows (`sub_key`) → Tasks 2, 3, 4, 6 (supported by the engine; the phase-1 builder does not offer a column picker, which is listed in the acceptance list as a follow-up inside Task 11 if cheap, otherwise phase 2); partial-date and money semantics → Tasks 4, 6; stale conditions → Tasks 3, 4, 8, 9, 11; indexes → Task 5; keyset paging and sorting → Tasks 4, 6, 7, 8; `POST /node/search` → Task 9; builder UI, URL state, warnings → Tasks 10–11; contract fixture → Task 1; docs and spec reconciliation → Task 12. Smart collections, connection conditions and pack changes are explicitly phases 2–4.

**Placeholders.** None intended. The two places that defer detail are deliberate and bounded: Task 11 delegates Svelte code to the mandated subagent with a numbered acceptance list, and Task 8's last test and Task 12's second and third e2e tests say which existing helper to copy because those helpers' exact names were not read.

**Type consistency.** `FieldKey`, `SortValue`, `Cursor`, `SearchHit`, `ResolvedQuery` are defined once in Task 2 and used unchanged in Tasks 4, 6, 7 and 8. `search` / `search_count` signatures in Task 4's port match Task 6's implementation and Task 8's calls. Operator names (`=`, `!=`, `~`, `>`, `>=`, `<`, `<=`, `between`, `in`, `empty`, `not_empty`, `has`, `incomplete`, `complete`) match across the JSON contract, `field_kinds.py`, the parser's `_OPERATORS` and the frontend table.

**Review Focus.** Each of the five has a named test: NOT/stale/wrong-typed (scenarios "not rating 4+…", "wrong-typed value…", "not of a stale field…"); partial dates (scenarios in Task 4, exercised against Postgres in Task 6); keyset paging (`test_paging_*` for both directions, plus the deleted-cursor test); cross-user `OR` (scenario "or group cannot reach another user's items", `test_everyone_scope…`, and the router test); LIKE wildcards and accents (scenarios "text treats % and _ literally", "text is accent-insensitive").
