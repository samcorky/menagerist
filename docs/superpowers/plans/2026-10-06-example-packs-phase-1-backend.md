# Example Packs, Phase 1: the `examples` backend module

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A backend `examples` module that lists shipped example packs, installs one (item types, relationship types, items, connections and presets), and uninstalls it, keeping anything the user changed. Reachable through three API routes.

**Architecture:** A new bounded context with its own domain, application, ports and adapters. It imports neither `graph` nor `presets`. It reaches them through two driven ports it owns (`PresetTarget`, `GraphTarget`), implemented in `entrypoints/api/shared/example_targets.py` by calling the real use cases. Install is an ordered list of steps; every created entity is recorded and committed immediately; failure triggers the same removal routine that uninstall uses.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy (async) and Alembic, pytest (plus pytest-alembic, testcontainers, archunitpython), structlog.

**Spec:** `docs/superpowers/specs/2026-10-06-example-packs-design.md`. The master plan `docs/superpowers/plans/2026-10-06-example-packs.md` covers all phases; this file is the detailed version of its Phase 1 and supersedes the Phase 1 section where they differ (see "Refinements" below).

**Prerequisite:** Phase 0 (the partial unique slug index) is committed.

## Global Constraints

- **Never run `git add` or `git commit`.** Each task ends with a checkpoint where the tree is left for the user to review and commit (CLAUDE.md, AGENTS.md). No `Co-Authored-By` trailer in drafted messages.
- Python 3.14; `mypy --strict`; no `from __future__ import annotations`; no quoted annotations; imports used only for annotations go under `if TYPE_CHECKING:`; classes a `CommandHandler` needs at runtime for `__init__` annotations keep a runtime import with `# noqa: TC001` (see `create_node_type.py`). Run `poe format` then `poe lint-backend` after each task; ruff will tell you which imports to move.
- British English in code, comments and docstrings. Comments only where intent is unclear. Google-style docstrings only where they add value.
- Entities: `@dataclass(kw_only=True, eq=False)`, `uuid.uuid7()` ids, timestamps set in domain methods with `datetime.now(UTC)`, invariants in `__post_init__` raising `shared_kernel.errors.ValidationError` subclasses.
- **Domain layer may import externally only** `dataclasses, typing, types, uuid, datetime, enum, abc, collections, mimetypes, re` (plus `app.shared_kernel`). No `json`, no `hashlib`. Application and ports may not import `fastapi, starlette, sqlalchemy, PIL, filetype, aiofiles`. No import cycles.
- `examples` must not import `app.modules.graph` or `app.modules.presets` (Task 1.1 adds a test).
- Every port ships an in-memory sibling. Commands take a unit of work and commit; queries take a repository bundle.
- Coverage floors: domain 100%, application 100%, adapters 80%.
- The application owns every constraint; DB indexes are backstops.
- Use `poe` tasks. Put `.venv/bin` on `PATH` in a fresh shell: `export PATH=$PWD/.venv/bin:$PATH` from the repo root. Integration tests need Docker.
- Every API model needs OpenAPI `examples` (an existing test requires it), and request bodies subclass `RequestModel`.
- Do not edit `frontend/src/lib/api/generated/` by hand.

## Refinements to the master plan (found while planning this phase)

1. **Targets need no `owned_ids`.** Because uninstall settles connections, then items, then types, then presets, by the time an item is inspected every pack-owned connection touching it is already gone or kept. So "any live edge touches this item" means user data, and "any live item of this type" means the type is in use. `inspect(kind, entity_id)` takes no extras.
2. **`InstallFailedError` is a plain `Exception`, not a `DomainError`.** `problem_response._status_for` only knows the four base types, and a `DomainError` outside them would crash the handler. A plain exception goes through the existing catch-all and returns a 500 problem response with the message as `detail`, which is the right status for a server-side failure.
3. **Entity records carry a human `label`** (item name, type label) so the kept-report can say what was kept without the UI showing slug-like refs.
4. **Persist after every created entity**, not every step, so a crash leaves at most one unrecorded entity.
5. **Failure rollback and uninstall share one routine** (`settle_installation`).
6. `FAILED` means "rolled back with nothing left owned"; a rollback that cannot finish leaves the installation `INSTALLING`, which uninstall resumes.

## File Structure

```
backend/src/app/modules/examples/
  domain/
    errors.py            error types (all but InstallFailedError subclass the shared bases)
    pack.py              pack value objects, ExamplePack (validates itself), preset-ref helpers
    installation.py      Installation entity, EntityRecord, status and outcome enums
    removal.py           decide_removal(): the pure keep-or-remove rule
  application/
    content_hash.py      content_hash(): canonical SHA-256 of a content dict
    removal.py           settle_installation(): remove or keep every owned entity
    list_example_packs.py
    install_example_pack.py
    uninstall_example_pack.py
  ports/
    pack_catalogue.py
    installation_repository.py
    unit_of_work.py
    pack_targets.py      Created, Inspection, PresetOutcome, RemoveResult, PresetTarget, GraphTarget
  adapters/
    platform/
      pack_parser.py              JSON dict -> domain values (strict)
      file_pack_catalogue.py      reads shared/examples/
      in_memory_pack_catalogue.py
    persistence/
      models.py  installation_repository.py  in_memory_installation_repository.py  unit_of_work.py
    api/
      dependencies.py
      example/router.py  example/schemas.py
backend/src/app/entrypoints/api/shared/example_targets.py   PresetPackTarget, GraphPackTarget, stores
backend/src/app/alembic/versions/g8b9c0d1e2f3_create_example_installations.py
backend/tests/modules/examples/  (mirrors the tree; support.py holds shared builders)
```

Modified: `modules/presets/application/import_presets.py`, `entrypoints/api/__init__.py`, `alembic/env.py`, `tests/architecture/test_architecture.py`.

## Review Focus

- A truth-table row wrong in `decide_removal` deletes user data (Task 1.2).
- A preset that already existed must never become pack-owned (Tasks 1.4, 1.5, 1.7).
- A crash between an entity's creation and its recording leaves one orphan; the next install's slug pre-flight must name it (Task 1.7 test).
- A failed rollback must leave the installation resumable, not `failed` (Task 1.7).
- Hashing must ignore key order and `favourite`, and must survive a JSONB round trip (Tasks 1.5, 1.6, 1.9).
- A pack file with an unknown key, wrong version, or mismatched id must be rejected with `InvalidPackError`, never a `KeyError` (Task 1.10).

---

## Task 1.1: Skeleton and architecture rule

**Files:**
- Create: `__init__.py` (empty) in `modules/examples/`, `domain/`, `application/`, `ports/`, `adapters/`, `adapters/api/`, `adapters/api/example/`, `adapters/persistence/`, `adapters/platform/` (check an existing module such as `presets` for whether its `__init__.py` files are empty, and match)
- Create: `backend/tests/modules/examples/{domain,application,adapters}/` (directories with `__init__.py` only if the sibling test trees have them)
- Modify: `backend/tests/architecture/test_architecture.py`

**Interfaces:** Produces the package layout every later task imports from.

- [ ] **Step 1: Write the architecture test**

Append to `backend/tests/architecture/test_architecture.py`:

```python
def test_examples_module_is_independent_of_graph_and_presets() -> None:
    """`examples` reaches `graph` and `presets` only through its own ports."""
    for other in ("graph", "presets"):
        rule = (
            project_files(SRC_PATH)
            .in_folder("*modules/examples*")
            .should_not()
            .depend_on_files()
            .in_folder(f"*modules/{other}*")
        )
        assert_passes(rule)
```

(While planning, the same rule form was run against `presets -> graph`, `graph -> presets` and `graph -> media` and all were clean, so it is a safe pattern. Adding those three as tests is a one-line follow-up.)

- [ ] **Step 2: Create the empty packages**

Run: `mkdir -p backend/src/app/modules/examples/{domain,application,ports,adapters/{api/example,persistence,platform}} backend/tests/modules/examples/{domain,application,adapters}` then create the empty `__init__.py` files listed above.

- [ ] **Step 3: Run it**

Run: `export PATH=$PWD/.venv/bin:$PATH && cd backend && ../.venv/bin/python -m pytest tests/architecture -q`
Expected: PASS (nothing to violate yet).

- [ ] **Step 4: Checkpoint.** Run `poe lint-backend`. Leave the tree uncommitted.

---

## Task 1.2: Domain

**Files:**
- Create: `domain/errors.py`, `domain/pack.py`, `domain/installation.py`, `domain/removal.py`
- Test: `backend/tests/modules/examples/domain/test_pack.py`, `test_installation.py`, `test_removal.py`

**Interfaces:**
- Produces (used by every later task):
  - `errors`: `PackNotFoundError(NotFoundError)`, `PackAlreadyInstalledError(ConflictError)`, `PackNotInstalledError(ConflictError)`, `SlugClashError(ConflictError)` with `.kind` and `.slug`, `InvalidPackError(ValidationError)`, `InvalidInstallationStateError(ConflictError)`, `InstallFailedError(Exception)`.
  - `pack`: `PackPreset`, `PackRelationshipType`, `PackItemType`, `PackItem`, `PackConnection`, `PackCounts`, `PackSummary`, `ExamplePack`, `preset_refs(schema)`, `resolve_preset_refs(schema, ids)`, `PRESET_MARKER`.
  - `installation`: `InstallationStatus`, `EntityKind`, `Outcome`, `REMOVAL_ORDER`, `EntityRecord`, `Installation`.
  - `removal`: `Action`, `RemovalDecision`, `decide_removal`, `KEEP_EDITED`, `KEEP_USER_DATA`, `KEEP_IN_USE`.

### 1.2a Errors

- [ ] **Step 1: Write `domain/errors.py`**

```python
from app.shared_kernel.errors import ConflictError, NotFoundError, ValidationError


class PackNotFoundError(NotFoundError):
    """Raised when an example pack id is not in the catalogue."""


class PackAlreadyInstalledError(ConflictError):
    """Raised when installing a pack that is installed or only half installed."""


class PackNotInstalledError(ConflictError):
    """Raised when removing a pack that is not installed."""


class SlugClashError(ConflictError):
    """Raised when a type the pack would create already exists."""

    def __init__(self, *, kind: str, slug: str) -> None:
        super().__init__(
            f"You already have {kind} called '{slug}'. Rename or remove it, "
            "then try again."
        )
        self.kind = kind
        self.slug = slug


class InvalidPackError(ValidationError):
    """Raised when a pack file or its content is malformed."""


class InvalidInstallationStateError(ConflictError):
    """Raised when an installation is asked to make an impossible change."""


class InstallFailedError(Exception):
    """Raised when an install failed part-way and was rolled back.

    Deliberately not a `DomainError`: it is a server-side failure, so the API
    reports it through the catch-all handler as a 500 problem response.
    """
```

(`SlugClashError`'s `kind` is a phrase such as `"an item type"` or `"a relationship type"`, so the message reads naturally.)

### 1.2b Pack

- [ ] **Step 2: Write the failing tests** `tests/modules/examples/domain/test_pack.py`

```python
import pytest

from app.modules.examples.domain.errors import InvalidPackError
from app.modules.examples.domain.pack import (
    MAX_ITEMS,
    ExamplePack,
    PackConnection,
    PackItem,
    PackItemType,
    PackPreset,
    PackRelationshipType,
    preset_refs,
    resolve_preset_refs,
)

_LIST = {"$preset": "grades"}
_SCHEMA = {
    "type": "object",
    "properties": {
        "condition": {"type": "string", "x-menagerist": {"kind": "choice", "list": _LIST}}
    },
}


def _pack(**overrides: object) -> ExamplePack:
    base: dict[str, object] = {
        "id": "demo",
        "presets": (
            PackPreset(ref="grades", kind="choice_list", label="Grades",
                       definition={"options": ["Mint"]}),
        ),
        "relationship_types": (
            PackRelationshipType(ref="signed-by", slug="signed-by", label="Signed by"),
        ),
        "item_types": (
            PackItemType(ref="record", slug="record", label="Record",
                         attributes_schema=_SCHEMA),
            PackItemType(ref="person", slug="person", label="Person"),
        ),
        "items": (
            PackItem(ref="a", type_ref="record", name="A"),
            PackItem(ref="b", type_ref="person", name="B"),
        ),
        "connections": (
            PackConnection(source_ref="a", target_ref="b", type_ref="signed-by"),
        ),
    }
    base.update(overrides)
    return ExamplePack(**base)  # type: ignore[arg-type]


def test_a_valid_pack_reports_its_counts() -> None:
    counts = _pack().counts
    assert (counts.presets, counts.relationship_types, counts.item_types) == (1, 1, 2)
    assert (counts.items, counts.connections) == (2, 1)


@pytest.mark.parametrize(
    "overrides",
    [
        {"id": "Bad Id"},
        {"items": (PackItem(ref="a", type_ref="record", name="A"),
                   PackItem(ref="a", type_ref="person", name="Dup"))},
        {"items": (PackItem(ref="a", type_ref="nope", name="A"),)},
        {"connections": (PackConnection(source_ref="a", target_ref="zz", type_ref="signed-by"),)},
        {"connections": (PackConnection(source_ref="a", target_ref="b", type_ref="nope"),)},
        {"connections": (PackConnection(source_ref="a", target_ref="a", type_ref="signed-by"),)},
        {"item_types": (PackItemType(ref="record", slug="Record Type", label="Record"),)},
        {"item_types": (PackItemType(ref="record", slug="record", label="R"),
                        PackItemType(ref="person", slug="record", label="P"))},
        {"presets": ()},  # the schema still references the "grades" preset
    ],
)
def test_an_invalid_pack_is_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(InvalidPackError):
        _pack(**overrides)


def test_too_many_items_is_rejected() -> None:
    items = tuple(
        PackItem(ref=f"i{n}", type_ref="person", name=str(n)) for n in range(MAX_ITEMS + 1)
    )
    with pytest.raises(InvalidPackError):
        _pack(items=items, connections=())


def test_preset_refs_finds_markers_anywhere() -> None:
    assert preset_refs(_SCHEMA) == {"grades"}
    assert preset_refs(None) == set()
    assert preset_refs({"a": [{"b": {"$preset": "x"}}]}) == {"x"}


def test_resolve_preset_refs_swaps_markers_for_ids() -> None:
    resolved = resolve_preset_refs(_SCHEMA, {"grades": "abc"})
    assert resolved["properties"]["condition"]["x-menagerist"]["list"] == "abc"
    assert _SCHEMA["properties"]["condition"]["x-menagerist"]["list"] == _LIST  # not mutated


def test_resolve_preset_refs_rejects_an_unknown_marker() -> None:
    with pytest.raises(InvalidPackError):
        resolve_preset_refs(_SCHEMA, {})
```

- [ ] **Step 3: Run to confirm it fails**

Run: `cd backend && ../.venv/bin/python -m pytest tests/modules/examples/domain/test_pack.py -q`
Expected: FAIL (`ModuleNotFoundError: app.modules.examples.domain.pack`).

- [ ] **Step 4: Write `domain/pack.py`**

```python
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from app.modules.examples.domain.errors import InvalidPackError
from app.shared_kernel.slug import slugify

PRESET_MARKER = "$preset"
MAX_PRESETS = 50
MAX_TYPES = 50
MAX_ITEMS = 500
MAX_CONNECTIONS = 2000

_REF = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def preset_refs(value: Any) -> set[str]:
    """Return the preset refs named by `{"$preset": ref}` markers anywhere in `value`."""
    if isinstance(value, dict):
        if set(value) == {PRESET_MARKER} and isinstance(value[PRESET_MARKER], str):
            return {value[PRESET_MARKER]}
        return set().union(*(preset_refs(v) for v in value.values()))
    if isinstance(value, list):
        return set().union(*(preset_refs(v) for v in value))
    return set()


def resolve_preset_refs(value: Any, ids: Mapping[str, str]) -> Any:
    """Return a copy of `value` with each preset marker replaced by its id."""
    if isinstance(value, dict):
        if set(value) == {PRESET_MARKER} and isinstance(value[PRESET_MARKER], str):
            ref = value[PRESET_MARKER]
            if ref not in ids:
                raise InvalidPackError(f"unknown preset '{ref}'")
            return ids[ref]
        return {k: resolve_preset_refs(v, ids) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_preset_refs(v, ids) for v in value]
    return value


@dataclass(kw_only=True, frozen=True, eq=False)
class PackPreset:
    """A saved field, field group or choice list the pack creates."""

    ref: str
    kind: str
    label: str
    description: str | None = None
    definition: dict[str, Any] = field(default_factory=dict)


@dataclass(kw_only=True, frozen=True, eq=False)
class PackRelationshipType:
    """A relationship type (an edge type) the pack creates."""

    ref: str
    slug: str
    label: str
    reverse_label: str | None = None
    description: str | None = None
    directional: bool = True
    attributes_schema: dict[str, Any] | None = None


@dataclass(kw_only=True, frozen=True, eq=False)
class PackItemType:
    """An item type (a node type) the pack creates."""

    ref: str
    slug: str
    label: str
    description: str | None = None
    attributes_schema: dict[str, Any] | None = None


@dataclass(kw_only=True, frozen=True, eq=False)
class PackItem:
    """An item (a node) the pack creates."""

    ref: str
    type_ref: str
    name: str
    description: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    tags: tuple[str, ...] = ()
    extra_schema: dict[str, Any] | None = None


@dataclass(kw_only=True, frozen=True, eq=False)
class PackConnection:
    """A connection (an edge) between two pack items."""

    source_ref: str
    target_ref: str
    type_ref: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(kw_only=True, frozen=True, eq=False)
class PackCounts:
    """How many entities of each kind a pack holds, creates, or removed."""

    presets: int = 0
    relationship_types: int = 0
    item_types: int = 0
    items: int = 0
    connections: int = 0


@dataclass(kw_only=True, frozen=True, eq=False)
class PackSummary:
    """A catalogue entry: what the Examples page lists."""

    id: str
    name: str
    description: str
    counts: PackCounts


def _check_refs(section: str, refs: list[str]) -> None:
    for ref in refs:
        if not _REF.match(ref):
            raise InvalidPackError(f"{section} ref '{ref}' must be lowercase letters, digits and hyphens")
    if len(set(refs)) != len(refs):
        raise InvalidPackError(f"{section} refs must be unique")


@dataclass(kw_only=True, frozen=True, eq=False)
class ExamplePack:
    """A pack's content. Validates its own references on construction."""

    id: str
    presets: tuple[PackPreset, ...] = ()
    relationship_types: tuple[PackRelationshipType, ...] = ()
    item_types: tuple[PackItemType, ...] = ()
    items: tuple[PackItem, ...] = ()
    connections: tuple[PackConnection, ...] = ()

    def __post_init__(self) -> None:
        """Reject a pack whose references do not resolve or that is too large."""
        if not _REF.match(self.id):
            raise InvalidPackError(f"pack id '{self.id}' must be lowercase letters, digits and hyphens")
        limits = (
            ("presets", len(self.presets), MAX_PRESETS),
            ("relationship types", len(self.relationship_types), MAX_TYPES),
            ("item types", len(self.item_types), MAX_TYPES),
            ("items", len(self.items), MAX_ITEMS),
            ("connections", len(self.connections), MAX_CONNECTIONS),
        )
        for name, count, limit in limits:
            if count > limit:
                raise InvalidPackError(f"a pack may hold at most {limit} {name}")

        _check_refs("preset", [p.ref for p in self.presets])
        _check_refs("relationship type", [t.ref for t in self.relationship_types])
        _check_refs("item type", [t.ref for t in self.item_types])
        _check_refs("item", [i.ref for i in self.items])

        for types in (self.relationship_types, self.item_types):
            slugs = [t.slug for t in types]
            if any(slugify(s) != s or s == "" for s in slugs):
                raise InvalidPackError("type slugs must be lowercase letters, digits and hyphens")
            if len(set(slugs)) != len(slugs):
                raise InvalidPackError("type slugs must be unique within a pack")

        item_type_refs = {t.ref for t in self.item_types}
        item_refs = {i.ref for i in self.items}
        relationship_refs = {t.ref for t in self.relationship_types}
        for item in self.items:
            if item.type_ref not in item_type_refs:
                raise InvalidPackError(f"item '{item.ref}' has unknown type '{item.type_ref}'")
        for c in self.connections:
            if c.source_ref not in item_refs or c.target_ref not in item_refs:
                raise InvalidPackError("a connection joins two items that are not in the pack")
            if c.source_ref == c.target_ref:
                raise InvalidPackError("a connection cannot join an item to itself")
            if c.type_ref not in relationship_refs:
                raise InvalidPackError(f"connection has unknown type '{c.type_ref}'")

        used: set[str] = set()
        for schema in (
            *(t.attributes_schema for t in self.item_types),
            *(t.attributes_schema for t in self.relationship_types),
        ):
            used |= preset_refs(schema)
        missing = used - {p.ref for p in self.presets}
        if missing:
            raise InvalidPackError(f"unknown preset '{sorted(missing)[0]}'")

    @property
    def counts(self) -> PackCounts:
        """Counts of each section."""
        return PackCounts(
            presets=len(self.presets),
            relationship_types=len(self.relationship_types),
            item_types=len(self.item_types),
            items=len(self.items),
            connections=len(self.connections),
        )
```

- [ ] **Step 5: Run to confirm it passes**

Run: `cd backend && ../.venv/bin/python -m pytest tests/modules/examples/domain/test_pack.py -q`
Expected: PASS.

### 1.2c Installation

- [ ] **Step 6: Write the failing tests** `tests/modules/examples/domain/test_installation.py`

```python
import uuid

import pytest

from app.modules.examples.domain.errors import InvalidInstallationStateError
from app.modules.examples.domain.installation import (
    EntityKind,
    Installation,
    InstallationStatus,
    Outcome,
)


def _started() -> Installation:
    return Installation.start("demo")


def _record(installation: Installation, ref: str = "a") -> uuid.UUID:
    entity_id = uuid.uuid7()
    installation.record(EntityKind.ITEM, ref, ref.upper(), entity_id, "hash")
    return entity_id


def test_start_creates_an_installing_installation() -> None:
    installation = _started()
    assert installation.status is InstallationStatus.INSTALLING
    assert installation.is_active
    assert installation.entities == []


def test_record_adds_an_owned_entity_and_touches() -> None:
    installation = _started()
    before = installation.updated_at
    entity_id = _record(installation)
    assert [r.entity_id for r in installation.owned()] == [entity_id]
    assert installation.updated_at >= before


def test_owned_can_be_filtered_by_kind() -> None:
    installation = _started()
    _record(installation)
    assert installation.owned(EntityKind.PRESET) == []
    assert len(installation.owned(EntityKind.ITEM)) == 1


def test_mark_installed_sets_the_time() -> None:
    installation = _started()
    installation.mark_installed()
    assert installation.status is InstallationStatus.INSTALLED
    assert installation.installed_at is not None
    assert installation.is_active


def test_record_is_only_allowed_while_installing() -> None:
    installation = _started()
    installation.mark_installed()
    with pytest.raises(InvalidInstallationStateError):
        _record(installation)


def test_mark_installed_twice_is_rejected() -> None:
    installation = _started()
    installation.mark_installed()
    with pytest.raises(InvalidInstallationStateError):
        installation.mark_installed()


def test_settle_marks_an_owned_entity_removed_or_kept() -> None:
    installation = _started()
    first = _record(installation, "a")
    second = _record(installation, "b")
    installation.settle(first, Outcome.REMOVED)
    installation.settle(second, Outcome.KEPT, "edited")
    kept = next(r for r in installation.entities if r.entity_id == second)
    assert kept.outcome is Outcome.KEPT and kept.reason == "edited"
    assert installation.owned() == []


def test_settle_rejects_an_unknown_or_already_settled_entity() -> None:
    installation = _started()
    entity_id = _record(installation)
    with pytest.raises(InvalidInstallationStateError):
        installation.settle(uuid.uuid7(), Outcome.REMOVED)
    installation.settle(entity_id, Outcome.REMOVED)
    with pytest.raises(InvalidInstallationStateError):
        installation.settle(entity_id, Outcome.REMOVED)


def test_settle_rejects_the_owned_outcome() -> None:
    installation = _started()
    entity_id = _record(installation)
    with pytest.raises(InvalidInstallationStateError):
        installation.settle(entity_id, Outcome.OWNED)


def test_mark_failed_needs_nothing_left_owned() -> None:
    installation = _started()
    entity_id = _record(installation)
    with pytest.raises(InvalidInstallationStateError):
        installation.mark_failed()
    installation.settle(entity_id, Outcome.REMOVED)
    installation.mark_failed()
    assert installation.status is InstallationStatus.FAILED
    assert not installation.is_active


def test_mark_removed_needs_nothing_left_owned() -> None:
    installation = _started()
    installation.mark_installed()
    installation.mark_removed()
    assert installation.status is InstallationStatus.REMOVED
    assert installation.removed_at is not None


def test_mark_removed_is_rejected_while_something_is_owned() -> None:
    installation = _started()
    _record(installation)
    with pytest.raises(InvalidInstallationStateError):
        installation.mark_removed()


def test_removed_and_failed_installations_cannot_change_again() -> None:
    installation = _started()
    installation.mark_failed()
    with pytest.raises(InvalidInstallationStateError):
        installation.mark_installed()
    with pytest.raises(InvalidInstallationStateError):
        installation.mark_removed()
```

- [ ] **Step 7: Run to confirm it fails** (`ModuleNotFoundError`), same command pattern with `test_installation.py`.

- [ ] **Step 8: Write `domain/installation.py`**

```python
import uuid
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum

from app.modules.examples.domain.errors import InvalidInstallationStateError
from app.shared_kernel.mixins import Identifiable, Timestamped


class InstallationStatus(StrEnum):
    """Where an installation is in its life."""

    INSTALLING = "installing"
    INSTALLED = "installed"
    REMOVED = "removed"
    FAILED = "failed"


class EntityKind(StrEnum):
    """What kind of entity an installation created."""

    PRESET = "preset"
    RELATIONSHIP_TYPE = "relationship_type"
    ITEM_TYPE = "item_type"
    ITEM = "item"
    CONNECTION = "connection"


class Outcome(StrEnum):
    """Who owns an entity now."""

    OWNED = "owned"
    REMOVED = "removed"
    KEPT = "kept"


# The reverse of install order: a thing goes before whatever it depends on.
REMOVAL_ORDER = (
    EntityKind.CONNECTION,
    EntityKind.ITEM,
    EntityKind.ITEM_TYPE,
    EntityKind.RELATIONSHIP_TYPE,
    EntityKind.PRESET,
)


@dataclass(kw_only=True, frozen=True, eq=False)
class EntityRecord:
    """One entity an installation created."""

    kind: EntityKind
    ref: str
    label: str
    entity_id: uuid.UUID
    content_hash: str
    outcome: Outcome = Outcome.OWNED
    reason: str | None = None


@dataclass(kw_only=True, eq=False)
class Installation(Identifiable, Timestamped):
    """The record of one pack being installed, and what became of its entities."""

    pack_id: str
    status: InstallationStatus
    entities: list[EntityRecord] = field(default_factory=list)
    installed_at: datetime | None = None
    removed_at: datetime | None = None

    @classmethod
    def start(cls, pack_id: str) -> Installation:
        """Begin an installation, generating its id and timestamps."""
        now = datetime.now(UTC)
        return cls(
            id=uuid.uuid7(),
            pack_id=pack_id,
            status=InstallationStatus.INSTALLING,
            created_at=now,
            updated_at=now,
        )

    @property
    def is_active(self) -> bool:
        """Whether this installation blocks a new install of the same pack."""
        return self.status in (InstallationStatus.INSTALLING, InstallationStatus.INSTALLED)

    def owned(self, kind: EntityKind | None = None) -> list[EntityRecord]:
        """Return the entities still owned by the pack, optionally of one kind."""
        return [
            r
            for r in self.entities
            if r.outcome is Outcome.OWNED and (kind is None or r.kind is kind)
        ]

    def record(
        self, kind: EntityKind, ref: str, label: str, entity_id: uuid.UUID, content_hash: str
    ) -> None:
        """Record an entity the pack just created."""
        self._require(InstallationStatus.INSTALLING)
        self.entities.append(
            EntityRecord(
                kind=kind, ref=ref, label=label, entity_id=entity_id, content_hash=content_hash
            )
        )
        self.touch()

    def settle(self, entity_id: uuid.UUID, outcome: Outcome, reason: str | None = None) -> None:
        """Mark an owned entity as removed, or kept (and so no longer the pack's)."""
        if outcome is Outcome.OWNED:
            raise InvalidInstallationStateError("an entity can only be settled as removed or kept")
        for index, record in enumerate(self.entities):
            if record.entity_id == entity_id and record.outcome is Outcome.OWNED:
                self.entities[index] = replace(record, outcome=outcome, reason=reason)
                self.touch()
                return
        raise InvalidInstallationStateError(f"no owned entity {entity_id} to settle")

    def mark_installed(self) -> None:
        """The install finished."""
        self._require(InstallationStatus.INSTALLING)
        self.status = InstallationStatus.INSTALLED
        self.installed_at = datetime.now(UTC)
        self.touch()

    def mark_failed(self) -> None:
        """The install failed and everything it created has been dealt with."""
        self._require(InstallationStatus.INSTALLING)
        self._require_nothing_owned()
        self.status = InstallationStatus.FAILED
        self.touch()

    def mark_removed(self) -> None:
        """The pack was removed and everything it created has been dealt with."""
        self._require(InstallationStatus.INSTALLING, InstallationStatus.INSTALLED)
        self._require_nothing_owned()
        self.status = InstallationStatus.REMOVED
        self.removed_at = datetime.now(UTC)
        self.touch()

    def _require(self, *allowed: InstallationStatus) -> None:
        if self.status not in allowed:
            raise InvalidInstallationStateError(
                f"installation is {self.status}, which does not allow this"
            )

    def _require_nothing_owned(self) -> None:
        if self.owned():
            raise InvalidInstallationStateError("the pack still owns entities")
```

- [ ] **Step 9: Run to confirm it passes**, then run `poe lint-backend` and `poe typecheck-backend` for the new files.

### 1.2d Removal rule

- [ ] **Step 10: Write the truth-table test** `tests/modules/examples/domain/test_removal.py`

```python
import uuid

import pytest

from app.modules.examples.domain.errors import InvalidInstallationStateError
from app.modules.examples.domain.installation import EntityKind, EntityRecord, Outcome
from app.modules.examples.domain.removal import (
    KEEP_EDITED,
    KEEP_IN_USE,
    KEEP_USER_DATA,
    Action,
    decide_removal,
)


def _record(outcome: Outcome = Outcome.OWNED) -> EntityRecord:
    return EntityRecord(
        kind=EntityKind.ITEM, ref="a", label="A", entity_id=uuid.uuid7(),
        content_hash="h1", outcome=outcome,
    )


@pytest.mark.parametrize(
    ("current", "user_data", "in_use", "action", "reason"),
    [
        (None, False, False, Action.ALREADY_GONE, None),
        (None, True, True, Action.ALREADY_GONE, None),
        ("h2", False, False, Action.KEEP, KEEP_EDITED),
        ("h2", True, True, Action.KEEP, KEEP_EDITED),
        ("h1", True, True, Action.KEEP, KEEP_USER_DATA),
        ("h1", True, False, Action.KEEP, KEEP_USER_DATA),
        ("h1", False, True, Action.KEEP, KEEP_IN_USE),
        ("h1", False, False, Action.REMOVE, None),
    ],
)
def test_truth_table(
    current: str | None, user_data: bool, in_use: bool, action: Action, reason: str | None
) -> None:
    decision = decide_removal(
        _record(), current, has_user_data=user_data, still_in_use=in_use
    )
    assert (decision.action, decision.reason) == (action, reason)


@pytest.mark.parametrize("outcome", [Outcome.REMOVED, Outcome.KEPT])
def test_a_settled_record_is_never_decided_again(outcome: Outcome) -> None:
    with pytest.raises(InvalidInstallationStateError):
        decide_removal(_record(outcome), "h1", has_user_data=False, still_in_use=False)
```

- [ ] **Step 11: Run to confirm it fails**, then write `domain/removal.py`:

```python
from dataclasses import dataclass
from enum import StrEnum

from app.modules.examples.domain.errors import InvalidInstallationStateError
from app.modules.examples.domain.installation import EntityRecord, Outcome

KEEP_EDITED = "edited"
KEEP_USER_DATA = "has your connections or files"
KEEP_IN_USE = "still in use"


class Action(StrEnum):
    """What to do with one owned entity on removal."""

    REMOVE = "remove"
    KEEP = "keep"
    ALREADY_GONE = "already_gone"


@dataclass(kw_only=True, frozen=True, eq=False)
class RemovalDecision:
    """The verdict for one entity, with the reason when it is kept."""

    action: Action
    reason: str | None = None


def decide_removal(
    record: EntityRecord,
    current_hash: str | None,
    *,
    has_user_data: bool,
    still_in_use: bool,
) -> RemovalDecision:
    """Decide whether an owned entity may be removed.

    `current_hash` is the hash of the entity's content now, or `None` if it is gone.
    Precedence when several reasons apply: edited, then user data, then in use.
    """
    if record.outcome is not Outcome.OWNED:
        raise InvalidInstallationStateError("only owned entities are decided")
    if current_hash is None:
        return RemovalDecision(action=Action.ALREADY_GONE)
    if current_hash != record.content_hash:
        return RemovalDecision(action=Action.KEEP, reason=KEEP_EDITED)
    if has_user_data:
        return RemovalDecision(action=Action.KEEP, reason=KEEP_USER_DATA)
    if still_in_use:
        return RemovalDecision(action=Action.KEEP, reason=KEEP_IN_USE)
    return RemovalDecision(action=Action.REMOVE)
```

- [ ] **Step 12: Run all domain tests with coverage**

Run: `cd backend && ../.venv/bin/python -m pytest tests/modules/examples/domain -q --cov=app.modules.examples.domain --cov-report=term-missing`
Expected: PASS, domain 100%. Add a test for any uncovered line (typically `SlugClashError` attributes and `InstallFailedError`; add `tests/modules/examples/domain/test_errors.py` asserting `SlugClashError(kind="an item type", slug="record")` has the message "You already have an item type called 'record'. Rename or remove it, then try again." and `.kind` and `.slug`, and that `InstallFailedError` is not a `DomainError`).

- [ ] **Step 13: Checkpoint.** `poe format`, `poe lint-backend`, `poe typecheck-backend`. Leave uncommitted.

---

## Task 1.3: Ports and in-memory adapters

**Files:**
- Create: `ports/pack_catalogue.py`, `ports/installation_repository.py`, `ports/unit_of_work.py`, `ports/pack_targets.py`, `adapters/persistence/in_memory_installation_repository.py`, `adapters/platform/in_memory_pack_catalogue.py`
- Test: `tests/modules/examples/adapters/test_in_memory_installation_repository.py`, `test_in_memory_pack_catalogue.py`

**Interfaces:**
- Consumes: Task 1.2 types.
- Produces: `PackCatalogue`, `InstallationRepository`, `ExampleRepos`, `ExampleUnitOfWork`, `Created`, `Inspection`, `PresetOutcome`, `RemoveResult`, `PresetTarget`, `GraphTarget`, `InMemoryInstallationRepository`, `InMemoryPackCatalogue`.

- [ ] **Step 1: Write the ports**

`ports/pack_catalogue.py`:

```python
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.modules.examples.domain.pack import ExamplePack, PackSummary


class PackCatalogue(Protocol):
    """The packs this server ships."""

    async def list_packs(self) -> list[PackSummary]:
        """Return every shipped pack's summary, in catalogue order."""
        ...

    async def get(self, pack_id: str) -> ExamplePack | None:
        """Return the pack with `pack_id`, or `None` if the catalogue has no such pack."""
        ...
```

`ports/installation_repository.py`:

```python
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import uuid

    from app.modules.examples.domain.installation import Installation


class InstallationRepository(Protocol):
    """Access to installation records, independent of storage backend."""

    async def add(self, installation: Installation) -> None:
        """Add a new installation."""
        ...

    async def save(self, installation: Installation) -> None:
        """Persist changes to an existing installation."""
        ...

    async def get(self, installation_id: uuid.UUID) -> Installation | None:
        """Return the installation with `installation_id`, or `None`."""
        ...

    async def get_active_for_pack(self, pack_id: str) -> Installation | None:
        """Return the installing or installed installation of `pack_id`, if any."""
        ...

    async def list_active(self) -> list[Installation]:
        """Return every installing or installed installation."""
        ...
```

`ports/unit_of_work.py`:

```python
from dataclasses import dataclass

from app.modules.examples.ports.installation_repository import InstallationRepository
from app.shared_kernel.unit_of_work import UnitOfWork


@dataclass(kw_only=True)
class ExampleRepos:
    """The examples module's repository bundle."""

    installations: InstallationRepository


ExampleUnitOfWork = UnitOfWork[ExampleRepos]
```

`ports/pack_targets.py`:

```python
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from app.modules.examples.domain.installation import EntityKind
from app.modules.examples.domain.pack import (
    PackConnection,
    PackItem,
    PackItemType,
    PackPreset,
    PackRelationshipType,
)


@dataclass(kw_only=True, frozen=True, eq=False)
class Created:
    """An entity a target created. `content` is what the pack defines, as stored."""

    entity_id: uuid.UUID
    content: dict[str, Any]


@dataclass(kw_only=True, frozen=True, eq=False)
class Inspection:
    """An entity as it is now. `content` is comparable with what `Created` returned."""

    content: dict[str, Any]
    has_user_data: bool = False
    still_in_use: bool = False


@dataclass(kw_only=True, frozen=True, eq=False)
class PresetOutcome:
    """One pack preset, resolved to a real preset. `created` is false if it already existed."""

    ref: str
    entity_id: uuid.UUID
    created: bool
    content: dict[str, Any]


class RemoveResult(Enum):
    """What happened when a target was asked to remove an entity."""

    REMOVED = "removed"
    ALREADY_GONE = "already_gone"
    REFUSED_IN_USE = "refused_in_use"


class PresetTarget(Protocol):
    """Creates, inspects and removes presets, owned by another module."""

    async def ensure(self, presets: Sequence[PackPreset]) -> list[PresetOutcome]:
        """Create each preset unless an identical one exists; return one outcome each, in order."""
        ...

    async def inspect(self, preset_id: uuid.UUID) -> Inspection | None:
        """Return the preset as it is now, or `None` if it is gone."""
        ...

    async def remove(self, preset_id: uuid.UUID) -> RemoveResult:
        """Remove the preset, or report that it is gone or still referenced."""
        ...


class GraphTarget(Protocol):
    """Creates, inspects and removes types, items and connections, owned by `graph`."""

    async def slug_taken(self, kind: EntityKind, slug: str) -> bool:
        """Whether a live item type or relationship type already has `slug`."""
        ...

    async def create_relationship_type(
        self, spec: PackRelationshipType, presets: Mapping[str, uuid.UUID]
    ) -> Created:
        """Create the relationship type, resolving `$preset` markers with `presets`."""
        ...

    async def create_item_type(
        self, spec: PackItemType, presets: Mapping[str, uuid.UUID]
    ) -> Created:
        """Create the item type, resolving `$preset` markers with `presets`."""
        ...

    async def create_item(self, spec: PackItem, *, type_slug: str) -> Created:
        """Create the item under the item type `type_slug`."""
        ...

    async def create_connection(
        self,
        spec: PackConnection,
        *,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
        type_slug: str,
    ) -> Created:
        """Create the connection between two created items."""
        ...

    async def inspect(self, kind: EntityKind, entity_id: uuid.UUID) -> Inspection | None:
        """Return the entity as it is now, or `None` if it is gone."""
        ...

    async def remove(self, kind: EntityKind, entity_id: uuid.UUID) -> RemoveResult:
        """Remove the entity, or report that it is gone or still in use."""
        ...
```

- [ ] **Step 2: Write the failing adapter tests** `tests/modules/examples/adapters/test_in_memory_installation_repository.py`:

```python
from app.modules.examples.adapters.persistence.in_memory_installation_repository import (
    InMemoryInstallationRepository,
)
from app.modules.examples.domain.installation import Installation


async def test_add_get_and_save_round_trip() -> None:
    repo = InMemoryInstallationRepository()
    installation = Installation.start("demo")
    await repo.add(installation)
    assert await repo.get(installation.id) is installation
    installation.mark_installed()
    await repo.save(installation)
    assert (await repo.get(installation.id)).status.value == "installed"  # type: ignore[union-attr]


async def test_get_returns_none_for_an_unknown_id() -> None:
    import uuid

    assert await InMemoryInstallationRepository().get(uuid.uuid7()) is None


async def test_active_lookup_ignores_removed_and_failed() -> None:
    repo = InMemoryInstallationRepository()
    removed = Installation.start("demo")
    removed.mark_removed()
    failed = Installation.start("demo")
    failed.mark_failed()
    live = Installation.start("demo")
    for i in (removed, failed, live):
        await repo.add(i)

    assert await repo.get_active_for_pack("demo") is live
    assert await repo.get_active_for_pack("other") is None
    assert await repo.list_active() == [live]
```

and `test_in_memory_pack_catalogue.py`:

```python
from app.modules.examples.adapters.platform.in_memory_pack_catalogue import (
    InMemoryPackCatalogue,
)
from app.modules.examples.domain.pack import ExamplePack, PackItem, PackItemType


def _pack(pack_id: str) -> ExamplePack:
    return ExamplePack(
        id=pack_id,
        item_types=(PackItemType(ref="thing", slug="thing", label="Thing"),),
        items=(PackItem(ref="a", type_ref="thing", name="A"),),
    )


async def test_lists_in_insertion_order_with_counts() -> None:
    catalogue = InMemoryPackCatalogue()
    catalogue.add(_pack("one"), name="One", description="First")
    catalogue.add(_pack("two"), name="Two", description="Second")

    summaries = await catalogue.list_packs()

    assert [s.id for s in summaries] == ["one", "two"]
    assert summaries[0].name == "One" and summaries[0].counts.items == 1


async def test_get_returns_the_pack_or_none() -> None:
    catalogue = InMemoryPackCatalogue()
    pack = _pack("one")
    catalogue.add(pack, name="One", description="First")

    assert await catalogue.get("one") is pack
    assert await catalogue.get("missing") is None
```

- [ ] **Step 3: Run to confirm both fail** (`ModuleNotFoundError`).

- [ ] **Step 4: Write the adapters**

`adapters/persistence/in_memory_installation_repository.py`:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid

    from app.modules.examples.domain.installation import Installation


class InMemoryInstallationRepository:
    """Dict-backed `InstallationRepository` for tests."""

    def __init__(self) -> None:
        self._installations: dict[uuid.UUID, Installation] = {}

    async def add(self, installation: Installation) -> None:
        """Add a new installation."""
        self._installations[installation.id] = installation

    async def save(self, installation: Installation) -> None:
        """Persist changes to an existing installation."""
        self._installations[installation.id] = installation

    async def get(self, installation_id: uuid.UUID) -> Installation | None:
        """Return the installation with `installation_id`, or `None`."""
        return self._installations.get(installation_id)

    async def get_active_for_pack(self, pack_id: str) -> Installation | None:
        """Return the installing or installed installation of `pack_id`, if any."""
        return next(
            (i for i in self._installations.values() if i.pack_id == pack_id and i.is_active),
            None,
        )

    async def list_active(self) -> list[Installation]:
        """Return every installing or installed installation, oldest first."""
        return sorted(
            (i for i in self._installations.values() if i.is_active), key=lambda i: i.id
        )
```

`adapters/platform/in_memory_pack_catalogue.py`:

```python
from app.modules.examples.domain.pack import ExamplePack, PackSummary


class InMemoryPackCatalogue:
    """A catalogue built in code, for tests."""

    def __init__(self) -> None:
        self._entries: dict[str, tuple[str, str, ExamplePack]] = {}

    def add(self, pack: ExamplePack, *, name: str, description: str) -> None:
        """Add a pack under its id."""
        self._entries[pack.id] = (name, description, pack)

    async def list_packs(self) -> list[PackSummary]:
        """Return every pack's summary, in insertion order."""
        return [
            PackSummary(id=pack.id, name=name, description=description, counts=pack.counts)
            for name, description, pack in self._entries.values()
        ]

    async def get(self, pack_id: str) -> ExamplePack | None:
        """Return the pack with `pack_id`, or `None`."""
        entry = self._entries.get(pack_id)
        return entry[2] if entry else None
```

- [ ] **Step 5: Run to confirm they pass.** Run `poe lint-backend`, `poe typecheck-backend`.

- [ ] **Step 6: Checkpoint.** Leave uncommitted.

---

## Task 1.4: `ImportPresets` returns ids (presets module)

**Files:**
- Modify: `backend/src/app/modules/presets/application/import_presets.py`
- Test: `backend/tests/modules/presets/application/test_preset_use_cases.py` (add), or a new `test_import_presets_result.py` beside it

**Interfaces:**
- Produces: `ImportedPreset(id: uuid.UUID, created: bool)` and `ImportPresetsResult.items: list[ImportedPreset]` in pack order, including repeats (their existing id, `created=False`). `created` and `skipped` stay.

- [ ] **Step 1: Write the failing test**

```python
async def test_import_reports_an_id_for_every_item_including_repeats() -> None:
    repos = PresetRepos(presets=InMemoryPresetRepository())
    uow = create_in_memory_preset_uow(repos)
    existing = await CreatePreset(uow).handle(
        CreatePresetCommand(kind="choice_list", label="Grades", definition={"options": ["Mint"]}),
        SYSTEM_ACTOR,
    )
    items = [
        {"kind": "choice_list", "label": "Grades", "description": None,
         "definition": {"options": ["Mint"]}},
        {"kind": "choice_list", "label": "Formats", "description": None,
         "definition": {"options": ["LP"]}},
    ]

    result = await ImportPresets(uow).handle(
        ImportPresetsCommand(pack_format=PACK_FORMAT, pack_version=PACK_VERSION, items=items),
        SYSTEM_ACTOR,
    )

    assert (result.created, result.skipped) == (1, 1)
    assert result.items[0].id == existing.id and result.items[0].created is False
    assert result.items[1].created is True
    assert await repos.presets.get(result.items[1].id) is not None
```

(Match the imports and helper style of the neighbouring tests in that file; `PACK_FORMAT` and `PACK_VERSION` come from `app.modules.presets.application.pack`.)

- [ ] **Step 2: Run to confirm it fails** (`AttributeError: 'ImportPresetsResult' object has no attribute 'items'`).

- [ ] **Step 3: Implement.** In `import_presets.py`:
  - add `@dataclass(kw_only=True) class ImportedPreset: id: uuid.UUID; created: bool` (move `import uuid` out of `TYPE_CHECKING` since a dataclass annotation is evaluated lazily, but keep it consistent with the file: a dataclass field annotation under `TYPE_CHECKING` is fine because annotations are strings at runtime only if `from __future__` is used; this repo forbids that, so import `uuid` at runtime);
  - add `items: list[ImportedPreset] = field(default_factory=list)` to `ImportPresetsResult`;
  - change `_existing_hashes` to return `dict[str, uuid.UUID]` (hash to id), seed `seen` from it, and when an item is skipped append `ImportedPreset(id=seen[digest], created=False)`; when created append `ImportedPreset(id=preset.id, created=True)` and remember `seen[digest] = preset.id`;
  - return `ImportPresetsResult(created=created, skipped=skipped, items=items)`.

- [ ] **Step 4: Run** `tests/modules/presets` and confirm everything passes, including the router tests (the response model is unchanged, so they must not need edits). Then `poe lint-backend`, `poe typecheck-backend`; application coverage for the file stays 100%.

- [ ] **Step 5: Checkpoint.**

---

## Task 1.5: Target adapters and the shared test world

**Files:**
- Create: `backend/src/app/entrypoints/api/shared/example_targets.py`
- Create: `backend/tests/modules/examples/support.py`
- Test: `backend/tests/entrypoints/api/shared/test_example_targets.py`

**Interfaces:**
- Consumes: Task 1.3 ports; Task 1.4 `ImportPresetsResult.items`; graph use cases `CreateNodeType`, `CreateEdgeType`, `CreateNode`, `CreateEdge`, `DeleteNode`, `DeleteEdge`, `DeleteNodeType`, `DeleteEdgeType`; presets use cases `ImportPresets`, `DeletePreset`; `PresetChoiceListSource` and `GraphPresetUsage` (same package).
- Produces:
  - `content_hash`-ready content dicts via private helpers (`_preset_content`, `_edge_type_content`, `_node_type_content`, `_node_content`, `_edge_content`);
  - `PresetStores(uow, read, usage)` and `GraphStores(uow, read, media, choice_lists)` dataclasses of factories; `in_memory_preset_stores(...)` and `in_memory_graph_stores(...)` builders; `build_preset_stores(session_factory)` and `build_graph_stores(session_factory)` for production;
  - `PresetPackTarget(stores)` and `GraphPackTarget(stores)`;
  - dependency providers `get_preset_pack_target`, `get_graph_pack_target` for the API.

- [ ] **Step 1: Write the shared test builders** `tests/modules/examples/support.py`

```python
from dataclasses import dataclass

from app.entrypoints.api.shared.example_targets import (
    GraphPackTarget,
    PresetPackTarget,
    in_memory_graph_stores,
    in_memory_preset_stores,
)
from app.modules.examples.adapters.persistence.in_memory_installation_repository import (
    InMemoryInstallationRepository,
)
from app.modules.examples.adapters.platform.in_memory_pack_catalogue import (
    InMemoryPackCatalogue,
)
from app.modules.examples.domain.pack import (
    ExamplePack,
    PackConnection,
    PackItem,
    PackItemType,
    PackPreset,
    PackRelationshipType,
)
from app.modules.examples.ports.unit_of_work import ExampleRepos, ExampleUnitOfWork
from app.modules.graph.adapters.persistence.in_memory_edge_repository import InMemoryEdgeRepository
from app.modules.graph.adapters.persistence.in_memory_edge_type_repository import InMemoryEdgeTypeRepository
from app.modules.graph.adapters.persistence.in_memory_node_repository import InMemoryNodeRepository
from app.modules.graph.adapters.persistence.in_memory_node_type_repository import InMemoryNodeTypeRepository
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.modules.media.adapters.persistence.in_memory_media_asset_repository import InMemoryMediaAssetRepository
from app.modules.media.adapters.persistence.in_memory_media_attachment_repository import InMemoryMediaAttachmentRepository
from app.modules.media.ports.unit_of_work import MediaRepos
from app.modules.presets.adapters.persistence.in_memory_preset_repository import InMemoryPresetRepository
from app.modules.presets.ports.unit_of_work import PresetRepos
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork

_LIST = {"$preset": "grades"}
_RECORD_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "condition": {
            "title": "Condition",
            "type": "string",
            "x-menagerist": {"kind": "choice", "list": _LIST},
        }
    },
}


def sample_pack(pack_id: str = "demo") -> ExamplePack:
    """One preset, two item types, one relationship type, two items, one connection."""
    return ExamplePack(
        id=pack_id,
        presets=(
            PackPreset(ref="grades", kind="choice_list", label=f"{pack_id} grades",
                       definition={"options": ["Mint", "Good"]}),
        ),
        relationship_types=(
            PackRelationshipType(ref="signed-by", slug=f"{pack_id}-signed-by",
                                 label="Signed by", reverse_label="Signed"),
        ),
        item_types=(
            PackItemType(ref="record", slug=f"{pack_id}-record", label="Record",
                         attributes_schema=_RECORD_SCHEMA),
            PackItemType(ref="person", slug=f"{pack_id}-person", label="Person"),
        ),
        items=(
            PackItem(ref="blue", type_ref="record", name="Blue",
                     attributes={"condition": "Mint"}, tags=("jazz",)),
            PackItem(ref="ada", type_ref="person", name="Ada"),
        ),
        connections=(PackConnection(source_ref="blue", target_ref="ada", type_ref="signed-by"),),
    )


@dataclass(kw_only=True)
class World:
    """Everything an application test needs, all in memory."""

    graph_repos: GraphRepos
    preset_repos: PresetRepos
    media_repos: MediaRepos
    installations: InMemoryInstallationRepository
    catalogue: InMemoryPackCatalogue
    uow: ExampleUnitOfWork
    presets: PresetPackTarget
    graph: GraphPackTarget


def make_world(*packs: ExamplePack) -> World:
    """Build a world with `packs` in the catalogue."""
    graph_repos = GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )
    preset_repos = PresetRepos(presets=InMemoryPresetRepository())
    media_repos = MediaRepos(
        assets=InMemoryMediaAssetRepository(), attachments=InMemoryMediaAttachmentRepository()
    )
    installations = InMemoryInstallationRepository()
    catalogue = InMemoryPackCatalogue()
    for pack in packs or (sample_pack(),):
        catalogue.add(pack, name=pack.id.title(), description=f"{pack.id} examples")
    return World(
        graph_repos=graph_repos,
        preset_repos=preset_repos,
        media_repos=media_repos,
        installations=installations,
        catalogue=catalogue,
        uow=InMemoryUnitOfWork(ExampleRepos(installations=installations)),
        presets=PresetPackTarget(in_memory_preset_stores(preset_repos, graph_repos)),
        graph=GraphPackTarget(
            in_memory_graph_stores(graph_repos, media_repos, preset_repos)
        ),
    )
```

- [ ] **Step 2: Write the failing target tests** `tests/entrypoints/api/shared/test_example_targets.py`. Cover each behaviour with a short test; the key ones in full:

```python
import pytest

from app.modules.examples.domain.installation import EntityKind
from app.modules.examples.domain.pack import PackItem, PackPreset
from app.modules.examples.ports.pack_targets import RemoveResult
from tests.modules.examples.support import make_world, sample_pack  # adjust to the repo's import style


async def _install_all(world):
    """Create every entity of the sample pack through the targets, in order."""
    pack = sample_pack()
    outcomes = await world.presets.ensure(pack.presets)
    preset_ids = {o.ref: o.entity_id for o in outcomes}
    rel = await world.graph.create_relationship_type(pack.relationship_types[0], preset_ids)
    types = [
        await world.graph.create_item_type(t, preset_ids) for t in pack.item_types
    ]
    blue = await world.graph.create_item(pack.items[0], type_slug="demo-record")
    ada = await world.graph.create_item(pack.items[1], type_slug="demo-person")
    edge = await world.graph.create_connection(
        pack.connections[0], source_id=blue.entity_id, target_id=ada.entity_id,
        type_slug="demo-signed-by",
    )
    return preset_ids, rel, types, blue, ada, edge


async def test_a_preset_that_already_exists_is_reported_as_not_created() -> None:
    world = make_world()
    first = await world.presets.ensure(sample_pack().presets)
    second = await world.presets.ensure(sample_pack().presets)

    assert first[0].created is True and second[0].created is False
    assert first[0].entity_id == second[0].entity_id


async def test_marker_in_a_schema_becomes_the_preset_id() -> None:
    world = make_world()
    preset_ids, _, types, *_ = await _install_all(world)

    prop = types[0].content["attributes_schema"]["properties"]["condition"]
    assert prop["x-menagerist"]["list"] == str(preset_ids["grades"])


async def test_inspect_reports_the_content_it_created_with() -> None:
    world = make_world()
    _, _, _, blue, *_ = await _install_all(world)

    inspection = await world.graph.inspect(EntityKind.ITEM, blue.entity_id)

    assert inspection is not None
    assert inspection.content == blue.content
    assert (inspection.has_user_data, inspection.still_in_use) == (False, False)


async def test_item_content_ignores_favourite_but_not_edits() -> None:
    world = make_world()
    _, _, _, blue, *_ = await _install_all(world)
    node = await world.graph_repos.nodes.get(blue.entity_id)
    node.favourite = True
    await world.graph_repos.nodes.save(node)
    assert (await world.graph.inspect(EntityKind.ITEM, blue.entity_id)).content == blue.content

    node.name = "Blue (mine)"
    await world.graph_repos.nodes.save(node)
    assert (await world.graph.inspect(EntityKind.ITEM, blue.entity_id)).content != blue.content


async def test_a_user_connection_counts_as_user_data() -> None:
    world = make_world()
    _, _, _, blue, ada, edge = await _install_all(world)
    await world.graph.remove(EntityKind.CONNECTION, edge.entity_id)
    assert (await world.graph.inspect(EntityKind.ITEM, blue.entity_id)).has_user_data is False

    # the user links the item to one of their own; nothing about it is pack-owned
    from app.modules.graph.domain.edge import Edge
    import uuid
    await world.graph_repos.edges.add(
        Edge.create(source_id=blue.entity_id, target_id=uuid.uuid7(), type="mine")
    )
    assert (await world.graph.inspect(EntityKind.ITEM, blue.entity_id)).has_user_data is True


async def test_an_attached_file_counts_as_user_data() -> None:
    import uuid

    from app.modules.media.domain.media_attachment import MediaAttachment

    world = make_world()
    _, _, _, blue, *_ = await _install_all(world)
    await world.media_repos.attachments.add(
        MediaAttachment.for_node(asset_id=uuid.uuid7(), node_id=blue.entity_id)
    )

    assert (await world.graph.inspect(EntityKind.ITEM, blue.entity_id)).has_user_data is True


async def test_a_type_with_live_items_is_in_use() -> None:
    world = make_world()
    _, _, types, blue, *_ = await _install_all(world)
    record_type = types[0].entity_id
    assert (await world.graph.inspect(EntityKind.ITEM_TYPE, record_type)).still_in_use is True
    await world.graph.remove(EntityKind.ITEM, blue.entity_id)
    assert (await world.graph.inspect(EntityKind.ITEM_TYPE, record_type)).still_in_use is False


async def test_relationship_type_in_use_while_a_connection_exists() -> None:
    world = make_world()
    _, rel, *_, edge = await _install_all(world)
    assert (await world.graph.inspect(EntityKind.RELATIONSHIP_TYPE, rel.entity_id)).still_in_use
    assert await world.graph.remove(EntityKind.RELATIONSHIP_TYPE, rel.entity_id) is RemoveResult.REFUSED_IN_USE
    await world.graph.remove(EntityKind.CONNECTION, edge.entity_id)
    assert await world.graph.remove(EntityKind.RELATIONSHIP_TYPE, rel.entity_id) is RemoveResult.REMOVED


async def test_remove_twice_reports_already_gone() -> None:
    world = make_world()
    _, _, _, blue, *_ = await _install_all(world)
    assert await world.graph.remove(EntityKind.ITEM, blue.entity_id) is RemoveResult.REMOVED
    assert await world.graph.remove(EntityKind.ITEM, blue.entity_id) is RemoveResult.ALREADY_GONE
    assert await world.graph.inspect(EntityKind.ITEM, blue.entity_id) is None


async def test_a_preset_a_type_references_cannot_be_removed() -> None:
    world = make_world()
    preset_ids, *_ = await _install_all(world)
    assert await world.presets.remove(preset_ids["grades"]) is RemoveResult.REFUSED_IN_USE


async def test_unknown_marker_fails_before_anything_is_created() -> None:
    world = make_world()
    pack = sample_pack()
    with pytest.raises(Exception, match="unknown preset"):
        await world.graph.create_item_type(pack.item_types[0], {})
    assert await world.graph_repos.node_types.get_by_slug("demo-record") is None


async def test_slug_taken_sees_live_types_only() -> None:
    world = make_world()
    _, _, types, *_ = await _install_all(world)
    assert await world.graph.slug_taken(EntityKind.ITEM_TYPE, "demo-record") is True
    assert await world.graph.slug_taken(EntityKind.RELATIONSHIP_TYPE, "demo-signed-by") is True
    assert await world.graph.slug_taken(EntityKind.ITEM_TYPE, "nope") is False
```

The tests change nodes through the repository directly, so no update use case is imported.

- [ ] **Step 3: Run to confirm they fail** (`ModuleNotFoundError: ...example_targets`).

- [ ] **Step 4: Write `entrypoints/api/shared/example_targets.py`**

```python
import uuid
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import Depends

from app.entrypoints.api.shared.choice_list_source import PresetChoiceListSource
from app.entrypoints.api.shared.preset_usage import GraphPresetUsage
from app.modules.examples.domain.errors import InvalidPackError
from app.modules.examples.domain.installation import EntityKind
from app.modules.examples.domain.pack import (
    PackConnection,
    PackItem,
    PackItemType,
    PackPreset,
    PackRelationshipType,
    resolve_preset_refs,
)
from app.modules.examples.ports.pack_targets import (
    Created,
    Inspection,
    PresetOutcome,
    RemoveResult,
)
from app.modules.graph.adapters.persistence.unit_of_work import (
    build_graph_repos,
    create_graph_uow,
    create_in_memory_graph_uow,
)
from app.modules.graph.application.create_edge import CreateEdge, CreateEdgeCommand
from app.modules.graph.application.create_edge_type import CreateEdgeType, CreateEdgeTypeCommand
from app.modules.graph.application.create_node import CreateNode, CreateNodeCommand
from app.modules.graph.application.create_node_type import CreateNodeType, CreateNodeTypeCommand
from app.modules.graph.application.delete_edge import DeleteEdge, DeleteEdgeCommand
from app.modules.graph.application.delete_edge_type import DeleteEdgeType, DeleteEdgeTypeCommand
from app.modules.graph.application.delete_node import DeleteNode, DeleteNodeCommand
from app.modules.graph.application.delete_node_type import DeleteNodeType, DeleteNodeTypeCommand
from app.modules.graph.domain.errors import (
    EdgeNotFoundError,
    EdgeTypeInUseError,
    EdgeTypeNotFoundError,
    NodeNotFoundError,
    NodeTypeNotFoundError,
)
from app.modules.graph.ports.unit_of_work import GraphRepos, GraphUnitOfWork
from app.modules.media.adapters.persistence.unit_of_work import build_media_repos
from app.modules.media.domain.media_attachment import AttachmentTarget
from app.modules.media.ports.unit_of_work import MediaRepos
from app.modules.presets.adapters.persistence.unit_of_work import (
    build_preset_repos,
    create_in_memory_preset_uow,
    create_preset_uow,
)
from app.modules.presets.application.delete_preset import DeletePreset, DeletePresetCommand
from app.modules.presets.application.import_presets import ImportPresets, ImportPresetsCommand
from app.modules.presets.application.pack import PACK_FORMAT, PACK_VERSION
from app.modules.presets.domain.errors import (
    BuiltinPresetError,
    PresetInUseError,
    PresetNotFoundError,
)
from app.modules.presets.ports.preset_usage import PresetUsage
from app.modules.presets.ports.unit_of_work import PresetRepos, PresetUnitOfWork
from app.platform.database import get_session_factory
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.slug import slugify

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.modules.graph.ports.choice_list_source import ChoiceListSource

_PAGE = 1


# ---- stores: how the targets reach storage (sessions in production, memory in tests) ----


@dataclass(kw_only=True)
class PresetStores:
    """Factories the preset target uses; each call opens fresh storage access."""

    uow: Callable[[], PresetUnitOfWork]
    read: Callable[[], AbstractAsyncContextManager[PresetRepos]]
    usage: Callable[[], AbstractAsyncContextManager[PresetUsage]]


@dataclass(kw_only=True)
class GraphStores:
    """Factories the graph target uses; each call opens fresh storage access."""

    uow: Callable[[], GraphUnitOfWork]
    read: Callable[[], AbstractAsyncContextManager[GraphRepos]]
    media: Callable[[], AbstractAsyncContextManager[MediaRepos]]
    choice_lists: Callable[[], AbstractAsyncContextManager[ChoiceListSource]]


def in_memory_preset_stores(preset_repos: PresetRepos, graph_repos: GraphRepos) -> PresetStores:
    """Stores over in-memory repositories, for tests."""

    @asynccontextmanager
    async def read() -> AsyncIterator[PresetRepos]:
        yield preset_repos

    @asynccontextmanager
    async def usage() -> AsyncIterator[PresetUsage]:
        yield GraphPresetUsage(graph_repos)

    return PresetStores(
        uow=lambda: create_in_memory_preset_uow(preset_repos), read=read, usage=usage
    )


def in_memory_graph_stores(
    graph_repos: GraphRepos, media_repos: MediaRepos, preset_repos: PresetRepos
) -> GraphStores:
    """Stores over in-memory repositories, for tests."""

    @asynccontextmanager
    async def read() -> AsyncIterator[GraphRepos]:
        yield graph_repos

    @asynccontextmanager
    async def media() -> AsyncIterator[MediaRepos]:
        yield media_repos

    @asynccontextmanager
    async def choice_lists() -> AsyncIterator[ChoiceListSource]:
        yield PresetChoiceListSource(preset_repos)

    return GraphStores(
        uow=lambda: create_in_memory_graph_uow(graph_repos),
        read=read,
        media=media,
        choice_lists=choice_lists,
    )


def build_preset_stores(session_factory: async_sessionmaker[AsyncSession]) -> PresetStores:
    """Stores over Postgres sessions."""

    @asynccontextmanager
    async def read() -> AsyncIterator[PresetRepos]:
        async with session_factory() as session:
            yield build_preset_repos(session)

    @asynccontextmanager
    async def usage() -> AsyncIterator[PresetUsage]:
        async with session_factory() as session:
            yield GraphPresetUsage(build_graph_repos(session))

    return PresetStores(uow=lambda: create_preset_uow(session_factory), read=read, usage=usage)


def build_graph_stores(session_factory: async_sessionmaker[AsyncSession]) -> GraphStores:
    """Stores over Postgres sessions."""

    @asynccontextmanager
    async def read() -> AsyncIterator[GraphRepos]:
        async with session_factory() as session:
            yield build_graph_repos(session)

    @asynccontextmanager
    async def media() -> AsyncIterator[MediaRepos]:
        async with session_factory() as session:
            yield build_media_repos(session)

    @asynccontextmanager
    async def choice_lists() -> AsyncIterator[ChoiceListSource]:
        async with session_factory() as session:
            yield PresetChoiceListSource(build_preset_repos(session))

    return GraphStores(
        uow=lambda: create_graph_uow(session_factory),
        read=read,
        media=media,
        choice_lists=choice_lists,
    )


# ---- content: what the pack defines, read back from what was stored ----


def _preset_content(p: Any) -> dict[str, Any]:
    return {"kind": p.kind, "label": p.label, "description": p.description, "definition": p.definition}


def _node_type_content(t: Any) -> dict[str, Any]:
    return {"slug": str(t.slug), "label": t.label, "description": t.description,
            "attributes_schema": t.attributes_schema}


def _edge_type_content(t: Any) -> dict[str, Any]:
    return {"slug": str(t.slug), "label": t.label, "reverse_label": t.reverse_label,
            "description": t.description, "directional": t.directional,
            "attributes_schema": t.attributes_schema}


def _node_content(n: Any) -> dict[str, Any]:
    # `favourite` is left out on purpose: starring an example is not editing it.
    return {"name": n.name, "type": n.type, "description": n.description,
            "attributes": n.attributes, "tags": n.tags, "extra_schema": n.extra_schema}


def _edge_content(e: Any) -> dict[str, Any]:
    return {"source_id": str(e.source_id), "target_id": str(e.target_id), "type": e.type,
            "attributes": e.attributes}


def _resolved(schema: dict[str, Any] | None, presets: Mapping[str, uuid.UUID]) -> dict[str, Any] | None:
    if schema is None:
        return None
    result: dict[str, Any] = resolve_preset_refs(schema, {k: str(v) for k, v in presets.items()})
    return result


# ---- the targets ----


class PresetPackTarget:
    """Implements `PresetTarget` with the presets use cases."""

    def __init__(self, stores: PresetStores) -> None:
        self._stores = stores

    async def ensure(self, presets: Sequence[PackPreset]) -> list[PresetOutcome]:
        """Create each preset unless an identical one exists."""
        if not presets:
            return []
        command = ImportPresetsCommand(
            pack_format=PACK_FORMAT,
            pack_version=PACK_VERSION,
            items=[
                {"kind": p.kind, "label": p.label, "description": p.description,
                 "definition": p.definition}
                for p in presets
            ],
        )
        result = await ImportPresets(self._stores.uow()).handle(command, SYSTEM_ACTOR)
        outcomes: list[PresetOutcome] = []
        async with self._stores.read() as repos:
            for spec, imported in zip(presets, result.items, strict=True):
                preset = await repos.presets.get(imported.id)
                if preset is None:
                    raise InvalidPackError(f"preset '{spec.ref}' vanished while installing")
                outcomes.append(
                    PresetOutcome(ref=spec.ref, entity_id=imported.id,
                                  created=imported.created, content=_preset_content(preset))
                )
        return outcomes

    async def inspect(self, preset_id: uuid.UUID) -> Inspection | None:
        """Return the preset as it is now, or `None` if it is gone."""
        async with self._stores.read() as repos:
            preset = await repos.presets.get(preset_id)
        return None if preset is None else Inspection(content=_preset_content(preset))

    async def remove(self, preset_id: uuid.UUID) -> RemoveResult:
        """Remove the preset unless it is built in or an item type still uses it."""
        async with self._stores.usage() as usage:
            try:
                await DeletePreset(self._stores.uow(), usage).handle(
                    DeletePresetCommand(preset_id=preset_id), SYSTEM_ACTOR
                )
            except (PresetInUseError, BuiltinPresetError):
                return RemoveResult.REFUSED_IN_USE
            except PresetNotFoundError:
                return RemoveResult.ALREADY_GONE
        return RemoveResult.REMOVED


class GraphPackTarget:
    """Implements `GraphTarget` with the graph use cases."""

    def __init__(self, stores: GraphStores) -> None:
        self._stores = stores

    async def slug_taken(self, kind: EntityKind, slug: str) -> bool:
        """Whether a live type of `kind` already has `slug`."""
        async with self._stores.read() as repos:
            if kind is EntityKind.ITEM_TYPE:
                return await repos.node_types.get_by_slug(slug) is not None
            return await repos.edge_types.get_by_slug(slugify(slug)) is not None

    async def create_relationship_type(
        self, spec: PackRelationshipType, presets: Mapping[str, uuid.UUID]
    ) -> Created:
        """Create the relationship type."""
        command = CreateEdgeTypeCommand(
            slug=spec.slug, label=spec.label, reverse_label=spec.reverse_label,
            description=spec.description, directional=spec.directional,
            attributes_schema=_resolved(spec.attributes_schema, presets),
        )
        async with self._stores.choice_lists() as source:
            edge_type = await CreateEdgeType(self._stores.uow(), source).handle(command, SYSTEM_ACTOR)
        return Created(entity_id=edge_type.id, content=_edge_type_content(edge_type))

    async def create_item_type(
        self, spec: PackItemType, presets: Mapping[str, uuid.UUID]
    ) -> Created:
        """Create the item type."""
        command = CreateNodeTypeCommand(
            slug=spec.slug, label=spec.label, description=spec.description,
            attributes_schema=_resolved(spec.attributes_schema, presets),
        )
        async with self._stores.choice_lists() as source:
            node_type = await CreateNodeType(self._stores.uow(), source).handle(command, SYSTEM_ACTOR)
        return Created(entity_id=node_type.id, content=_node_type_content(node_type))

    async def create_item(self, spec: PackItem, *, type_slug: str) -> Created:
        """Create the item under `type_slug`."""
        command = CreateNodeCommand(
            name=spec.name, type=type_slug, description=spec.description,
            attributes=spec.attributes, tags=list(spec.tags), extra_schema=spec.extra_schema,
        )
        async with self._stores.choice_lists() as source:
            node = await CreateNode(self._stores.uow(), source).handle(command, SYSTEM_ACTOR)
        return Created(entity_id=node.id, content=_node_content(node))

    async def create_connection(
        self, spec: PackConnection, *, source_id: uuid.UUID, target_id: uuid.UUID, type_slug: str
    ) -> Created:
        """Create the connection."""
        command = CreateEdgeCommand(
            source_id=source_id, target_id=target_id, type=type_slug, attributes=spec.attributes
        )
        async with self._stores.choice_lists() as source:
            edge = await CreateEdge(self._stores.uow(), source).handle(command, SYSTEM_ACTOR)
        return Created(entity_id=edge.id, content=_edge_content(edge))

    async def inspect(self, kind: EntityKind, entity_id: uuid.UUID) -> Inspection | None:
        """Return the entity as it is now, or `None` if it is gone."""
        async with self._stores.read() as repos:
            if kind is EntityKind.ITEM:
                node = await repos.nodes.get(entity_id)
                if node is None:
                    return None
                touched = await repos.edges.list_for_node(node.id, after=None, limit=_PAGE)
                async with self._stores.media() as media:
                    files = await media.attachments.list_for_target(AttachmentTarget.NODE, node.id)
                return Inspection(content=_node_content(node), has_user_data=bool(touched or files))
            if kind is EntityKind.ITEM_TYPE:
                node_type = await repos.node_types.get(entity_id)
                if node_type is None:
                    return None
                items = await repos.nodes.list(after=None, limit=_PAGE, type=str(node_type.slug))
                return Inspection(content=_node_type_content(node_type), still_in_use=bool(items))
            if kind is EntityKind.RELATIONSHIP_TYPE:
                edge_type = await repos.edge_types.get(entity_id)
                if edge_type is None:
                    return None
                in_use = await repos.edges.has_edges_of_type(str(edge_type.slug))
                return Inspection(content=_edge_type_content(edge_type), still_in_use=in_use)
            edge = await repos.edges.get(entity_id)
            return None if edge is None else Inspection(content=_edge_content(edge))

    async def remove(self, kind: EntityKind, entity_id: uuid.UUID) -> RemoveResult:
        """Remove the entity through its delete use case."""
        uow = self._stores.uow()
        try:
            if kind is EntityKind.ITEM:
                await DeleteNode(uow).handle(DeleteNodeCommand(node_id=entity_id), SYSTEM_ACTOR)
            elif kind is EntityKind.ITEM_TYPE:
                await DeleteNodeType(uow).handle(
                    DeleteNodeTypeCommand(node_type_id=entity_id), SYSTEM_ACTOR
                )
            elif kind is EntityKind.RELATIONSHIP_TYPE:
                await DeleteEdgeType(uow).handle(
                    DeleteEdgeTypeCommand(edge_type_id=entity_id), SYSTEM_ACTOR
                )
            else:
                await DeleteEdge(uow).handle(DeleteEdgeCommand(edge_id=entity_id), SYSTEM_ACTOR)
        except (NodeNotFoundError, NodeTypeNotFoundError, EdgeTypeNotFoundError, EdgeNotFoundError):
            return RemoveResult.ALREADY_GONE
        except EdgeTypeInUseError:
            return RemoveResult.REFUSED_IN_USE
        return RemoveResult.REMOVED


# ---- FastAPI providers ----


def get_preset_pack_target(
    session_factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
) -> PresetPackTarget:
    """Return the preset target over Postgres."""
    return PresetPackTarget(build_preset_stores(session_factory))


def get_graph_pack_target(
    session_factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
) -> GraphPackTarget:
    """Return the graph target over Postgres."""
    return GraphPackTarget(build_graph_stores(session_factory))
```

Notes for the implementer: (1) `DeleteEdgeType` raises `EdgeTypeInUseError` only when active edges use it, which `inspect` has normally already ruled out; the mapping is a guard. (2) `DeleteNodeType` has no in-use guard (it clears `type` on live items), so the application must only ask to remove a type whose `still_in_use` is false, which `decide_removal` guarantees. (3) Typing: the `Any` helpers are deliberate to avoid importing four entity classes for annotations; tighten them if mypy asks. (4) The `FastAPI` providers sit in this file because `preset_usage.py` and `choice_list_source.py` do the same.

- [ ] **Step 5: Run the target tests**

Run: `cd backend && ../.venv/bin/python -m pytest tests/entrypoints/api/shared/test_example_targets.py -q`
Expected: PASS. Fix by reading failures, not by loosening assertions.

- [ ] **Step 6: Run** `poe format`, `poe lint-backend`, `poe typecheck-backend`; run the architecture tests (`tests/architecture`) and confirm no cycle and no `examples -> graph/presets` import.

- [ ] **Step 7: Checkpoint.**

---

## Task 1.6: Content hash and the list query

**Files:**
- Create: `application/content_hash.py`, `application/list_example_packs.py`
- Test: `tests/modules/examples/application/test_content_hash.py`, `test_list_example_packs.py`

**Interfaces:**
- Produces: `content_hash(content: Mapping[str, Any]) -> str`; `ListExamplePacksQuery`, `ExamplePackStatus(summary, installation)`, `ListExamplePacks(repos, catalogue)`.

- [ ] **Step 1: Write the failing tests**

```python
# test_content_hash.py
from app.modules.examples.application.content_hash import content_hash


def test_key_order_does_not_matter_at_any_depth() -> None:
    a = {"x": 1, "y": {"b": [1, 2], "a": None}}
    b = {"y": {"a": None, "b": [1, 2]}, "x": 1}
    assert content_hash(a) == content_hash(b)


def test_a_changed_value_changes_the_hash() -> None:
    assert content_hash({"x": 1}) != content_hash({"x": 2})
    assert content_hash({"x": [1, 2]}) != content_hash({"x": [2, 1]})


def test_unicode_is_hashed_as_written() -> None:
    assert content_hash({"x": "café 🎵"}) == content_hash({"x": "café 🎵"})


def test_the_hash_is_stable() -> None:
    # SHA-256 of the canonical JSON `{"x":1}`; if this changes, every stored hash changes
    assert content_hash({"x": 1}) == (
        "5041bf1f713df204784353e82f6a4a535931cb64f1f4b4a5aeaffcb720918b22"
    )
```

```python
# test_list_example_packs.py
from app.modules.examples.application.list_example_packs import (
    ListExamplePacks,
    ListExamplePacksQuery,
)
from app.modules.examples.domain.installation import Installation
from app.modules.examples.ports.unit_of_work import ExampleRepos
from app.shared_kernel.actor import SYSTEM_ACTOR
from tests.modules.examples.support import make_world, sample_pack


async def test_lists_each_pack_with_its_active_installation() -> None:
    world = make_world(sample_pack("one"), sample_pack("two"))
    installed = Installation.start("two")
    installed.mark_installed()
    await world.installations.add(installed)
    removed = Installation.start("one")
    removed.mark_removed()
    await world.installations.add(removed)

    result = await ListExamplePacks(
        ExampleRepos(installations=world.installations), world.catalogue
    ).handle(ListExamplePacksQuery(), SYSTEM_ACTOR)

    by_id = {s.summary.id: s for s in result}
    assert by_id["one"].installation is None  # removed does not count
    assert by_id["two"].installation is installed
    assert [s.summary.id for s in result] == ["one", "two"]


async def test_lists_nothing_for_an_empty_catalogue() -> None:
    from app.modules.examples.adapters.platform.in_memory_pack_catalogue import InMemoryPackCatalogue
    from app.modules.examples.adapters.persistence.in_memory_installation_repository import InMemoryInstallationRepository

    result = await ListExamplePacks(
        ExampleRepos(installations=InMemoryInstallationRepository()), InMemoryPackCatalogue()
    ).handle(ListExamplePacksQuery(), SYSTEM_ACTOR)
    assert result == []
```

- [ ] **Step 2: Run to confirm they fail**, then write:

`application/content_hash.py`:

```python
import hashlib
import json
from collections.abc import Mapping
from typing import Any


def content_hash(content: Mapping[str, Any]) -> str:
    """Return a stable SHA-256 of `content`, independent of key order."""
    canonical = json.dumps(
        content, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

`application/list_example_packs.py`:

```python
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.modules.examples.domain.installation import Installation
from app.modules.examples.domain.pack import PackSummary
from app.modules.examples.ports.pack_catalogue import PackCatalogue  # noqa: TC001
from app.modules.examples.ports.unit_of_work import ExampleRepos
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class ListExamplePacksQuery:
    """Request to list the shipped packs with their installation state."""


@dataclass(kw_only=True, frozen=True, eq=False)
class ExamplePackStatus:
    """A shipped pack and its active installation, if any."""

    summary: PackSummary
    installation: Installation | None


class ListExamplePacks(QueryHandler[ExampleRepos, ListExamplePacksQuery, list[ExamplePackStatus]]):
    """List the shipped packs and which of them are installed."""

    def __init__(self, repos: ExampleRepos, catalogue: PackCatalogue) -> None:
        super().__init__(repos)
        self._catalogue = catalogue

    async def handle(
        self, query: ListExamplePacksQuery, actor: Actor
    ) -> list[ExamplePackStatus]:
        """Return one status per shipped pack, in catalogue order."""
        active = {i.pack_id: i for i in await self._repos.installations.list_active()}
        return [
            ExamplePackStatus(summary=s, installation=active.get(s.id))
            for s in await self._catalogue.list_packs()
        ]
```

- [ ] **Step 3: Run to confirm they pass.**

- [ ] **Step 4: Checkpoint** (`poe format`, `poe lint-backend`, `poe typecheck-backend`; application coverage for these files 100%).

---

## Task 1.7: Install

**Files:**
- Create: `application/removal.py`, `application/install_example_pack.py`
- Test: `tests/modules/examples/application/test_install_example_pack.py` (the removal routine is exercised here and again in Task 1.8)

**Interfaces:**
- Consumes: Tasks 1.2, 1.3, 1.5 (via `support.make_world`), 1.6 `content_hash`.
- Produces: `InstallExamplePackCommand(pack_id)`, `InstallResult(pack_id, created: PackCounts)`, `InstallExamplePack(uow, catalogue, presets, graph)`; and `settle_installation(installation, *, presets, graph, persist) -> list[KeptEntity]` plus `KeptEntity(kind, ref, label, reason)`.

- [ ] **Step 1: Write the failing tests**

```python
import pytest

from app.modules.examples.application.install_example_pack import (
    InstallExamplePack, InstallExamplePackCommand,
)
from app.modules.examples.domain.errors import (
    InstallFailedError, PackAlreadyInstalledError, PackNotFoundError, SlugClashError,
)
from app.modules.examples.domain.installation import EntityKind, InstallationStatus, Outcome
from app.modules.graph.domain.node_type import NodeType
from app.shared_kernel.actor import SYSTEM_ACTOR
from tests.modules.examples.support import make_world, sample_pack


def _use_case(world) -> InstallExamplePack:
    return InstallExamplePack(world.uow, world.catalogue, world.presets, world.graph)


async def _active(world, pack_id="demo"):
    return await world.installations.get_active_for_pack(pack_id)


async def test_install_creates_everything_and_records_it() -> None:
    world = make_world()

    result = await _use_case(world).handle(InstallExamplePackCommand(pack_id="demo"), SYSTEM_ACTOR)

    counts = result.created
    assert (counts.presets, counts.relationship_types, counts.item_types) == (1, 1, 2)
    assert (counts.items, counts.connections) == (2, 1)
    installation = await _active(world)
    assert installation.status is InstallationStatus.INSTALLED
    assert len(installation.owned()) == 7
    assert await world.graph_repos.nodes.list(after=None, limit=10)  # items exist
    assert len(await world.graph_repos.node_types.list(after=None, limit=10)) == 2
    assert world.uow.committed


async def test_every_created_entity_is_hashed_for_later_comparison() -> None:
    world = make_world()
    await _use_case(world).handle(InstallExamplePackCommand(pack_id="demo"), SYSTEM_ACTOR)
    assert all(len(r.content_hash) == 64 for r in (await _active(world)).owned())


async def test_unknown_pack_is_not_found() -> None:
    with pytest.raises(PackNotFoundError):
        await _use_case(make_world()).handle(InstallExamplePackCommand(pack_id="nope"), SYSTEM_ACTOR)


async def test_installing_twice_is_a_conflict() -> None:
    world = make_world()
    await _use_case(world).handle(InstallExamplePackCommand(pack_id="demo"), SYSTEM_ACTOR)
    with pytest.raises(PackAlreadyInstalledError):
        await _use_case(world).handle(InstallExamplePackCommand(pack_id="demo"), SYSTEM_ACTOR)


@pytest.mark.parametrize(
    ("repo", "slug", "kind_phrase"),
    [("node_types", "demo-record", "an item type"), ("edge_types", "demo-signed-by", "a relationship type")],
)
async def test_a_slug_clash_creates_nothing_and_names_the_slug(repo, slug, kind_phrase) -> None:
    world = make_world()
    if repo == "node_types":
        await world.graph_repos.node_types.add(NodeType.create(slug=slug, label="Mine"))
    else:
        from app.modules.graph.domain.edge_type import EdgeType
        await world.graph_repos.edge_types.add(EdgeType.create(slug=slug, label="Mine"))

    with pytest.raises(SlugClashError) as excinfo:
        await _use_case(world).handle(InstallExamplePackCommand(pack_id="demo"), SYSTEM_ACTOR)

    assert excinfo.value.slug == slug and kind_phrase in str(excinfo.value)
    assert await _active(world) is None
    assert await world.preset_repos.presets.list(after=None, limit=10) == []
    assert await world.graph_repos.nodes.list(after=None, limit=10) == []


async def test_an_identical_existing_preset_is_used_but_not_owned() -> None:
    world = make_world()
    existing = await world.presets.ensure(sample_pack().presets)

    await _use_case(world).handle(InstallExamplePackCommand(pack_id="demo"), SYSTEM_ACTOR)

    installation = await _active(world)
    assert installation.owned(EntityKind.PRESET) == []
    assert existing[0].created is True  # created by the test, not by the pack


# The sample pack has 1 preset, 1 relationship type, 2 item types, 2 items, 1 connection,
# so these are exactly the calls that exist: a failure at the start and at the end of each step.
@pytest.mark.parametrize(
    ("method", "fail_on_call"),
    [
        ("ensure", 1),
        ("create_relationship_type", 1),
        ("create_item_type", 1),
        ("create_item_type", 2),
        ("create_item", 1),
        ("create_item", 2),
        ("create_connection", 1),
    ],
)
async def test_a_failure_rolls_everything_back(method: str, fail_on_call: int) -> None:
    world = make_world()
    target = world.presets if method == "ensure" else world.graph
    original = getattr(target, method)
    calls = 0

    async def flaky(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == fail_on_call:
            raise RuntimeError("boom")
        return await original(*args, **kwargs)

    setattr(target, method, flaky)

    with pytest.raises(InstallFailedError, match="boom"):
        await _use_case(world).handle(InstallExamplePackCommand(pack_id="demo"), SYSTEM_ACTOR)

    assert await _active(world) is None
    assert await world.graph_repos.node_types.list(after=None, limit=10) == []
    assert await world.graph_repos.nodes.list(after=None, limit=10) == []
    assert await world.graph_repos.edges.list(after=None, limit=10) == []
    assert await world.graph_repos.edge_types.list(after=None, limit=10) == []
    assert await world.preset_repos.presets.list(after=None, limit=10) == []
    assert calls == fail_on_call  # the injected failure really happened
```

```python
async def test_a_rollback_that_cannot_finish_leaves_the_install_resumable() -> None:
    world = make_world()

    async def broken_remove(*args, **kwargs):
        raise RuntimeError("database down")

    async def fail_connection(*args, **kwargs):
        raise RuntimeError("boom")

    world.graph.create_connection = fail_connection  # type: ignore[method-assign]
    world.graph.remove = broken_remove  # type: ignore[method-assign]

    with pytest.raises(InstallFailedError, match="Remove the examples"):
        await _use_case(world).handle(InstallExamplePackCommand(pack_id="demo"), SYSTEM_ACTOR)

    installation = await _active(world)
    assert installation is not None and installation.status is InstallationStatus.INSTALLING
    assert installation.owned()  # recorded, so uninstall can finish the job


async def test_an_unfinished_installation_blocks_a_second_install() -> None:
    from app.modules.examples.domain.installation import Installation

    world = make_world()
    await world.installations.add(Installation.start("demo"))  # a crash left this behind
    with pytest.raises(PackAlreadyInstalledError):
        await _use_case(world).handle(InstallExamplePackCommand(pack_id="demo"), SYSTEM_ACTOR)


async def test_reinstalling_after_removal_succeeds() -> None:
    from app.modules.examples.application.uninstall_example_pack import (
        UninstallExamplePack, UninstallExamplePackCommand,
    )

    world = make_world()
    await _use_case(world).handle(InstallExamplePackCommand(pack_id="demo"), SYSTEM_ACTOR)
    await UninstallExamplePack(world.uow, world.presets, world.graph).handle(
        UninstallExamplePackCommand(pack_id="demo"), SYSTEM_ACTOR
    )

    await _use_case(world).handle(InstallExamplePackCommand(pack_id="demo"), SYSTEM_ACTOR)

    assert (await _active(world)).status is InstallationStatus.INSTALLED
    assert len(await world.graph_repos.node_types.list(after=None, limit=10)) == 2


async def test_a_crash_between_create_and_record_is_named_by_the_next_install() -> None:
    """One orphan can be left by a crash; the slug pre-flight then names it."""
    world = make_world()
    await world.graph.create_item_type(sample_pack().item_types[1], {})  # created, never recorded
    with pytest.raises(SlugClashError, match="demo-person"):
        await _use_case(world).handle(InstallExamplePackCommand(pack_id="demo"), SYSTEM_ACTOR)
```

(The last test needs `test_reinstalling_after_removal_succeeds` to run after Task 1.8; mark it `pytest.mark.skip(reason="needs uninstall, Task 1.8")` until then and remove the skip in Task 1.8, or write Task 1.7 and 1.8 tests together and run them after 1.8.)

- [ ] **Step 2: Run to confirm they fail** (`ModuleNotFoundError`).

- [ ] **Step 3: Write `application/removal.py`**

```python
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from app.modules.examples.application.content_hash import content_hash
from app.modules.examples.domain.installation import (
    REMOVAL_ORDER,
    EntityKind,
    EntityRecord,
    Installation,
    Outcome,
)
from app.modules.examples.domain.removal import KEEP_IN_USE, Action, decide_removal
from app.modules.examples.ports.pack_targets import (
    GraphTarget,
    Inspection,
    PresetTarget,
    RemoveResult,
)

logger = structlog.get_logger()


@dataclass(kw_only=True, frozen=True, eq=False)
class KeptEntity:
    """An entity left in place on removal, and why."""

    kind: EntityKind
    ref: str
    label: str
    reason: str


async def settle_installation(
    installation: Installation,
    *,
    presets: PresetTarget,
    graph: GraphTarget,
    persist: Callable[[Installation], Awaitable[None]],
) -> list[KeptEntity]:
    """Remove or keep every owned entity, saving after each one.

    Entities are handled in `REMOVAL_ORDER`, so by the time something is inspected
    everything that depended on it has already gone or been kept. Safe to call again
    on a half-finished installation: it only touches entities still owned.
    """
    kept: list[KeptEntity] = []
    for kind in REMOVAL_ORDER:
        for record in reversed(installation.owned(kind)):
            reason = await _settle_one(installation, record, presets=presets, graph=graph)
            await persist(installation)
            if reason is not None:
                kept.append(
                    KeptEntity(kind=record.kind, ref=record.ref, label=record.label, reason=reason)
                )
    return kept


async def _settle_one(
    installation: Installation,
    record: EntityRecord,
    *,
    presets: PresetTarget,
    graph: GraphTarget,
) -> str | None:
    """Settle one record; return the reason it was kept, or `None`."""
    inspection: Inspection | None
    if record.kind is EntityKind.PRESET:
        inspection = await presets.inspect(record.entity_id)
    else:
        inspection = await graph.inspect(record.kind, record.entity_id)

    decision = decide_removal(
        record,
        None if inspection is None else content_hash(inspection.content),
        has_user_data=inspection is not None and inspection.has_user_data,
        still_in_use=inspection is not None and inspection.still_in_use,
    )
    if decision.action is Action.ALREADY_GONE:
        installation.settle(record.entity_id, Outcome.REMOVED)
        return None
    if decision.action is Action.KEEP:
        installation.settle(record.entity_id, Outcome.KEPT, decision.reason)
        return decision.reason

    if record.kind is EntityKind.PRESET:
        result = await presets.remove(record.entity_id)
    else:
        result = await graph.remove(record.kind, record.entity_id)
    if result is RemoveResult.REFUSED_IN_USE:
        installation.settle(record.entity_id, Outcome.KEPT, KEEP_IN_USE)
        return KEEP_IN_USE
    installation.settle(record.entity_id, Outcome.REMOVED)
    return None
```

- [ ] **Step 4: Write `application/install_example_pack.py`**

```python
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, NoReturn

import structlog

from app.modules.examples.application.content_hash import content_hash
from app.modules.examples.application.removal import settle_installation
from app.modules.examples.domain.errors import (
    InstallFailedError,
    PackAlreadyInstalledError,
    PackNotFoundError,
    SlugClashError,
)
from app.modules.examples.domain.installation import EntityKind, Installation
from app.modules.examples.domain.pack import ExamplePack, PackCounts
from app.modules.examples.ports.pack_catalogue import PackCatalogue  # noqa: TC001
from app.modules.examples.ports.pack_targets import GraphTarget, PresetTarget  # noqa: TC001
from app.modules.examples.ports.unit_of_work import ExampleUnitOfWork
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class InstallExamplePackCommand:
    """Request to install a shipped example pack."""

    pack_id: str


@dataclass(kw_only=True, frozen=True, eq=False)
class InstallResult:
    """What an install created."""

    pack_id: str
    created: PackCounts


@dataclass(kw_only=True)
class _Run:
    """State shared by the install steps."""

    pack: ExamplePack
    installation: Installation
    preset_ids: dict[str, uuid.UUID] = field(default_factory=dict)
    type_slugs: dict[str, str] = field(default_factory=dict)
    item_ids: dict[str, uuid.UUID] = field(default_factory=dict)
    item_names: dict[str, str] = field(default_factory=dict)


class InstallExamplePack(
    CommandHandler[ExampleUnitOfWork, InstallExamplePackCommand, InstallResult]
):
    """Install a pack as an ordered list of steps, recording every entity as it is made.

    :raises PackNotFoundError: the catalogue has no such pack.
    :raises PackAlreadyInstalledError: installed already, or an earlier install is unfinished.
    :raises SlugClashError: a type slug the pack needs is already taken (nothing is created).
    :raises InstallFailedError: a step failed; what had been created was removed.
    """

    def __init__(
        self,
        uow: ExampleUnitOfWork,
        catalogue: PackCatalogue,
        presets: PresetTarget,
        graph: GraphTarget,
    ) -> None:
        super().__init__(uow)
        self._catalogue = catalogue
        self._presets = presets
        self._graph = graph

    async def handle(
        self, command: InstallExamplePackCommand, actor: Actor
    ) -> InstallResult:
        """Install the pack and return what was created."""
        pack = await self._catalogue.get(command.pack_id)
        if pack is None:
            raise PackNotFoundError(f"Example pack '{command.pack_id}' not found")
        async with self._uow as repos:
            if await repos.installations.get_active_for_pack(pack.id) is not None:
                raise PackAlreadyInstalledError(
                    f"'{pack.id}' is already installed, or an earlier install did not finish. "
                    "Remove it first."
                )
        await self._check_slugs(pack)

        installation = Installation.start(pack.id)
        await self._persist(installation, new=True)
        run = _Run(pack=pack, installation=installation)
        try:
            await self._install_presets(run)
            await self._install_relationship_types(run)
            await self._install_item_types(run)
            await self._install_items(run)
            await self._install_connections(run)
        except Exception as exc:
            await self._roll_back(installation, exc)

        installation.mark_installed()
        await self._persist(installation)
        logger.info("example pack installed", pack_id=pack.id, entities=len(installation.entities))
        return InstallResult(pack_id=pack.id, created=installation_counts(installation))

    async def _check_slugs(self, pack: ExamplePack) -> None:
        for spec in pack.item_types:
            if await self._graph.slug_taken(EntityKind.ITEM_TYPE, spec.slug):
                raise SlugClashError(kind="an item type", slug=spec.slug)
        for rel in pack.relationship_types:
            if await self._graph.slug_taken(EntityKind.RELATIONSHIP_TYPE, rel.slug):
                raise SlugClashError(kind="a relationship type", slug=rel.slug)

    async def _persist(self, installation: Installation, *, new: bool = False) -> None:
        async with self._uow as repos:
            if new:
                await repos.installations.add(installation)
            else:
                await repos.installations.save(installation)
            await self._uow.commit()

    async def _record(
        self, run: _Run, kind: EntityKind, ref: str, label: str, entity_id: uuid.UUID,
        content: dict[str, object],
    ) -> None:
        run.installation.record(kind, ref, label, entity_id, content_hash(content))
        await self._persist(run.installation)

    async def _install_presets(self, run: _Run) -> None:
        for outcome, spec in zip(
            await self._presets.ensure(run.pack.presets), run.pack.presets, strict=True
        ):
            run.preset_ids[outcome.ref] = outcome.entity_id
            if outcome.created:  # an identical preset that already existed is not ours
                await self._record(
                    run, EntityKind.PRESET, outcome.ref, spec.label, outcome.entity_id, outcome.content
                )

    async def _install_relationship_types(self, run: _Run) -> None:
        for spec in run.pack.relationship_types:
            created = await self._graph.create_relationship_type(spec, run.preset_ids)
            await self._record(
                run, EntityKind.RELATIONSHIP_TYPE, spec.ref, spec.label, created.entity_id, created.content
            )

    async def _install_item_types(self, run: _Run) -> None:
        for spec in run.pack.item_types:
            created = await self._graph.create_item_type(spec, run.preset_ids)
            run.type_slugs[spec.ref] = spec.slug
            await self._record(
                run, EntityKind.ITEM_TYPE, spec.ref, spec.label, created.entity_id, created.content
            )

    async def _install_items(self, run: _Run) -> None:
        for spec in run.pack.items:
            created = await self._graph.create_item(spec, type_slug=run.type_slugs[spec.type_ref])
            run.item_ids[spec.ref] = created.entity_id
            run.item_names[spec.ref] = spec.name
            await self._record(
                run, EntityKind.ITEM, spec.ref, spec.name, created.entity_id, created.content
            )

    async def _install_connections(self, run: _Run) -> None:
        slugs = {t.ref: t.slug for t in run.pack.relationship_types}
        for n, spec in enumerate(run.pack.connections):
            created = await self._graph.create_connection(
                spec,
                source_id=run.item_ids[spec.source_ref],
                target_id=run.item_ids[spec.target_ref],
                type_slug=slugs[spec.type_ref],
            )
            label = f"{run.item_names[spec.source_ref]} to {run.item_names[spec.target_ref]}"
            await self._record(
                run, EntityKind.CONNECTION, f"connection-{n}", label, created.entity_id, created.content
            )

    async def _roll_back(self, installation: Installation, cause: Exception) -> NoReturn:
        """Remove what was created, then raise `InstallFailedError`."""
        try:
            kept = await settle_installation(
                installation, presets=self._presets, graph=self._graph, persist=self._persist
            )
            installation.mark_failed()
            await self._persist(installation)
        except Exception as rollback_error:
            logger.error("example pack rollback failed", pack_id=installation.pack_id,
                         error=str(rollback_error))
            raise InstallFailedError(
                f"Adding '{installation.pack_id}' failed ({cause}) and could not be undone "
                f"({rollback_error}). Remove the examples from the Examples page to "
                "finish cleaning up."
            ) from cause
        suffix = "" if not kept else f" {len(kept)} item(s) could not be removed and were kept."
        raise InstallFailedError(
            f"Adding '{installation.pack_id}' failed ({cause}). Nothing was left behind.{suffix}"
        ) from cause


def installation_counts(installation: Installation) -> PackCounts:
    """Count an installation's recorded entities by kind, whatever their outcome."""

    def count(kind: EntityKind) -> int:
        return sum(1 for r in installation.entities if r.kind is kind)

    return PackCounts(
        presets=count(EntityKind.PRESET),
        relationship_types=count(EntityKind.RELATIONSHIP_TYPE),
        item_types=count(EntityKind.ITEM_TYPE),
        items=count(EntityKind.ITEM),
        connections=count(EntityKind.CONNECTION),
    )
```

(`_roll_back` always raises, so its return type is `NoReturn` and the `except` block needs nothing after the call.)

- [ ] **Step 5: Run the install tests**

Run: `cd backend && ../.venv/bin/python -m pytest tests/modules/examples/application/test_install_example_pack.py -q`
Expected: PASS except the two tests that need uninstall (skipped until 1.8).

- [ ] **Step 6: Checkpoint.** `poe format`, `poe lint-backend`, `poe typecheck-backend`.

---

## Task 1.8: Uninstall

**Files:**
- Create: `application/uninstall_example_pack.py`
- Test: `tests/modules/examples/application/test_uninstall_example_pack.py`; remove the skips from Task 1.7's tests

**Interfaces:**
- Produces: `UninstallExamplePackCommand(pack_id)`, `UninstallResult(removed: PackCounts, kept: tuple[KeptEntity, ...])`, `UninstallExamplePack(uow, presets, graph)`.

- [ ] **Step 1: Write the failing tests**

```python
import uuid

import pytest

from app.modules.examples.application.install_example_pack import InstallExamplePack, InstallExamplePackCommand
from app.modules.examples.application.uninstall_example_pack import (
    UninstallExamplePack, UninstallExamplePackCommand,
)
from app.modules.examples.domain.errors import PackNotInstalledError
from app.modules.examples.domain.installation import EntityKind, Installation, InstallationStatus
from app.modules.examples.domain.removal import KEEP_EDITED, KEEP_IN_USE, KEEP_USER_DATA
from app.modules.graph.domain.edge import Edge
from app.shared_kernel.actor import SYSTEM_ACTOR
from tests.modules.examples.support import make_world, sample_pack


async def _installed():
    world = make_world()
    await InstallExamplePack(world.uow, world.catalogue, world.presets, world.graph).handle(
        InstallExamplePackCommand(pack_id="demo"), SYSTEM_ACTOR
    )
    return world


async def _uninstall(world, pack_id="demo"):
    return await UninstallExamplePack(world.uow, world.presets, world.graph).handle(
        UninstallExamplePackCommand(pack_id=pack_id), SYSTEM_ACTOR
    )


async def _empty(world) -> None:
    assert await world.graph_repos.nodes.list(after=None, limit=10) == []
    assert await world.graph_repos.node_types.list(after=None, limit=10) == []
    assert await world.graph_repos.edge_types.list(after=None, limit=10) == []
    assert await world.graph_repos.edges.list(after=None, limit=10) == []
    assert await world.preset_repos.presets.list(after=None, limit=10) == []


async def test_removes_everything_that_is_untouched() -> None:
    world = await _installed()

    result = await _uninstall(world)

    await _empty(world)
    assert result.kept == ()
    assert (result.removed.items, result.removed.connections) == (2, 1)
    assert (result.removed.item_types, result.removed.relationship_types, result.removed.presets) == (2, 1, 1)
    assert await world.installations.get_active_for_pack("demo") is None


async def test_unknown_or_not_installed_pack_errors() -> None:
    world = make_world()
    with pytest.raises(PackNotInstalledError):
        await _uninstall(world)


async def test_an_edited_item_is_kept_and_so_are_the_types_it_needs() -> None:
    world = await _installed()
    blue = next(n for n in await world.graph_repos.nodes.list(after=None, limit=10) if n.name == "Blue")
    blue.name = "Blue (my copy)"
    await world.graph_repos.nodes.save(blue)

    result = await _uninstall(world)

    reasons = {(k.kind, k.reason) for k in result.kept}
    assert (EntityKind.ITEM, KEEP_EDITED) in reasons
    assert (EntityKind.ITEM_TYPE, KEEP_IN_USE) in reasons  # "record" still has Blue
    assert (EntityKind.PRESET, KEEP_IN_USE) in reasons  # record's schema still points at it
    assert [n.name for n in await world.graph_repos.nodes.list(after=None, limit=10)] == ["Blue (my copy)"]


async def test_an_item_with_a_users_own_connection_is_kept() -> None:
    world = await _installed()
    ada = next(n for n in await world.graph_repos.nodes.list(after=None, limit=10) if n.name == "Ada")
    await world.graph_repos.edges.add(Edge.create(source_id=ada.id, target_id=uuid.uuid7(), type="mine"))

    result = await _uninstall(world)

    assert any(k.label == "Ada" and k.reason == KEEP_USER_DATA for k in result.kept)


async def test_an_item_with_an_attached_file_is_kept() -> None:
    from app.modules.media.domain.media_attachment import MediaAttachment

    world = await _installed()
    ada = next(n for n in await world.graph_repos.nodes.list(after=None, limit=10) if n.name == "Ada")
    await world.media_repos.attachments.add(
        MediaAttachment.for_node(asset_id=uuid.uuid7(), node_id=ada.id)
    )

    result = await _uninstall(world)

    assert any(k.label == "Ada" and k.reason == KEEP_USER_DATA for k in result.kept)


async def test_a_favourited_item_is_still_removed() -> None:
    world = await _installed()
    for node in await world.graph_repos.nodes.list(after=None, limit=10):
        node.favourite = True
        await world.graph_repos.nodes.save(node)

    result = await _uninstall(world)

    assert result.kept == ()
    await _empty(world)


async def test_something_the_user_already_deleted_is_not_an_error() -> None:
    world = await _installed()
    ada = next(n for n in await world.graph_repos.nodes.list(after=None, limit=10) if n.name == "Ada")
    ada.soft_delete()
    await world.graph_repos.nodes.save(ada)

    result = await _uninstall(world)

    assert result.kept == ()


async def test_a_preset_another_type_uses_is_kept() -> None:
    from app.modules.graph.domain.node_type import NodeType

    world = await _installed()
    preset = (await world.preset_repos.presets.list(after=None, limit=10))[0]
    mine = NodeType.create(slug="mine", label="Mine")
    mine.attributes_schema = {
        "type": "object",
        "properties": {"c": {"type": "string", "x-menagerist": {"list": str(preset.id)}}},
    }
    await world.graph_repos.node_types.add(mine)

    result = await _uninstall(world)

    assert any(k.kind is EntityKind.PRESET and k.reason == KEEP_IN_USE for k in result.kept)


async def test_kept_entities_are_no_longer_the_packs() -> None:
    world = await _installed()
    blue = next(n for n in await world.graph_repos.nodes.list(after=None, limit=10) if n.name == "Blue")
    blue.name = "Mine now"
    await world.graph_repos.nodes.save(blue)
    await _uninstall(world)

    # a second uninstall finds nothing to do, and a reinstall is blocked by the kept type's slug
    from app.modules.examples.domain.errors import SlugClashError
    with pytest.raises(SlugClashError):
        await InstallExamplePack(world.uow, world.catalogue, world.presets, world.graph).handle(
            InstallExamplePackCommand(pack_id="demo"), SYSTEM_ACTOR
        )


async def test_an_unfinished_installation_is_resumed() -> None:
    world = await _installed()
    installation = await world.installations.get_active_for_pack("demo")
    installation.status = InstallationStatus.INSTALLING  # as if the process died before finishing

    result = await _uninstall(world)

    assert result.kept == ()
    await _empty(world)
    assert await world.installations.get_active_for_pack("demo") is None
```

The "kept entities are no longer the pack's" test documents the deliberate behaviour that a kept type's slug blocks a clean reinstall until the user renames or removes it (the Examples page shows the clash message).

- [ ] **Step 2: Run to confirm they fail** (`ModuleNotFoundError`), then write `application/uninstall_example_pack.py`:

```python
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from app.modules.examples.application.removal import KeptEntity, settle_installation
from app.modules.examples.domain.errors import PackNotInstalledError
from app.modules.examples.domain.installation import EntityKind, Installation, Outcome
from app.modules.examples.domain.pack import PackCounts
from app.modules.examples.ports.pack_targets import GraphTarget, PresetTarget  # noqa: TC001
from app.modules.examples.ports.unit_of_work import ExampleUnitOfWork
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class UninstallExamplePackCommand:
    """Request to remove an installed example pack."""

    pack_id: str


@dataclass(kw_only=True, frozen=True, eq=False)
class UninstallResult:
    """What a removal did: how much went, and what was kept and why."""

    pack_id: str
    removed: PackCounts
    kept: tuple[KeptEntity, ...]


class UninstallExamplePack(
    CommandHandler[ExampleUnitOfWork, UninstallExamplePackCommand, UninstallResult]
):
    """Remove what a pack created and the user has not changed; keep and report the rest.

    Also finishes an installation an earlier crash left unfinished.

    :raises PackNotInstalledError: there is nothing to remove.
    """

    def __init__(self, uow: ExampleUnitOfWork, presets: PresetTarget, graph: GraphTarget) -> None:
        super().__init__(uow)
        self._presets = presets
        self._graph = graph

    async def handle(
        self, command: UninstallExamplePackCommand, actor: Actor
    ) -> UninstallResult:
        """Settle every owned entity, then close the installation."""
        async with self._uow as repos:
            installation = await repos.installations.get_active_for_pack(command.pack_id)
        if installation is None:
            raise PackNotInstalledError(f"'{command.pack_id}' is not installed")

        kept = await settle_installation(
            installation, presets=self._presets, graph=self._graph, persist=self._persist
        )
        installation.mark_removed()
        await self._persist(installation)
        logger.info("example pack removed", pack_id=command.pack_id, kept=len(kept))
        return UninstallResult(
            pack_id=command.pack_id, removed=_removed_counts(installation), kept=tuple(kept)
        )

    async def _persist(self, installation: Installation) -> None:
        async with self._uow as repos:
            await repos.installations.save(installation)
            await self._uow.commit()


def _removed_counts(installation: Installation) -> PackCounts:
    def count(kind: EntityKind) -> int:
        return sum(
            1 for r in installation.entities if r.kind is kind and r.outcome is Outcome.REMOVED
        )

    return PackCounts(
        presets=count(EntityKind.PRESET),
        relationship_types=count(EntityKind.RELATIONSHIP_TYPE),
        item_types=count(EntityKind.ITEM_TYPE),
        items=count(EntityKind.ITEM),
        connections=count(EntityKind.CONNECTION),
    )
```

Note: the installation fetched from the repository is the same object the in-memory repository holds, so `settle` mutates it in place; with Postgres (Task 1.9) `get_active_for_pack` returns a fresh domain object and `save` merges it back. Both work because `_persist` saves after each change.

- [ ] **Step 3: Run the uninstall tests and the whole examples application suite**

Run: `cd backend && ../.venv/bin/python -m pytest tests/modules/examples -q --cov=app.modules.examples --cov-report=term-missing`
Expected: PASS; domain and application 100%. Add a test for any uncovered branch (typically the "REFUSED_IN_USE from the target" branch for a relationship type, and the already-gone branch).

- [ ] **Step 4: Checkpoint.** `poe format`, `poe lint-backend`, `poe typecheck-backend`.

---

## Task 1.9: Persistence

**Files:**
- Create: `adapters/persistence/models.py`, `installation_repository.py`, `unit_of_work.py`; `backend/src/app/alembic/versions/g8b9c0d1e2f3_create_example_installations.py`
- Modify: `backend/src/app/alembic/env.py` (import the new models module beside the others)
- Test: `tests/modules/examples/adapters/test_installation_repository.py` (integration)

**Interfaces:**
- Produces: `ExampleInstallationModel`, `SqlAlchemyInstallationRepository`, `build_example_repos(session)`, `create_example_uow(session_factory)`, `create_in_memory_example_uow(repos)`.

- [ ] **Step 1: Write the failing integration tests**

```python
import pytest
from sqlalchemy.exc import IntegrityError

from app.modules.examples.adapters.persistence.installation_repository import (
    SqlAlchemyInstallationRepository,
)
from app.modules.examples.domain.installation import EntityKind, Installation, Outcome

pytestmark = pytest.mark.integration


async def test_round_trips_entities_through_jsonb(db_session) -> None:
    import uuid

    repo = SqlAlchemyInstallationRepository(db_session)
    installation = Installation.start("demo")
    entity_id = uuid.uuid7()
    installation.record(EntityKind.ITEM, "blue", "Blue", entity_id, "h" * 64)
    installation.settle(entity_id, Outcome.KEPT, "edited")
    await repo.add(installation)
    db_session.expire_all()

    stored = await repo.get(installation.id)

    assert stored is not None
    record = stored.entities[0]
    assert (record.kind, record.ref, record.label, record.entity_id) == (
        EntityKind.ITEM, "blue", "Blue", entity_id,
    )
    assert (record.content_hash, record.outcome, record.reason) == ("h" * 64, Outcome.KEPT, "edited")


async def test_save_persists_status_changes(db_session) -> None:
    repo = SqlAlchemyInstallationRepository(db_session)
    installation = Installation.start("demo")
    await repo.add(installation)
    installation.mark_installed()
    await repo.save(installation)
    db_session.expire_all()

    stored = await repo.get(installation.id)
    assert stored is not None and stored.installed_at is not None and stored.is_active


async def test_active_lookup_and_list(db_session) -> None:
    repo = SqlAlchemyInstallationRepository(db_session)
    gone = Installation.start("demo")
    gone.mark_removed()
    await repo.add(gone)
    live = Installation.start("demo")
    await repo.add(live)

    assert (await repo.get_active_for_pack("demo")).id == live.id  # type: ignore[union-attr]
    assert [i.id for i in await repo.list_active()] == [live.id]
    assert await repo.get_active_for_pack("other") is None


async def test_the_index_backs_the_one_active_install_rule(db_session) -> None:
    repo = SqlAlchemyInstallationRepository(db_session)
    await repo.add(Installation.start("demo"))
    with pytest.raises(IntegrityError):
        await repo.add(Installation.start("demo"))
```

- [ ] **Step 2: Run to confirm they fail**, then write the model:

```python
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.database import Base
from app.platform.orm_mixins import IdentifiableMixin, TimestampedMixin


class ExampleInstallationModel(IdentifiableMixin, TimestampedMixin, Base):
    """ORM row for an example pack installation."""

    __tablename__ = "example_installations"
    # A backstop only: `InstallExamplePack` already refuses a second active install.
    __table_args__ = (
        Index(
            "uq_example_installations_active_pack",
            "pack_id",
            unique=True,
            postgresql_where=text("status IN ('installing', 'installed')"),
        ),
    )

    pack_id: Mapped[str] = mapped_column(index=True)
    status: Mapped[str]
    entities: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    installed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

the migration `g8b9c0d1e2f3_create_example_installations.py` (follow `e5f6a7b8c9d0_create_presets_table.py` for column types; `down_revision = "f7a8b9c0d1e2"`):

```python
def upgrade() -> None:
    op.create_table(
        "example_installations",
        sa.Column("pack_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("entities", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                  server_default="[]"),
        sa.Column("installed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_example_installations_pack_id"), "example_installations", ["pack_id"], unique=False)
    op.create_index(
        "uq_example_installations_active_pack", "example_installations", ["pack_id"],
        unique=True, postgresql_where=sa.text("status IN ('installing', 'installed')"),
    )


def downgrade() -> None:
    op.drop_index("uq_example_installations_active_pack", table_name="example_installations",
                  postgresql_where=sa.text("status IN ('installing', 'installed')"))
    op.drop_index(op.f("ix_example_installations_pack_id"), table_name="example_installations")
    op.drop_table("example_installations")
```

The model's `entities` default (`default=list`) and the migration's `server_default="[]"` must agree for pytest-alembic; if `test_model_definitions_match_ddl` complains, add `server_default=text("'[]'::jsonb")` to the model column the way `PresetModel.definition` does (it uses `default=dict` with a `server_default="{}"` in the migration, so copy that exact pairing).

the repository:

```python
import uuid
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import select

from app.modules.examples.adapters.persistence.models import ExampleInstallationModel
from app.modules.examples.domain.installation import (
    EntityKind,
    EntityRecord,
    Installation,
    InstallationStatus,
    Outcome,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()
_ACTIVE = (InstallationStatus.INSTALLING.value, InstallationStatus.INSTALLED.value)


def _record_to_json(r: EntityRecord) -> dict[str, Any]:
    return {"kind": r.kind.value, "ref": r.ref, "label": r.label, "entity_id": str(r.entity_id),
            "content_hash": r.content_hash, "outcome": r.outcome.value, "reason": r.reason}


def _record_from_json(d: dict[str, Any]) -> EntityRecord:
    return EntityRecord(kind=EntityKind(d["kind"]), ref=d["ref"], label=d["label"],
                        entity_id=uuid.UUID(d["entity_id"]), content_hash=d["content_hash"],
                        outcome=Outcome(d["outcome"]), reason=d.get("reason"))


def _to_domain(m: ExampleInstallationModel) -> Installation:
    return Installation(
        id=m.id, pack_id=m.pack_id, status=InstallationStatus(m.status),
        entities=[_record_from_json(d) for d in m.entities],
        installed_at=m.installed_at, removed_at=m.removed_at,
        created_at=m.created_at, updated_at=m.updated_at,
    )


def _to_model(i: Installation) -> ExampleInstallationModel:
    return ExampleInstallationModel(
        id=i.id, pack_id=i.pack_id, status=i.status.value,
        entities=[_record_to_json(r) for r in i.entities],
        installed_at=i.installed_at, removed_at=i.removed_at,
        created_at=i.created_at, updated_at=i.updated_at,
    )


class SqlAlchemyInstallationRepository:
    """Postgres-backed `InstallationRepository`, scoped to one session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, installation: Installation) -> None:
        """Add a new installation."""
        logger.debug("adding example installation", installation_id=installation.id)
        self._session.add(_to_model(installation))
        await self._session.flush()

    async def save(self, installation: Installation) -> None:
        """Persist changes to an existing installation."""
        logger.debug("saving example installation", installation_id=installation.id)
        await self._session.merge(_to_model(installation))
        await self._session.flush()

    async def get(self, installation_id: uuid.UUID) -> Installation | None:
        """Return the installation with `installation_id`, or `None`."""
        model = await self._session.get(ExampleInstallationModel, installation_id)
        return None if model is None else _to_domain(model)

    async def get_active_for_pack(self, pack_id: str) -> Installation | None:
        """Return the installing or installed installation of `pack_id`, if any."""
        stmt = select(ExampleInstallationModel).where(
            ExampleInstallationModel.pack_id == pack_id,
            ExampleInstallationModel.status.in_(_ACTIVE),
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return None if model is None else _to_domain(model)

    async def list_active(self) -> list[Installation]:
        """Return every installing or installed installation, oldest first."""
        stmt = (
            select(ExampleInstallationModel)
            .where(ExampleInstallationModel.status.in_(_ACTIVE))
            .order_by(ExampleInstallationModel.id)
        )
        return [_to_domain(m) for m in (await self._session.execute(stmt)).scalars()]
```

and `unit_of_work.py` (same three-function shape as the presets one):

```python
from typing import TYPE_CHECKING

from app.modules.examples.adapters.persistence.installation_repository import (
    SqlAlchemyInstallationRepository,
)
from app.modules.examples.ports.unit_of_work import ExampleRepos
from app.platform.unit_of_work import SqlAlchemySessionUnitOfWork
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.modules.examples.ports.unit_of_work import ExampleUnitOfWork


def build_example_repos(session: AsyncSession) -> ExampleRepos:
    """Build an `ExampleRepos` bundle of SQLAlchemy repositories over `session`."""
    return ExampleRepos(installations=SqlAlchemyInstallationRepository(session))


def create_example_uow(session_factory: async_sessionmaker[AsyncSession]) -> ExampleUnitOfWork:
    """Wrap a session factory in a SqlAlchemySessionUnitOfWork."""
    return SqlAlchemySessionUnitOfWork(session_factory, build_example_repos)


def create_in_memory_example_uow(repos: ExampleRepos) -> ExampleUnitOfWork:
    """Wrap repos in an InMemoryUnitOfWork."""
    return InMemoryUnitOfWork(repos)
```

In `alembic/env.py` add `from app.modules.examples.adapters.persistence import models as example_models  # noqa: F401` beside the others.

- [ ] **Step 3: Migrate and test**

Run: `export PATH=$PWD/.venv/bin:$PATH && poe migrate && cd backend && ../.venv/bin/python -m pytest tests/modules/examples/adapters/test_installation_repository.py tests/platform/test_migrations.py -q -m integration`
Expected: PASS, including pytest-alembic (`test_model_definitions_match_ddl`, `test_up_down_consistency`, `test_single_head_revision`).

- [ ] **Step 4: Checkpoint.** `poe lint-backend`, `poe typecheck-backend`, `poe test-backend-integration`.

---

## Task 1.10: File catalogue

**Files:**
- Create: `adapters/platform/pack_parser.py`, `adapters/platform/file_pack_catalogue.py`
- Test: `tests/modules/examples/adapters/test_pack_parser.py`, `test_file_pack_catalogue.py`

**Interfaces:**
- Produces: `parse_index(data) -> list[IndexEntry]`, `parse_pack(data) -> ExamplePack`, `IndexEntry(id, name, description)`, `FilePackCatalogue(root: Path | None = None)` implementing `PackCatalogue`. Constants `INDEX_FORMAT = "menagerist-examples-index"`, `PACK_FORMAT = "menagerist-example-pack"`, `FORMAT_VERSION = 1`.

- [ ] **Step 1: Write the failing tests** (`test_pack_parser.py`):

```python
import pytest

from app.modules.examples.adapters.platform.pack_parser import parse_index, parse_pack
from app.modules.examples.domain.errors import InvalidPackError

_PACK = {
    "format": "menagerist-example-pack",
    "version": 1,
    "id": "demo",
    "presets": [{"ref": "grades", "kind": "choice_list", "label": "Grades",
                 "definition": {"options": ["Mint"]}}],
    "relationship_types": [{"ref": "by", "slug": "by", "label": "By", "reverse_label": "Made"}],
    "item_types": [{"ref": "thing", "slug": "thing", "label": "Thing"}],
    "items": [{"ref": "a", "type": "thing", "name": "A", "tags": ["x"]},
              {"ref": "b", "type": "thing", "name": "B"}],
    "connections": [{"from": "a", "to": "b", "type": "by"}],
}


def test_parses_a_pack() -> None:
    pack = parse_pack(_PACK)
    assert pack.id == "demo" and pack.counts.items == 2
    assert pack.items[0].tags == ("x",) and pack.relationship_types[0].reverse_label == "Made"
    assert pack.connections[0].source_ref == "a"


def _without(key: str) -> dict:
    return {k: v for k, v in _PACK.items() if k != key}


@pytest.mark.parametrize(
    "data",
    [
        [],
        {**_PACK, "format": "other"},
        {**_PACK, "version": 2},
        _without("id"),
        {**_PACK, "surprise": 1},
        {**_PACK, "items": [{"ref": "a", "type": "thing", "name": "A", "colour": "red"}]},
        {**_PACK, "items": [{"ref": "a", "type": "thing"}]},
        {**_PACK, "items": "nope"},
        {**_PACK, "connections": [{"from": "a", "to": "b"}]},
    ],
)
def test_a_malformed_pack_is_an_invalid_pack_error(data: object) -> None:
    with pytest.raises(InvalidPackError):
        parse_pack(data)


def test_parses_an_index() -> None:
    entries = parse_index({"format": "menagerist-examples-index", "version": 1,
                           "packs": [{"id": "demo", "name": "Demo", "description": "A demo"}]})
    assert [(e.id, e.name, e.description) for e in entries] == [("demo", "Demo", "A demo")]


@pytest.mark.parametrize(
    "data",
    [
        {"format": "x", "version": 1, "packs": []},
        {"format": "menagerist-examples-index", "version": 2, "packs": []},
        {"format": "menagerist-examples-index", "version": 1, "packs": [{"id": "demo"}]},
        {"format": "menagerist-examples-index", "version": 1, "packs": [], "extra": 1},
    ],
)
def test_a_malformed_index_is_an_invalid_pack_error(data: dict) -> None:
    with pytest.raises(InvalidPackError):
        parse_index(data)
```

and `test_file_pack_catalogue.py`:

```python
import json
from pathlib import Path

import pytest

from app.modules.examples.adapters.platform.file_pack_catalogue import FilePackCatalogue
from app.modules.examples.domain.errors import InvalidPackError

from tests.modules.examples.adapters.test_pack_parser import _PACK


def _write(root: Path, index: list[dict], packs: dict[str, dict]) -> FilePackCatalogue:
    (root / "index.json").write_text(json.dumps(
        {"format": "menagerist-examples-index", "version": 1, "packs": index}), encoding="utf-8")
    for name, data in packs.items():
        (root / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")
    return FilePackCatalogue(root)


async def test_lists_and_gets_packs(tmp_path: Path) -> None:
    catalogue = _write(tmp_path, [{"id": "demo", "name": "Demo", "description": "A demo"}],
                       {"demo": _PACK})

    summaries = await catalogue.list_packs()
    pack = await catalogue.get("demo")

    assert summaries[0].name == "Demo" and summaries[0].counts.items == 2
    assert pack is not None and pack.id == "demo"
    assert await catalogue.get("missing") is None


async def test_an_index_entry_without_a_file_is_rejected(tmp_path: Path) -> None:
    catalogue = _write(tmp_path, [{"id": "demo", "name": "Demo", "description": "x"}], {})
    with pytest.raises(InvalidPackError):
        await catalogue.list_packs()


async def test_a_file_whose_id_differs_from_its_name_is_rejected(tmp_path: Path) -> None:
    catalogue = _write(tmp_path, [{"id": "demo", "name": "Demo", "description": "x"}],
                       {"demo": {**_PACK, "id": "other"}})
    with pytest.raises(InvalidPackError):
        await catalogue.get("demo")


async def test_unreadable_json_is_an_invalid_pack_error(tmp_path: Path) -> None:
    catalogue = _write(tmp_path, [{"id": "demo", "name": "Demo", "description": "x"}], {})
    (tmp_path / "demo.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(InvalidPackError):
        await catalogue.get("demo")


async def test_a_pack_is_parsed_once(tmp_path: Path) -> None:
    catalogue = _write(tmp_path, [{"id": "demo", "name": "Demo", "description": "x"}], {"demo": _PACK})
    first = await catalogue.get("demo")
    (tmp_path / "demo.json").unlink()
    assert await catalogue.get("demo") is first


async def test_defaults_to_the_shared_examples_directory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "examples").mkdir()
    _write(tmp_path / "examples", [], {})
    monkeypatch.setenv("MENAGERIST_SHARED_DIR", str(tmp_path))
    assert await FilePackCatalogue().list_packs() == []
```

- [ ] **Step 2: Run to confirm they fail**, then implement.

`adapters/platform/pack_parser.py`:

```python
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.modules.examples.domain.errors import InvalidPackError
from app.modules.examples.domain.pack import (
    ExamplePack,
    PackConnection,
    PackItem,
    PackItemType,
    PackPreset,
    PackRelationshipType,
)

INDEX_FORMAT = "menagerist-examples-index"
PACK_FORMAT = "menagerist-example-pack"
FORMAT_VERSION = 1


@dataclass(kw_only=True, frozen=True)
class IndexEntry:
    """One line of the catalogue index."""

    id: str
    name: str
    description: str


def _object(value: object, where: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise InvalidPackError(f"{where} must be an object")
    return value


def _array(value: object, where: str) -> list[Any]:
    if not isinstance(value, list):
        raise InvalidPackError(f"{where} must be an array")
    return value


def _check_keys(data: Mapping[str, Any], *, required: set[str], optional: set[str], where: str) -> None:
    missing = required - set(data)
    if missing:
        raise InvalidPackError(f"{where} is missing {sorted(missing)[0]!r}")
    unknown = set(data) - required - optional
    if unknown:
        raise InvalidPackError(f"{where} has unknown key {sorted(unknown)[0]!r}")


def _str(value: object, where: str) -> str:
    if not isinstance(value, str):
        raise InvalidPackError(f"{where} must be a string")
    return value


def _opt_str(value: object, where: str) -> str | None:
    return None if value is None else _str(value, where)


def _opt_object(value: object, where: str) -> dict[str, Any] | None:
    return None if value is None else dict(_object(value, where))


def _envelope(data: object, expected: str, where: str) -> Mapping[str, Any]:
    root = _object(data, where)
    if root.get("format") != expected:
        raise InvalidPackError(f"{where} format must be '{expected}'")
    if root.get("version") != FORMAT_VERSION:
        raise InvalidPackError(f"{where} version {root.get('version')!r} is not supported")
    return root


def parse_index(data: object) -> list[IndexEntry]:
    """Parse `index.json`."""
    root = _envelope(data, INDEX_FORMAT, "the examples index")
    _check_keys(root, required={"format", "version", "packs"}, optional=set(), where="the examples index")
    entries: list[IndexEntry] = []
    for n, raw in enumerate(_array(root["packs"], "packs")):
        entry = _object(raw, f"packs[{n}]")
        _check_keys(entry, required={"id", "name", "description"}, optional=set(), where=f"packs[{n}]")
        entries.append(IndexEntry(id=_str(entry["id"], "id"), name=_str(entry["name"], "name"),
                                  description=_str(entry["description"], "description")))
    return entries


def parse_pack(data: object) -> ExamplePack:
    """Parse one pack file; unknown keys and wrong types are rejected."""
    root = _envelope(data, PACK_FORMAT, "the pack")
    sections = {"presets", "relationship_types", "item_types", "items", "connections"}
    _check_keys(root, required={"format", "version", "id"}, optional=sections, where="the pack")

    def each(section: str) -> list[Mapping[str, Any]]:
        return [_object(v, f"{section}[{n}]") for n, v in enumerate(_array(root.get(section, []), section))]

    presets = []
    for p in each("presets"):
        _check_keys(p, required={"ref", "kind", "label", "definition"}, optional={"description"}, where="a preset")
        presets.append(PackPreset(ref=_str(p["ref"], "ref"), kind=_str(p["kind"], "kind"),
                                  label=_str(p["label"], "label"),
                                  description=_opt_str(p.get("description"), "description"),
                                  definition=dict(_object(p["definition"], "definition"))))
    relationship_types = []
    for t in each("relationship_types"):
        _check_keys(t, required={"ref", "slug", "label"},
                    optional={"reverse_label", "description", "directional", "attributes_schema"},
                    where="a relationship type")
        relationship_types.append(PackRelationshipType(
            ref=_str(t["ref"], "ref"), slug=_str(t["slug"], "slug"), label=_str(t["label"], "label"),
            reverse_label=_opt_str(t.get("reverse_label"), "reverse_label"),
            description=_opt_str(t.get("description"), "description"),
            directional=bool(t.get("directional", True)),
            attributes_schema=_opt_object(t.get("attributes_schema"), "attributes_schema")))
    item_types = []
    for t in each("item_types"):
        _check_keys(t, required={"ref", "slug", "label"}, optional={"description", "attributes_schema"},
                    where="an item type")
        item_types.append(PackItemType(
            ref=_str(t["ref"], "ref"), slug=_str(t["slug"], "slug"), label=_str(t["label"], "label"),
            description=_opt_str(t.get("description"), "description"),
            attributes_schema=_opt_object(t.get("attributes_schema"), "attributes_schema")))
    items = []
    for i in each("items"):
        _check_keys(i, required={"ref", "type", "name"},
                    optional={"description", "attributes", "tags", "extra_schema"}, where="an item")
        items.append(PackItem(
            ref=_str(i["ref"], "ref"), type_ref=_str(i["type"], "type"), name=_str(i["name"], "name"),
            description=_opt_str(i.get("description"), "description"),
            attributes=dict(_object(i.get("attributes", {}), "attributes")),
            tags=tuple(_str(t, "tag") for t in _array(i.get("tags", []), "tags")),
            extra_schema=_opt_object(i.get("extra_schema"), "extra_schema")))
    connections = []
    for c in each("connections"):
        _check_keys(c, required={"from", "to", "type"}, optional={"attributes"}, where="a connection")
        connections.append(PackConnection(
            source_ref=_str(c["from"], "from"), target_ref=_str(c["to"], "to"),
            type_ref=_str(c["type"], "type"),
            attributes=dict(_object(c.get("attributes", {}), "attributes"))))

    return ExamplePack(
        id=_str(root["id"], "id"), presets=tuple(presets),
        relationship_types=tuple(relationship_types), item_types=tuple(item_types),
        items=tuple(items), connections=tuple(connections),
    )
```

`adapters/platform/file_pack_catalogue.py`:

```python
import json
from pathlib import Path
from typing import Any

from app.modules.examples.adapters.platform.pack_parser import IndexEntry, parse_index, parse_pack
from app.modules.examples.domain.errors import InvalidPackError
from app.modules.examples.domain.pack import ExamplePack, PackSummary
from app.platform.shared_data import shared_data_path


class FilePackCatalogue:
    """Reads the packs shipped in `shared/examples/`. Packs never change at runtime, so
    each file is parsed once and kept."""

    def __init__(self, root: Path | None = None) -> None:
        self._root = root
        self._index: list[IndexEntry] | None = None
        self._packs: dict[str, ExamplePack] = {}

    def _dir(self) -> Path:
        return self._root if self._root is not None else shared_data_path("examples")

    def _read(self, name: str) -> Any:
        path = self._dir() / name
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise InvalidPackError(f"cannot read {name}: {exc}") from exc

    def _entries(self) -> list[IndexEntry]:
        if self._index is None:
            self._index = parse_index(self._read("index.json"))
        return self._index

    def _load(self, pack_id: str) -> ExamplePack:
        if pack_id not in self._packs:
            pack = parse_pack(self._read(f"{pack_id}.json"))
            if pack.id != pack_id:
                raise InvalidPackError(f"{pack_id}.json declares id '{pack.id}'")
            self._packs[pack_id] = pack
        return self._packs[pack_id]

    async def list_packs(self) -> list[PackSummary]:
        """Return a summary of every pack in the index."""
        return [
            PackSummary(id=e.id, name=e.name, description=e.description, counts=self._load(e.id).counts)
            for e in self._entries()
        ]

    async def get(self, pack_id: str) -> ExamplePack | None:
        """Return the pack, or `None` if the index does not list it."""
        if all(e.id != pack_id for e in self._entries()):
            return None
        return self._load(pack_id)
```

(The `bool(...)` and `dict(...)` coercions are intentional leniency for `directional` and object fields; tighten with explicit type checks if a test shows a bad value slipping through.)

- [ ] **Step 3: Run both test files**; expect PASS. Then `poe lint-backend` and `poe typecheck-backend`.

- [ ] **Step 4: Checkpoint.**

---

## Task 1.11: API

**Files:**
- Create: `adapters/api/dependencies.py`, `adapters/api/example/schemas.py`, `adapters/api/example/router.py`
- Modify: `backend/src/app/entrypoints/api/__init__.py` (import the router; `api_v1_router.include_router(example_router)` after `preset_router`)
- Test: `tests/modules/examples/adapters/api/test_example_router.py`; `tests/entrypoints/api/test_api_schemas.py` picks the new schemas up on its own

**Interfaces:**
- Consumes: Tasks 1.6 to 1.10; `get_preset_pack_target`, `get_graph_pack_target`.
- Produces: routes `GET /api/v1/example` (`list_example_packs`), `PUT /api/v1/example/{pack_id}/installation` (`install_example_pack`), `DELETE /api/v1/example/{pack_id}/installation` (`uninstall_example_pack`); dependency functions `get_example_uow`, `get_example_repos`, `get_pack_catalogue`, `get_list_example_packs_use_case`, `get_install_example_pack_use_case`, `get_uninstall_example_pack_use_case`.

- [ ] **Step 1: Write the failing router tests**

```python
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.entrypoints.api.shared.example_targets import get_graph_pack_target, get_preset_pack_target
from app.modules.examples.adapters.api.dependencies import (
    get_example_repos, get_example_uow, get_pack_catalogue,
)
from app.modules.examples.ports.unit_of_work import ExampleRepos
from tests.modules.examples.support import World, make_world, sample_pack


def _client(world: World) -> TestClient:
    app: FastAPI = create_app()
    app.dependency_overrides[get_example_uow] = lambda: world.uow
    app.dependency_overrides[get_example_repos] = lambda: ExampleRepos(installations=world.installations)
    app.dependency_overrides[get_pack_catalogue] = lambda: world.catalogue
    app.dependency_overrides[get_preset_pack_target] = lambda: world.presets
    app.dependency_overrides[get_graph_pack_target] = lambda: world.graph
    return TestClient(app)


def test_list_shows_packs_and_installation_state() -> None:
    client = _client(make_world(sample_pack("one"), sample_pack("two")))

    first = client.get("/api/v1/example")
    assert first.status_code == 200
    assert [p["id"] for p in first.json()] == ["one", "two"]
    assert first.json()[0]["installation"] is None
    assert first.json()[0]["counts"]["items"] == 2

    assert client.put("/api/v1/example/one/installation").status_code == 200
    after = client.get("/api/v1/example").json()
    assert after[0]["installation"]["status"] == "installed"
    assert after[0]["installation"]["counts"]["items"] == 2
    assert after[1]["installation"] is None


def test_install_returns_what_was_created() -> None:
    client = _client(make_world())
    response = client.put("/api/v1/example/demo/installation")
    assert response.status_code == 200
    body = response.json()
    assert body["pack_id"] == "demo" and body["created"]["item_types"] == 2


def test_install_twice_is_a_409_and_unknown_is_a_404() -> None:
    client = _client(make_world())
    assert client.put("/api/v1/example/demo/installation").status_code == 200
    again = client.put("/api/v1/example/demo/installation")
    assert again.status_code == 409 and again.json()["title"] == "PackAlreadyInstalledError"
    assert client.put("/api/v1/example/nope/installation").status_code == 404


def test_uninstall_reports_removed_and_kept() -> None:
    world = make_world()
    client = _client(world)
    client.put("/api/v1/example/demo/installation")

    response = client.delete("/api/v1/example/demo/installation")

    assert response.status_code == 200
    body = response.json()
    assert body["removed"]["items"] == 2 and body["kept"] == []


def test_uninstall_when_not_installed_is_a_409() -> None:
    client = _client(make_world())
    assert client.delete("/api/v1/example/demo/installation").status_code == 409


def test_a_failed_install_is_a_500_problem_with_the_cause() -> None:
    world = make_world()

    async def boom(*args, **kwargs):
        raise RuntimeError("boom")

    world.graph.create_item = boom  # type: ignore[method-assign]
    client = _client(world)

    response = client.put("/api/v1/example/demo/installation")

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/problem+json")
    assert "boom" in response.json()["detail"]


def test_slug_clash_is_a_409_naming_the_slug() -> None:
    import asyncio
    from app.modules.graph.domain.node_type import NodeType

    world = make_world()
    asyncio.run(world.graph_repos.node_types.add(NodeType.create(slug="demo-record", label="Mine")))
    response = _client(world).put("/api/v1/example/demo/installation")
    assert response.status_code == 409 and "demo-record" in response.json()["detail"]
```

(`TestClient` with an app whose dependencies are in-memory works because the in-memory stores are plain Python objects shared across requests. Use `TestClient(app, raise_server_exceptions=False)` for the 500 test so the server error becomes a response instead of re-raising.)

- [ ] **Step 2: Run to confirm they fail**, then write.

`schemas.py` (every model has `json_schema_extra` examples, as `test_api_schemas.py` requires; nested models too):

```python
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from app.modules.examples.application.install_example_pack import InstallResult
    from app.modules.examples.application.list_example_packs import ExamplePackStatus
    from app.modules.examples.application.removal import KeptEntity
    from app.modules.examples.application.uninstall_example_pack import UninstallResult
    from app.modules.examples.domain.pack import PackCounts

_COUNTS_EXAMPLE: dict[str, Any] = {
    "presets": 1, "relationship_types": 2, "item_types": 3, "items": 12, "connections": 14
}


class PackCountsResponse(BaseModel):
    """How many of each thing an example set contains."""

    model_config = ConfigDict(json_schema_extra={"examples": [_COUNTS_EXAMPLE]})

    presets: int
    relationship_types: int
    item_types: int
    items: int
    connections: int

    @classmethod
    def from_domain(cls, counts: PackCounts) -> PackCountsResponse:
        """Build from the domain counts."""
        return cls(presets=counts.presets, relationship_types=counts.relationship_types,
                   item_types=counts.item_types, items=counts.items, connections=counts.connections)


class InstallationResponse(BaseModel):
    """An example set that is installed on this server."""

    model_config = ConfigDict(json_schema_extra={"examples": [{
        "status": "installed", "installed_at": "2026-10-06T10:14:44.465954Z",
        "counts": _COUNTS_EXAMPLE}]})

    status: str
    installed_at: datetime | None
    counts: PackCountsResponse


class ExamplePackResponse(BaseModel):
    """A shipped example set and whether it is installed."""

    model_config = ConfigDict(json_schema_extra={"examples": [{
        "id": "vinyl", "name": "Vinyl and signed items",
        "description": "Records, artists and signings, with who signed what.",
        "counts": _COUNTS_EXAMPLE, "installation": None}]})

    id: str
    name: str
    description: str
    counts: PackCountsResponse
    installation: InstallationResponse | None

    @classmethod
    def from_status(cls, status: ExamplePackStatus) -> ExamplePackResponse:
        """Build from a list-query result."""
        installation = status.installation
        return cls(
            id=status.summary.id, name=status.summary.name, description=status.summary.description,
            counts=PackCountsResponse.from_domain(status.summary.counts),
            installation=None if installation is None else InstallationResponse(
                status=installation.status.value, installed_at=installation.installed_at,
                counts=PackCountsResponse.from_domain(installation_counts(installation))),
        )


class InstallResultResponse(BaseModel):
    """What adding an example set created."""

    model_config = ConfigDict(json_schema_extra={"examples": [{
        "pack_id": "vinyl", "created": _COUNTS_EXAMPLE}]})

    pack_id: str
    created: PackCountsResponse

    @classmethod
    def from_domain(cls, result: InstallResult) -> InstallResultResponse:
        """Build from the install result."""
        return cls(pack_id=result.pack_id, created=PackCountsResponse.from_domain(result.created))


class KeptEntityResponse(BaseModel):
    """Something removal left in place, and why."""

    model_config = ConfigDict(json_schema_extra={"examples": [{
        "kind": "item", "label": "Blue (my copy)", "reason": "edited"}]})

    kind: str
    label: str
    reason: str

    @classmethod
    def from_domain(cls, kept: KeptEntity) -> KeptEntityResponse:
        """Build from a kept entity."""
        return cls(kind=kept.kind.value, label=kept.label, reason=kept.reason)


class UninstallResultResponse(BaseModel):
    """What removing an example set did."""

    model_config = ConfigDict(json_schema_extra={"examples": [{
        "pack_id": "vinyl", "removed": _COUNTS_EXAMPLE,
        "kept": [{"kind": "item", "label": "Blue (my copy)", "reason": "edited"}]}]})

    pack_id: str
    removed: PackCountsResponse
    kept: list[KeptEntityResponse]

    @classmethod
    def from_domain(cls, result: UninstallResult) -> UninstallResultResponse:
        """Build from the uninstall result."""
        return cls(pack_id=result.pack_id, removed=PackCountsResponse.from_domain(result.removed),
                   kept=[KeptEntityResponse.from_domain(k) for k in result.kept])
```

`installation_counts(installation)` is a small pure function in `application/install_example_pack.py` (Task 1.7, replacing a private `_created_counts`); it counts an installation's records by kind whatever their outcome (for an installed pack, every record is owned). `schemas.py` imports it at runtime: `from app.modules.examples.application.install_example_pack import installation_counts`.

`dependencies.py`:

```python
from functools import lru_cache
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends

from app.entrypoints.api.shared.example_targets import (
    GraphPackTarget, PresetPackTarget, get_graph_pack_target, get_preset_pack_target,
)
from app.modules.examples.adapters.persistence.unit_of_work import build_example_repos, create_example_uow
from app.modules.examples.adapters.platform.file_pack_catalogue import FilePackCatalogue
from app.modules.examples.application.install_example_pack import InstallExamplePack
from app.modules.examples.application.list_example_packs import ListExamplePacks
from app.modules.examples.application.uninstall_example_pack import UninstallExamplePack
from app.modules.examples.ports.pack_catalogue import PackCatalogue
from app.modules.examples.ports.unit_of_work import ExampleRepos, ExampleUnitOfWork
from app.platform.database import get_session_factory

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


def get_example_uow(
    session_factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
) -> ExampleUnitOfWork:
    """Return a unit of work over the installations table, for commands."""
    return create_example_uow(session_factory)


async def get_example_repos(
    session_factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
) -> AsyncIterator[ExampleRepos]:
    """Return a read-only repository bundle, for queries."""
    async with session_factory() as session:
        yield build_example_repos(session)


@lru_cache(maxsize=1)
def _catalogue() -> FilePackCatalogue:
    return FilePackCatalogue()


def get_pack_catalogue() -> PackCatalogue:
    """Return the shipped-pack catalogue (parsed once per process)."""
    return _catalogue()


def get_list_example_packs_use_case(
    repos: Annotated[ExampleRepos, Depends(get_example_repos)],
    catalogue: Annotated[PackCatalogue, Depends(get_pack_catalogue)],
) -> ListExamplePacks:
    return ListExamplePacks(repos, catalogue)


def get_install_example_pack_use_case(
    uow: Annotated[ExampleUnitOfWork, Depends(get_example_uow)],
    catalogue: Annotated[PackCatalogue, Depends(get_pack_catalogue)],
    presets: Annotated[PresetPackTarget, Depends(get_preset_pack_target)],
    graph: Annotated[GraphPackTarget, Depends(get_graph_pack_target)],
) -> InstallExamplePack:
    return InstallExamplePack(uow, catalogue, presets, graph)


def get_uninstall_example_pack_use_case(
    uow: Annotated[ExampleUnitOfWork, Depends(get_example_uow)],
    presets: Annotated[PresetPackTarget, Depends(get_preset_pack_target)],
    graph: Annotated[GraphPackTarget, Depends(get_graph_pack_target)],
) -> UninstallExamplePack:
    return UninstallExamplePack(uow, presets, graph)
```

`example/router.py`:

```python
from typing import Annotated

from fastapi import APIRouter, Depends

from app.entrypoints.api.shared.dependencies import get_current_actor
from app.entrypoints.api.shared.permission_aware_route import PermissionAwareRoute
from app.entrypoints.api.shared.problem_response import error_response
from app.modules.examples.adapters.api.dependencies import (
    get_install_example_pack_use_case,
    get_list_example_packs_use_case,
    get_uninstall_example_pack_use_case,
)
from app.modules.examples.adapters.api.example.schemas import (
    ExamplePackResponse,
    InstallResultResponse,
    UninstallResultResponse,
)
from app.modules.examples.application.install_example_pack import (
    InstallExamplePack,
    InstallExamplePackCommand,
)
from app.modules.examples.application.list_example_packs import (
    ListExamplePacks,
    ListExamplePacksQuery,
)
from app.modules.examples.application.uninstall_example_pack import (
    UninstallExamplePack,
    UninstallExamplePackCommand,
)
from app.modules.examples.domain.errors import (
    PackAlreadyInstalledError,
    PackNotFoundError,
    PackNotInstalledError,
)
from app.shared_kernel.actor import Actor

router = APIRouter(prefix="/example", tags=["Examples"], route_class=PermissionAwareRoute)

_NOT_FOUND = error_response(PackNotFoundError, detail="Example pack 'vinyl' not found")
# One 409 entry per route: a response status can only be documented once. The install
# route's 409 also covers a taken type name (`SlugClashError`); its docstring says so.
_ALREADY = error_response(PackAlreadyInstalledError, detail="'vinyl' is already installed.")
_NOT_INSTALLED = error_response(PackNotInstalledError, detail="'vinyl' is not installed")


@router.get("", response_model=list[ExamplePackResponse], operation_id="list_example_packs")
async def list_example_packs(
    use_case: Annotated[ListExamplePacks, Depends(get_list_example_packs_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> list[ExamplePackResponse]:
    """List the example sets this server ships and which are installed."""
    statuses = await use_case.handle(ListExamplePacksQuery(), actor)
    return [ExamplePackResponse.from_status(s) for s in statuses]


@router.put(
    "/{pack_id}/installation",
    response_model=InstallResultResponse,
    operation_id="install_example_pack",
    responses={**_NOT_FOUND, **_ALREADY},
)
async def install_example_pack(
    pack_id: str,
    use_case: Annotated[InstallExamplePack, Depends(get_install_example_pack_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> InstallResultResponse:
    """Add an example set: its item types, items, connections and saved lists.

    Returns 409 if the set is already added, or if you already have an item type or
    relationship type with a name it needs (nothing is created in that case).
    """
    result = await use_case.handle(InstallExamplePackCommand(pack_id=pack_id), actor)
    return InstallResultResponse.from_domain(result)


@router.delete(
    "/{pack_id}/installation",
    response_model=UninstallResultResponse,
    operation_id="uninstall_example_pack",
    responses={**_NOT_FOUND, **_NOT_INSTALLED},
)
async def uninstall_example_pack(
    pack_id: str,
    use_case: Annotated[UninstallExamplePack, Depends(get_uninstall_example_pack_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> UninstallResultResponse:
    """Remove an example set. Anything you changed or connected to is kept."""
    result = await use_case.handle(UninstallExamplePackCommand(pack_id=pack_id), actor)
    return UninstallResultResponse.from_domain(result)
```

In `entrypoints/api/__init__.py` add `from app.modules.examples.adapters.api.example.router import router as example_router` and `api_v1_router.include_router(example_router)`.

- [ ] **Step 3: Run the router tests and the schema tests**

Run: `cd backend && ../.venv/bin/python -m pytest tests/modules/examples/adapters/api tests/entrypoints/api/test_api_schemas.py -q`
Expected: PASS.

- [ ] **Step 4: Write the end-to-end integration test** `tests/modules/examples/adapters/api/test_example_install_postgres.py` (`@pytest.mark.integration`): write a tiny pack into a temp directory, point `MENAGERIST_SHARED_DIR` at it, build the app with real dependencies (no overrides), run `PUT`, `GET`, `DELETE`, `PUT` again through `TestClient`, and assert the second install succeeds and `GET /api/v1/node-type` is empty after removal. This is the test that proves Phase 0 and Phase 1 together on Postgres. If the real `get_session_factory` is not aimed at the testcontainers database by default, follow how `tests/entrypoints/cli/test_cli.py` or an existing integration API test sets `MENAGERIST_DATABASE_URL` (the `postgres_url` fixture already does).

- [ ] **Step 5: Full backend checks**

Run: `poe lint-backend`, `poe typecheck-backend`, `poe test-backend`, `poe test-backend-integration`, `poe coverage`
Expected: all green; domain and application 100%, adapters at or above 80%.

- [ ] **Step 6: Checkpoint.**

---

## Task 1.12: Regenerate the client

**Files:** none edited by hand (`frontend/src/lib/api/generated/` is generated and gitignored; `frontend/openapi.json` may change, check `git status`).

- [ ] **Step 1:** `export PATH=$PWD/.venv/bin:$PATH && poe generate-frontend-client`
- [ ] **Step 2:** Confirm `listExamplePacks`, `installExamplePack`, `uninstallExamplePack` and the types `ExamplePackResponse`, `InstallResultResponse`, `UninstallResultResponse`, `PackCountsResponse` are exported from `frontend/src/lib/api/client.ts` (open it; if it re-exports by name, add the new names to it).
- [ ] **Step 3:** `poe typecheck-frontend` and `poe lint-frontend` still pass.
- [ ] **Step 4: Checkpoint.** Draft the commit message for Phase 1 (type `feat(examples)`), without a `Co-Authored-By` trailer, and stop for the user to commit.

---

## Self-review against the spec

- **Spec section 1 (pack files):** parser and catalogue (1.10); `$preset` markers (1.2, 1.5); unknown keys and versions rejected (1.10).
- **Section 2 (module):** layout in "File Structure"; ports owned by `examples` (1.3); targets in `entrypoints/api/shared` (1.5); installation entity and table (1.2, 1.9).
- **Section 3 (install):** pre-flight (1.7), steps in order (1.7), existing presets not owned (1.4, 1.5, 1.7), compensation (1.7), unfinished install resumable (1.7, 1.8).
- **Section 4 (uninstall):** order and decisions (1.2, 1.7 `settle_installation`, 1.8); favourite excluded (1.5, 1.8); preset in use (1.5, 1.8).
- **Section 5 (slugs):** Phase 0, exercised by 1.7's reinstall test and 1.11's Postgres test.
- **Section 6 (API):** 1.11 (three routes, named models, examples, no request body so no `RequestModel`).
- **Section 9 (testing):** domain truth table (1.2), application scenarios (1.7, 1.8), router tests (1.11), integration (1.9, 1.11), architecture (1.1).
- **Not in this phase:** the shipped content and its contract test (Phase 2), all frontend work (Phase 3), docs (Phase 4).

**Placeholder scan:** done after writing. Three things are deliberately left for the implementer to confirm against the real code rather than guessed here: the exact `archunitpython` form (verified while planning on four module pairs), the Alembic column pairing for the `entities` JSONB default if pytest-alembic complains (the instruction says to copy `PresetModel`'s pairing), and the real database URL wiring for the Postgres end-to-end test in 1.11 (the `postgres_url` fixture already sets it). None is a hidden gap in design.

**Type consistency:** `EntityRecord` carries `label` everywhere (domain, hashing call sites, JSON mapping, API); `inspect(kind, entity_id)` has no extra parameters in the port, the adapter and the removal routine; `InstallFailedError` is a plain `Exception` in the domain, the use case and the API test.

## Execution handoff

Plan saved to `docs/superpowers/plans/2026-10-06-example-packs-phase-1-backend.md`. Phase 0 is already done and committed. Please review it, then choose an execution approach:

- **Subagent-driven:** a fresh subagent per task with a review after each. Slower and costlier, but this phase has real interface coupling between tasks (1.2 to 1.8 build on one another), so independent review catches drift.
- **Native:** I implement every task in this session and run one whole-branch review at the end.

I recommend **subagent-driven**, because Tasks 1.2 to 1.8 share many names and types and a mistake in the removal rules deletes user data.
