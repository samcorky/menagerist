# Optional links between example packs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A pack can declare `links` to another pack; the connections appear automatically while both packs are installed (either order) and are removed, never blocking, when either goes.

**Architecture:** Pack format v5 adds `links`. A link is applied after a pack finishes installing, by a small application service that resolves both ends from the two installations and creates an ordinary connection, recorded under the *declaring* pack's installation as `link:<with>:<n>`. Removal first settles other installations' links pointing at the pack being removed, then proceeds as today. No new table, no migration.

**Tech Stack:** Python 3.14 / FastAPI / SQLAlchemy backend (hexagonal, `modules/examples`), SvelteKit 5 frontend, pytest, Vitest, Playwright, `poe` tasks.

**Spec:** `docs/superpowers/specs/2026-10-14-pack-links-design.md`. Read it first; this plan implements it exactly.

## Global Constraints

- **Never create, amend, stage or push a git commit.** Every "Checkpoint" step below ends by running checks only. The user commits.
- British English in copy, comments and docs. Comments short and only where intent is unclear. Google-style docstrings.
- Backend: Python 3.14, `mypy --strict` clean (`uv run poe typecheck-backend`), ruff clean (`uv run poe lint-backend`). Domain and application layers import no framework or adapter code. Coverage floors: domain 100%, application 100%, shared_kernel 100%, adapters 80%, platform 70% (`uv run poe coverage` is the final gate).
- Test files need unique basenames (no `__init__.py` under `backend/tests`). Run backend tests from `backend/`: `uv run pytest <path> -q --no-cov`.
- Use `ExampleUnitOfWork`/`InMemory*` doubles for application tests via the `make_world` fixture in `backend/tests/modules/examples/conftest.py`. Only tests of real persistence are `@pytest.mark.integration`.
- Frontend: Svelte 5 runes; **every `.svelte` edit goes through the `svelte:svelte-file-editor` subagent**. No graph terminology (node, edge, graph) in user-visible text; say "connection" and "item". `src/lib/api/generated/` is generated (gitignored); regenerate with `uv run poe generate-frontend-client`, never edit by hand. Touch targets keep their 44 px rule.
- Pack format: versions 1 to 4 must keep loading unchanged. Pack ids and refs match `^[a-z0-9][a-z0-9-]*\Z`.
- Dependency direction `entrypoints -> adapters -> application -> domain`; architecture tests in `backend/tests/architecture/` must stay green.

## Review Focus

Failure modes the spec implies; each has a test in the task named.

1. The person deleted the item at one end of a link: skip quietly, install still succeeds (Task 4).
2. Remove the other pack then add it back: the link returns exactly once, no duplicate (Task 5).
3. An edited link survives removal of either pack and keeps the item it touches (Task 5).
4. Someone else's installations of the same packs get no links from this person's install (Task 4).
5. A link failure (target error) must not fail or roll back the pack install (Task 4).

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `backend/src/app/modules/examples/domain/pack.py` | modify | `PackLink`, `ExamplePack.links`, link validation, `link_targets`, `link_item_refs`, `PackSummary.links_with`, catalogue check |
| `backend/src/app/modules/examples/adapters/platform/pack_parser.py` | modify | version 5, `links` key |
| `backend/src/app/modules/examples/adapters/platform/file_pack_catalogue.py` | modify | validate link targets too; `links_with` in summaries |
| `backend/src/app/modules/examples/adapters/platform/in_memory_pack_catalogue.py` | modify | `links_with` in summaries |
| `backend/src/app/modules/examples/domain/installation.py` | modify | `Installation.record_late` |
| `backend/src/app/modules/examples/ports/pack_targets.py` | modify | `GraphTarget.connection_exists` |
| `backend/src/app/entrypoints/api/shared/example_targets.py` | modify | `GraphPackTarget.connection_exists` |
| `backend/src/app/modules/examples/application/pack_links.py` | create | `apply_links` |
| `backend/src/app/modules/examples/application/install_example_pack.py` | modify | apply links after install; `InstallResult.linked` |
| `backend/src/app/modules/examples/application/removal.py` | modify | `settle_records` |
| `backend/src/app/modules/examples/application/uninstall_example_pack.py` | modify | settle incoming links first |
| `backend/src/app/modules/examples/application/list_example_packs.py` | modify | `links_with` on the status |
| `backend/src/app/modules/examples/adapters/api/example/schemas.py` | modify | `links_with`, `linked` |
| `backend/src/app/modules/examples/packs/music.json` | modify | v5, relationship type + 4 links |
| `backend/src/app/modules/examples/packs/soundtracks.json` | delete | converted to links |
| `backend/src/app/modules/examples/packs/index.json` | modify | drop soundtracks |
| `frontend/src/lib/examples.ts`, `frontend/src/routes/settings/examples/+page.svelte` | modify | note and install message |
| tests | create/modify | see each task |

---

### Task 1: Domain model for links

**Files:**
- Modify: `backend/src/app/modules/examples/domain/pack.py`
- Test: `backend/tests/modules/examples/domain/test_pack_links_domain.py` (create)

**Interfaces:**
- Produces: `PackLink(with_pack: str, source_ref: str, target_ref: str, type_ref: str, attributes: dict[str, Any])`; `ExamplePack.links: tuple[PackLink, ...] = ()`; `ExamplePack.link_targets -> tuple[str, ...]`; `ExamplePack.link_item_refs() -> frozenset[tuple[str, str]]` (pack id, local ref); `PackSummary.links_with: tuple[str, ...] = ()`.

- [ ] **Step 1: Write the failing tests**

```python
"""Links between packs: what a pack may declare."""

import pytest

from app.modules.examples.domain.errors import InvalidPackError
from app.modules.examples.domain.pack import (
    ExamplePack,
    PackItem,
    PackItemType,
    PackLink,
    PackRelationshipType,
)


def _pack(*links: PackLink, requires: tuple[str, ...] = ()) -> ExamplePack:
    return ExamplePack(
        id="music",
        requires=requires,
        relationship_types=(
            PackRelationshipType(ref="tie", slug="music-tie", label="Tie"),
        ),
        item_types=(PackItemType(ref="thing", slug="music-thing", label="Thing"),),
        items=(PackItem(ref="a", type_ref="thing", name="A"),),
        links=links,
    )


def _link(**overrides: str) -> PackLink:
    fields = {
        "with_pack": "movies",
        "source_ref": "a",
        "target_ref": "movies:b",
        "type_ref": "tie",
    }
    return PackLink(**{**fields, **overrides})


def test_a_valid_link_is_accepted_and_names_its_targets() -> None:
    """The pack reports who it links with and which of their items it needs."""
    pack = _pack(_link(), _link(target_ref="movies:c"))

    assert pack.link_targets == ("movies",)
    assert pack.link_item_refs() == {("movies", "b"), ("movies", "c")}


def test_the_other_pack_can_be_either_end() -> None:
    """Direction is free."""
    _pack(_link(source_ref="movies:b", target_ref="a"))


@pytest.mark.parametrize(
    ("overrides", "requires", "message"),
    [
        ({"with_pack": "music"}, (), "cannot link with itself"),
        ({"with_pack": "movies"}, ("movies",), "which it requires"),
        ({"with_pack": "Bad Id"}, (), "lowercase letters"),
        ({"source_ref": "nope"}, (), "unknown item 'nope'"),
        ({"target_ref": "games:b"}, (), "names pack 'games', not 'movies'"),
        ({"target_ref": "a", "source_ref": "a"}, (), "must join an item of another pack"),
        (
            {"source_ref": "movies:b", "target_ref": "movies:b"},
            (),
            "cannot join an item to itself",
        ),
        ({"type_ref": "movies:tie"}, (), "unknown type"),
        ({"type_ref": "missing"}, (), "unknown type"),
    ],
)
def test_a_bad_link_is_rejected(
    overrides: dict[str, str], requires: tuple[str, ...], message: str
) -> None:
    """Every rule in the spec's Pack format section is enforced."""
    with pytest.raises(InvalidPackError, match=message):
        _pack(_link(**overrides), requires=requires)


def test_a_pack_with_no_links_has_no_targets() -> None:
    """The default is no links."""
    pack = _pack()

    assert pack.link_targets == ()
    assert pack.link_item_refs() == frozenset()
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && uv run pytest tests/modules/examples/domain/test_pack_links_domain.py -q --no-cov`
Expected: FAIL (`ImportError: cannot import name 'PackLink'`).

- [ ] **Step 3: Implement**

In `domain/pack.py`:

1. After `PackConnection`, add:

```python
@dataclass(kw_only=True, frozen=True, eq=False)
class PackLink:
    """A connection between one of this pack's items and an item of another pack.

    It exists only while both packs are installed. `source_ref` and `target_ref`
    are this pack's own refs, or `<with_pack>:<ref>` for the other pack's items.
    `type_ref` is one of this pack's own relationship types.
    """

    with_pack: str
    source_ref: str
    target_ref: str
    type_ref: str
    attributes: dict[str, Any] = field(default_factory=dict)
```

2. In `PackSummary` add `links_with: tuple[str, ...] = ()` after `requires`.
3. In `ExamplePack` add the field `links: tuple[PackLink, ...] = ()` after `requires`; in `__post_init__` call `self._check_pack_links()` right after `self._check_links()`; in `_check_limits` add `("links", len(self.links), MAX_CONNECTIONS),` to the tuple.
4. Add these members to `ExamplePack` (after `external_refs`):

```python
    @property
    def link_targets(self) -> tuple[str, ...]:
        """The distinct packs this pack links with, in first-seen order."""
        return tuple(dict.fromkeys(link.with_pack for link in self.links))

    def link_item_refs(self) -> frozenset[tuple[str, str]]:
        """Return (pack id, local ref) for every item of another pack a link names."""
        found: set[tuple[str, str]] = set()
        for link in self.links:
            for ref in (link.source_ref, link.target_ref):
                pack_id, local = split_ref(ref)
                if pack_id is not None:
                    found.add((pack_id, local))
        return frozenset(found)

    def _check_pack_links(self) -> None:
        item_refs = {i.ref for i in self.items}
        relationship_refs = {t.ref for t in self.relationship_types}
        for link in self.links:
            if not _REF.match(link.with_pack):
                raise InvalidPackError(
                    f"link pack id '{link.with_pack}' {_REF_RULE}"
                )
            if link.with_pack == self.id:
                raise InvalidPackError(f"pack '{self.id}' cannot link with itself")
            if link.with_pack in self.requires:
                raise InvalidPackError(
                    f"pack '{self.id}' links with '{link.with_pack}', which it "
                    + "requires; use a normal connection instead"
                )
            prefixed = 0
            for ref in (link.source_ref, link.target_ref):
                pack_id, local = split_ref(ref)
                if pack_id is None:
                    if local not in item_refs:
                        raise InvalidPackError(f"link has unknown item '{local}'")
                elif pack_id != link.with_pack:
                    raise InvalidPackError(
                        f"link ref '{ref}' names pack '{pack_id}', "
                        + f"not '{link.with_pack}'"
                    )
                else:
                    prefixed += 1
            if prefixed == 0:
                raise InvalidPackError("a link must join an item of another pack")
            if link.source_ref == link.target_ref:
                raise InvalidPackError("a link cannot join an item to itself")
            if link.type_ref not in relationship_refs:
                raise InvalidPackError(
                    f"link has unknown type '{link.type_ref}'; use one of this "
                    + "pack's own relationship types"
                )
```

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && uv run pytest tests/modules/examples/domain -q --no-cov`
Expected: PASS (the new file and the existing domain tests).

- [ ] **Step 5: Checkpoint**

Run: `uv run poe lint-backend && uv run poe typecheck-backend` (repo root). Expected: clean. Do not commit.

---

### Task 2: Parser, catalogue validation and summaries

**Files:**
- Modify: `adapters/platform/pack_parser.py`, `domain/pack.py` (`validate_catalogue`), `adapters/platform/file_pack_catalogue.py`, `adapters/platform/in_memory_pack_catalogue.py` (all under `backend/src/app/modules/examples/`)
- Test: `backend/tests/modules/examples/adapters/test_pack_links_catalogue.py` (create)

**Interfaces:**
- Consumes: `PackLink`, `ExamplePack.link_targets`, `ExamplePack.link_item_refs()`, `PackSummary.links_with` (Task 1).
- Produces: `parse_pack` accepts `"version": 5` and `"links": [{"with", "from", "to", "type", "attributes"?}]`; `validate_catalogue` rejects an unavailable `with` pack and a `<pack>:<ref>` that pack does not define as an item; every catalogue summary carries `links_with`.

- [ ] **Step 1: Write the failing tests**

```python
"""Parsing and validating `links`."""

from typing import Any

import pytest

from app.modules.examples.adapters.platform.in_memory_pack_catalogue import (
    InMemoryPackCatalogue,
)
from app.modules.examples.adapters.platform.pack_parser import parse_pack
from app.modules.examples.domain.errors import InvalidPackError
from app.modules.examples.domain.pack import (
    ExamplePack,
    PackItem,
    PackItemType,
    PackLink,
    PackRelationshipType,
)


def _doc(version: int = 5, **extra: Any) -> dict[str, Any]:  # noqa: ANN401
    return {
        "format": "menagerist-example-pack",
        "version": version,
        "id": "music",
        "relationship_types": [{"ref": "tie", "slug": "music-tie", "label": "Tie"}],
        "item_types": [{"ref": "thing", "slug": "music-thing", "label": "Thing"}],
        "items": [{"ref": "a", "type": "thing", "name": "A"}],
        **extra,
    }


_LINK = {"with": "movies", "from": "a", "to": "movies:b", "type": "tie"}


def test_a_version_5_pack_may_declare_links() -> None:
    """`links` parse into `PackLink`s."""
    pack = parse_pack(_doc(links=[{**_LINK, "attributes": {"n": 1}}]))

    [link] = pack.links
    assert (link.with_pack, link.source_ref, link.target_ref, link.type_ref) == (
        "movies",
        "a",
        "movies:b",
        "tie",
    )
    assert link.attributes == {"n": 1}


def test_links_need_version_5() -> None:
    """Older versions do not know the key."""
    with pytest.raises(InvalidPackError, match="links"):
        parse_pack(_doc(version=4, links=[_LINK]))


@pytest.mark.parametrize("missing", ["with", "from", "to", "type"])
def test_a_link_needs_its_four_keys(missing: str) -> None:
    """Required keys are enforced."""
    link = {k: v for k, v in _LINK.items() if k != missing}
    with pytest.raises(InvalidPackError):
        parse_pack(_doc(links=[link]))


def test_a_link_rejects_unknown_keys() -> None:
    """Strict like the rest of the format."""
    with pytest.raises(InvalidPackError):
        parse_pack(_doc(links=[{**_LINK, "colour": "red"}]))


def _movies() -> ExamplePack:
    return ExamplePack(
        id="movies",
        item_types=(PackItemType(ref="film", slug="movies-film", label="Film"),),
        items=(PackItem(ref="b", type_ref="film", name="B"),),
    )


def _music(target: str = "movies:b", with_pack: str = "movies") -> ExamplePack:
    return ExamplePack(
        id="music",
        relationship_types=(
            PackRelationshipType(ref="tie", slug="music-tie", label="Tie"),
        ),
        item_types=(PackItemType(ref="thing", slug="music-thing", label="Thing"),),
        items=(PackItem(ref="a", type_ref="thing", name="A"),),
        links=(
            PackLink(
                with_pack=with_pack, source_ref="a", target_ref=target, type_ref="tie"
            ),
        ),
    )


async def test_the_catalogue_accepts_links_and_reports_them() -> None:
    """Summaries say who each pack links with."""
    catalogue = InMemoryPackCatalogue()
    catalogue.add(_movies(), name="Movies", description="d")
    catalogue.add(_music(), name="Music", description="d")

    summaries = {s.id: s for s in await catalogue.list_packs()}

    assert summaries["music"].links_with == ("movies",)
    assert summaries["movies"].links_with == ()


def test_the_catalogue_rejects_a_link_to_a_missing_pack() -> None:
    """`with` must be a pack the catalogue has."""
    catalogue = InMemoryPackCatalogue()

    with pytest.raises(InvalidPackError, match="links with movies"):
        catalogue.add(_music(), name="Music", description="d")


def test_the_catalogue_rejects_a_link_to_an_item_the_other_pack_lacks() -> None:
    """The other end must exist in the other pack's file."""
    catalogue = InMemoryPackCatalogue()
    catalogue.add(_movies(), name="Movies", description="d")

    with pytest.raises(InvalidPackError, match="movies:nope"):
        catalogue.add(_music(target="movies:nope"), name="Music", description="d")
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && uv run pytest tests/modules/examples/adapters/test_pack_links_catalogue.py -q --no-cov`
Expected: FAIL (parser rejects `links`; no `links_with`).

- [ ] **Step 3: Implement**

`pack_parser.py`:
- Update the comment and constant: `# v4 adds requires and pack:ref references; v5 adds top-level links.` and `PACK_VERSIONS = (1, 2, 3, 4, 5)`.
- Import `PackLink`. Add `_V5_KEYS = {"links"}` beside `_V4_KEYS`.
- Add after `_parse_connection`:

```python
def _parse_link(c: Mapping[str, Any]) -> PackLink:
    _check_keys(
        c,
        required={"with", "from", "to", "type"},
        optional={"attributes"},
        where="a link",
    )
    return PackLink(
        with_pack=_str(c["with"], "with"),
        source_ref=_str(c["from"], "from"),
        target_ref=_str(c["to"], "to"),
        type_ref=_str(c["type"], "type"),
        attributes=_dict(c.get("attributes", {}), "attributes"),
    )
```
- In `parse_pack`: add `| (_V5_KEYS if root["version"] >= 5 else set())` to `optional`, and pass `links=_parse_all(root, "links", _parse_link),` to `ExamplePack(...)`.

`domain/pack.py`, end of `validate_catalogue`, after the existing external-refs loop:

```python
    for pack in packs.values():
        for target in pack.link_targets:
            if target not in packs:
                raise InvalidPackError(
                    f"pack {pack.id} links with {target}, which is not available"
                )
        for pack_id, ref in sorted(pack.link_item_refs()):
            if ref not in defined[pack_id][EntityKind.ITEM]:
                raise InvalidPackError(
                    f"pack {pack.id} links to {pack_id}:{ref}, which {pack_id} "
                    + "does not define as an item"
                )
```

`file_pack_catalogue.py`: in `_validate`, change `pending.extend(loaded[pack_id].requires)` to `pending.extend([*loaded[pack_id].requires, *loaded[pack_id].link_targets])`; in `list_packs` add `links_with=self._packs[e.id].link_targets,` to the `PackSummary(...)`.

`in_memory_pack_catalogue.py`: add `links_with=pack.link_targets,` to the `PackSummary(...)` in `list_packs`.

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && uv run pytest tests/modules/examples/adapters tests/modules/examples/domain -q --no-cov`
Expected: PASS, including the existing parser and catalogue tests (v1 to v4 packs unchanged).

- [ ] **Step 5: Checkpoint**

Run: `uv run poe lint-backend && uv run poe typecheck-backend`. Expected clean. Do not commit.

---

### Task 3: Recording late, and asking whether a connection exists

**Files:**
- Modify: `domain/installation.py`, `ports/pack_targets.py` (under `backend/src/app/modules/examples/`), `backend/src/app/entrypoints/api/shared/example_targets.py`
- Test: `backend/tests/modules/examples/domain/test_installation_record_late.py` (create), `backend/tests/modules/examples/adapters/test_graph_target_connection_exists.py` (create)

**Interfaces:**
- Produces: `Installation.record_late(kind, ref, label, entity_id, content_hash) -> None` (allowed while `INSTALLING` or `INSTALLED`); `GraphTarget.connection_exists(source_id: uuid.UUID, target_id: uuid.UUID, type_slug: str) -> bool` (true when a live connection of that type already runs from source to target).

- [ ] **Step 1: Write the failing tests**

`test_installation_record_late.py`:

```python
"""`record_late`: recording after the pack finished installing."""

import uuid

import pytest

from app.modules.examples.domain.errors import InvalidInstallationStateError
from app.modules.examples.domain.installation import (
    EntityKind,
    Installation,
    InstallationStatus,
)


def _installation(status: InstallationStatus) -> Installation:
    installation = Installation.start("music", uuid.uuid7())
    installation.status = status
    return installation


@pytest.mark.parametrize(
    "status", [InstallationStatus.INSTALLING, InstallationStatus.INSTALLED]
)
def test_record_late_works_while_installing_or_installed(
    status: InstallationStatus,
) -> None:
    """Links are recorded once the pack is installed."""
    installation = _installation(status)

    installation.record_late(
        EntityKind.CONNECTION, "link:movies:0", "A to B", uuid.uuid7(), "h"
    )

    [record] = installation.owned(EntityKind.CONNECTION)
    assert record.ref == "link:movies:0"


@pytest.mark.parametrize(
    "status", [InstallationStatus.REMOVED, InstallationStatus.FAILED]
)
def test_record_late_is_refused_once_finished_with(status: InstallationStatus) -> None:
    """A removed or failed installation takes no more records."""
    installation = _installation(status)

    with pytest.raises(InvalidInstallationStateError):
        installation.record_late(
            EntityKind.CONNECTION, "link:movies:0", "A to B", uuid.uuid7(), "h"
        )


def test_record_still_needs_installing() -> None:
    """The ordinary method is unchanged."""
    installation = _installation(InstallationStatus.INSTALLED)

    with pytest.raises(InvalidInstallationStateError):
        installation.record(EntityKind.ITEM, "a", "A", uuid.uuid7(), "h")
```

`test_graph_target_connection_exists.py` (use the `make_world` fixture; install a one-connection pack and ask):

```python
"""`GraphPackTarget.connection_exists`."""

from typing import TYPE_CHECKING

from app.entrypoints.api.shared.access_policy import OwnerAccessPolicy
from app.modules.examples.application.install_example_pack import (
    InstallExamplePack,
    InstallExamplePackCommand,
)
from app.shared_kernel.access_scope import AccessScope

if TYPE_CHECKING:
    from tests.modules.examples.conftest import MakeWorld


async def test_connection_exists_looks_at_type_and_direction(
    make_world: MakeWorld,
) -> None:
    """Only a live connection of the same type in the same direction counts."""
    world = make_world()
    await InstallExamplePack(
        world.uow,
        OwnerAccessPolicy(),
        world.catalogue,
        world.presets,
        world.graph,
        world.collections,
        world.covers,
    ).handle(InstallExamplePackCommand(pack_id="demo"), world.actor)
    [edge] = await world.graph_repos.edges.list(
        after=None, limit=10, scope=AccessScope.everyone()
    )

    assert await world.graph.connection_exists(
        edge.source_id, edge.target_id, edge.type
    )
    assert not await world.graph.connection_exists(
        edge.target_id, edge.source_id, edge.type
    )
    assert not await world.graph.connection_exists(
        edge.source_id, edge.target_id, "some-other-type"
    )
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && uv run pytest tests/modules/examples/domain/test_installation_record_late.py tests/modules/examples/adapters/test_graph_target_connection_exists.py -q --no-cov`
Expected: FAIL (`AttributeError` for both).

- [ ] **Step 3: Implement**

`domain/installation.py`: replace the body of `record` so both methods share an appender:

```python
    def record(
        self,
        kind: EntityKind,
        ref: str,
        label: str,
        entity_id: uuid.UUID,
        content_hash: str,
    ) -> None:
        """Record an entity the pack just created."""
        self._require(InstallationStatus.INSTALLING)
        self._append(kind, ref, label, entity_id, content_hash)

    def record_late(
        self,
        kind: EntityKind,
        ref: str,
        label: str,
        entity_id: uuid.UUID,
        content_hash: str,
    ) -> None:
        """Record an entity created after the install finished (a link)."""
        self._require(InstallationStatus.INSTALLING, InstallationStatus.INSTALLED)
        self._append(kind, ref, label, entity_id, content_hash)

    def _append(
        self,
        kind: EntityKind,
        ref: str,
        label: str,
        entity_id: uuid.UUID,
        content_hash: str,
    ) -> None:
        self.entities.append(
            EntityRecord(
                kind=kind,
                ref=ref,
                label=label,
                entity_id=entity_id,
                content_hash=content_hash,
            )
        )
        self.touch()
```

`ports/pack_targets.py`, in `GraphTarget` after `create_connection`:

```python
    async def connection_exists(
        self, source_id: uuid.UUID, target_id: uuid.UUID, type_slug: str
    ) -> bool:
        """Whether a live connection of `type_slug` already runs source to target."""
        ...
```

`example_targets.py`, in `GraphPackTarget` after `create_connection`:

```python
    async def connection_exists(
        self, source_id: uuid.UUID, target_id: uuid.UUID, type_slug: str
    ) -> bool:
        """Whether a live connection of `type_slug` already runs source to target."""
        async with self._stores.read() as repos:
            after: uuid.UUID | None = None
            while True:
                page = await repos.edges.list_for_node(
                    source_id, scope=self._scope, after=after, limit=_PAGE
                )
                if any(
                    e.source_id == source_id
                    and e.target_id == target_id
                    and e.type == type_slug
                    for e in page
                ):
                    return True
                if len(page) < _PAGE:
                    return False
                after = page[-1].id
```

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && uv run pytest tests/modules/examples -q --no-cov`
Expected: PASS. If another test double implements `GraphTarget` structurally, `uv run poe typecheck-backend` will name it; add `connection_exists` there.

- [ ] **Step 5: Checkpoint**

Run: `uv run poe lint-backend && uv run poe typecheck-backend`. Expected clean. Do not commit.

---

### Task 4: Applying links on install

**Files:**
- Create: `backend/src/app/modules/examples/application/pack_links.py`
- Modify: `backend/src/app/modules/examples/application/install_example_pack.py`
- Test: `backend/tests/modules/examples/application/test_pack_links.py` (create)

**Interfaces:**
- Consumes: `PackLink`, `ExamplePack.links`, `link_targets` (Task 1); `Installation.record_late`, `GraphTarget.connection_exists` (Task 3).
- Produces: `apply_links(*, declaring_pack: ExamplePack, declaring: Installation, other: Installation, graph: GraphTarget, persist: Callable[[Installation], Awaitable[None]]) -> int` (links created); `InstallResult.linked: int = 0`. A link's record is `EntityKind.CONNECTION`, ref `link:<with>:<n>`.

- [ ] **Step 1: Write the failing tests**

```python
"""Links: they appear when the second pack arrives, in either order."""

import uuid
from typing import TYPE_CHECKING

import pytest

from app.entrypoints.api.shared.access_policy import OwnerAccessPolicy
from app.modules.examples.application.install_example_pack import (
    InstallExamplePack,
    InstallExamplePackCommand,
    InstallResult,
)
from app.modules.examples.domain.installation import EntityKind, Installation, Outcome
from app.modules.examples.domain.pack import (
    ExamplePack,
    PackItem,
    PackItemType,
    PackLink,
    PackRelationshipType,
)
from app.shared_kernel.access_scope import AccessScope
from app.shared_kernel.actor import Actor

if TYPE_CHECKING:
    from tests.modules.examples.conftest import MakeWorld, World

USER_B = Actor(id=uuid.UUID(int=0xB2), roles=frozenset({"member"}))


def _side(pack_id: str, *links: PackLink) -> ExamplePack:
    title = pack_id.title()
    return ExamplePack(
        id=pack_id,
        relationship_types=(
            PackRelationshipType(
                ref="tie", slug=f"{pack_id}-tie", label="Tie", reverse_label="Tied"
            ),
        ),
        item_types=(
            PackItemType(ref="thing", slug=f"{pack_id}-thing", label=f"{title} thing"),
        ),
        items=(
            PackItem(ref="a", type_ref="thing", name=f"{title} A"),
            PackItem(ref="b", type_ref="thing", name=f"{title} B"),
        ),
        links=links,
    )


def _world(make_world: MakeWorld) -> World:
    """`music` declares one link to `movies`; `movies` declares none."""
    link = PackLink(
        with_pack="movies", source_ref="a", target_ref="movies:a", type_ref="tie"
    )
    return make_world(_side("music", link), _side("movies"))


async def _install(world: World, pack_id: str) -> InstallResult:
    return await InstallExamplePack(
        world.uow,
        OwnerAccessPolicy(),
        world.catalogue,
        world.presets,
        world.graph,
        world.collections,
        world.covers,
    ).handle(InstallExamplePackCommand(pack_id=pack_id), world.actor)


async def _pairs(world: World) -> set[tuple[str, str]]:
    names = {
        n.id: n.name
        for n in await world.graph_repos.nodes.list(
            scope=AccessScope.everyone(), after=None, limit=50
        )
    }
    edges = await world.graph_repos.edges.list(
        after=None, limit=50, scope=AccessScope.everyone()
    )
    return {(names[e.source_id], names[e.target_id]) for e in edges}


async def _installation(world: World, pack_id: str) -> Installation:
    found = await world.installations.get_active_for_pack(
        pack_id, scope=AccessScope.everyone()
    )
    assert found is not None
    return found


@pytest.mark.parametrize(("first", "second"), [("music", "movies"), ("movies", "music")])
async def test_links_appear_when_the_second_pack_arrives(
    make_world: MakeWorld, first: str, second: str
) -> None:
    """Either order gives the same connection, recorded under the declaring pack."""
    world = _world(make_world)

    await _install(world, first)
    assert await _pairs(world) == set()
    result = await _install(world, second)

    assert await _pairs(world) == {("Music A", "Movies A")}
    assert result.linked == 1
    assert result.created.connections == 0  # the pack's own content only
    [record] = (await _installation(world, "music")).owned(EntityKind.CONNECTION)
    assert record.ref == "link:movies:0"
    assert record.label == "Music A to Movies A"
    assert (await _installation(world, "movies")).owned(EntityKind.CONNECTION) == []


async def test_a_pack_with_no_partner_installed_links_nothing(
    make_world: MakeWorld,
) -> None:
    """Links wait for the other pack."""
    world = _world(make_world)

    result = await _install(world, "music")

    assert result.linked == 0
    assert await _pairs(world) == set()


async def test_a_deleted_endpoint_skips_the_link_quietly(
    make_world: MakeWorld,
) -> None:
    """The person deleted Movies A before Music arrived: no link, no error."""
    world = _world(make_world)
    await _install(world, "movies")
    movies_a = next(
        n
        for n in await world.graph_repos.nodes.list(
            scope=AccessScope.everyone(), after=None, limit=50
        )
        if n.name == "Movies A"
    )
    movies_a.soft_delete()
    await world.graph_repos.nodes.save(movies_a)

    result = await _install(world, "music")

    assert result.linked == 0
    assert (await _installation(world, "music")).status.value == "installed"
    assert await _pairs(world) == set()


async def test_a_failing_link_does_not_fail_the_install(
    make_world: MakeWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pack is installed; the link is logged and skipped."""
    world = _world(make_world)
    await _install(world, "music")

    async def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("link boom")

    monkeypatch.setattr(world.graph, "create_connection", boom)

    result = await _install(world, "movies")

    assert result.linked == 0
    assert (await _installation(world, "movies")).status.value == "installed"
    assert await _pairs(world) == set()


async def test_another_persons_installations_are_left_alone(
    make_world: MakeWorld,
) -> None:
    """One person installing a pack never links into someone else's."""
    world = _world(make_world)
    await _install(world, "music")

    other = world.as_actor(USER_B)
    result = await _install(other, "movies")

    assert result.linked == 0
    assert await _pairs(world) == set()
    music = await _installation(world, "music")
    assert all(r.outcome is Outcome.OWNED for r in music.entities)
```

Note: `world.graph_repos.edges.delete` and `nodes.delete` must exist on the in-memory repositories; if the repository only has `save` with a soft-delete flag, set `deleted_at` and `save` instead (mirror how `test_uninstall_example_pack.py` deletes a node, search that file for `deleted`). Adjust the test, not the production code.

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && uv run pytest tests/modules/examples/application/test_pack_links.py -q --no-cov`
Expected: FAIL (`ModuleNotFoundError: pack_links`, `InstallResult` has no `linked`).

- [ ] **Step 3: Implement**

Create `application/pack_links.py`:

```python
import uuid
from typing import TYPE_CHECKING

import structlog

from app.modules.examples.application.content_hash import content_hash
from app.modules.examples.domain.installation import (
    EntityKind,
    Installation,
)
from app.modules.examples.domain.pack import ExamplePack, PackConnection, split_ref

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from app.modules.examples.domain.pack import PackLink
    from app.modules.examples.ports.pack_targets import GraphTarget

logger = structlog.get_logger()


def link_ref(with_pack: str, index: int) -> str:
    """Return the record ref of the `index`th link, which removal matches by prefix."""
    return f"link:{with_pack}:{index}"


async def apply_links(
    *,
    declaring_pack: ExamplePack,
    declaring: Installation,
    other: Installation,
    graph: GraphTarget,
    persist: Callable[[Installation], Awaitable[None]],
) -> int:
    """Create the links `declaring_pack` declares with the pack `other` installed.

    Each link is an ordinary connection, recorded in `declaring`. A link is skipped,
    quietly, when an end no longer exists, when it was already applied, or when the
    same connection is already there. A failure is logged and the link skipped: the
    packs themselves are installed and links are optional.

    Returns:
        How many links were created.
    """
    created = 0
    for index, link in enumerate(declaring_pack.links):
        if link.with_pack != other.pack_id:
            continue
        try:
            if await _apply_one(
                declaring_pack, declaring, other, link, index, graph, persist
            ):
                created += 1
        except Exception:
            logger.exception(
                "example pack link failed",
                pack_id=declaring_pack.id,
                with_pack=link.with_pack,
                link=index,
            )
    return created


async def _apply_one(
    pack: ExamplePack,
    declaring: Installation,
    other: Installation,
    link: PackLink,
    index: int,
    graph: GraphTarget,
    persist: Callable[[Installation], Awaitable[None]],
) -> bool:
    ref = link_ref(link.with_pack, index)
    if any(r.ref == ref for r in declaring.owned(EntityKind.CONNECTION)):
        return False
    source = await _end(link.source_ref, declaring, other, graph)
    target = await _end(link.target_ref, declaring, other, graph)
    if source is None or target is None:
        return False
    slug = next(t.slug for t in pack.relationship_types if t.ref == link.type_ref)
    if await graph.connection_exists(source[0], target[0], slug):
        return False
    created = await graph.create_connection(
        PackConnection(
            source_ref=link.source_ref,
            target_ref=link.target_ref,
            type_ref=link.type_ref,
            attributes=link.attributes,
        ),
        source_id=source[0],
        target_id=target[0],
        type_slug=slug,
    )
    declaring.record_late(
        EntityKind.CONNECTION,
        ref,
        f"{source[1]} to {target[1]}",
        created.entity_id,
        content_hash(created.content),
    )
    await persist(declaring)
    return True


async def _end(
    ref: str, declaring: Installation, other: Installation, graph: GraphTarget
) -> tuple[uuid.UUID, str] | None:
    """Return the live item's id and name behind a link end, or None if it is gone."""
    pack_id, local = split_ref(ref)
    installation = declaring if pack_id is None else other
    record = next(
        (r for r in installation.owned(EntityKind.ITEM) if r.ref == local), None
    )
    if record is None:
        return None
    found = await graph.inspect(EntityKind.ITEM, record.entity_id)
    if found is None:
        return None
    return record.entity_id, str(found.content["name"])
```

Check that `_node_content` (in `example_targets.py`) includes a `"name"` key; it does for items (`resolve_external_refs` reads `inspection.content.get("name")`).

`install_example_pack.py`:
- Add `linked: int = 0` to `InstallResult` (last field).
- Import `apply_links` from `app.modules.examples.application.pack_links` and `InstallationStatus` from `domain.installation`.
- In `handle`, replace the tail (from `installation.mark_installed()`) with:

```python
        installation.mark_installed()
        await self._persist(installation)
        created = _counts(
            r.kind
            for r in installation.entities
            if (r.kind, r.ref) not in run.adopted
        )
        linked = await self._apply_links(pack, installation, scope)
        logger.info(
            "example pack installed",
            pack_id=pack.id,
            entities=len(installation.entities),
            linked=linked,
        )
        return InstallResult(
            pack_id=pack.id,
            created=created,
            adopted=_counts(kind for kind, _ in run.adopted),
            linked=linked,
        )
```
- Add the method (next to `_check_not_installed`):

```python
    async def _apply_links(
        self, pack: ExamplePack, installation: Installation, scope: AccessScope
    ) -> int:
        """Apply this pack's links and other packs' links that point at it."""
        async with self._uow as repos:
            active = await repos.installations.list_active(scope=scope)
        finished = {
            i.pack_id: i for i in active if i.status is InstallationStatus.INSTALLED
        }
        linked = 0
        for target in pack.link_targets:
            if target in finished:
                linked += await apply_links(
                    declaring_pack=pack,
                    declaring=installation,
                    other=finished[target],
                    graph=self._graph,
                    persist=self._persist,
                )
        for other in finished.values():
            if other.id == installation.id:
                continue
            declaring_pack = await self._catalogue.get(other.pack_id)
            if declaring_pack is not None and pack.id in declaring_pack.link_targets:
                linked += await apply_links(
                    declaring_pack=declaring_pack,
                    declaring=other,
                    other=installation,
                    graph=self._graph,
                    persist=self._persist,
                )
        return linked
```

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && uv run pytest tests/modules/examples -q --no-cov`
Expected: PASS (new tests and every existing install test, since `linked` defaults to 0).

- [ ] **Step 5: Checkpoint**

Run: `uv run poe lint-backend && uv run poe typecheck-backend`. Expected clean. Do not commit.

---

### Task 5: Removing links

**Files:**
- Modify: `backend/src/app/modules/examples/application/removal.py`, `backend/src/app/modules/examples/application/uninstall_example_pack.py`
- Test: `backend/tests/modules/examples/application/test_pack_links.py` (append; it already has the `_side`, `_world`, `_install`, `_pairs` and `_installation` helpers from Task 4)

**Interfaces:**
- Consumes: `Installation.owned`; the `link:<with>:<n>` record refs from Task 4.
- Produces: `settle_records(installation, records, *, presets, graph, collections, covers, persist) -> list[KeptEntity]` in `removal.py`; `UninstallExamplePack` removes (or keeps, if edited) links other installations of the same person recorded `with` the pack being removed, before settling the pack's own entities.

- [ ] **Step 1: Write the failing tests**

At the top of `test_pack_links.py` add these imports (merge with the existing ones):

```python
from app.modules.examples.application.uninstall_example_pack import (
    UninstallExamplePack,
    UninstallExamplePackCommand,
    UninstallResult,
)
from app.modules.examples.domain.removal import KEEP_EDITED
```

Then append:

```python
async def _uninstall(world: World, pack_id: str) -> UninstallResult:
    return await UninstallExamplePack(
        world.uow,
        OwnerAccessPolicy(),
        world.catalogue,
        world.presets,
        world.graph,
        world.collections,
        world.covers,
    ).handle(UninstallExamplePackCommand(pack_id=pack_id), world.actor)


async def test_removing_the_other_pack_removes_the_link(make_world: MakeWorld) -> None:
    """Removal is not refused, and the declaring pack stays installed."""
    world = _world(make_world)
    await _install(world, "music")
    await _install(world, "movies")

    await _uninstall(world, "movies")

    assert await _pairs(world) == set()
    music = await _installation(world, "music")
    assert music.owned(EntityKind.CONNECTION) == []


async def test_the_link_returns_exactly_once_when_the_pack_is_added_back(
    make_world: MakeWorld,
) -> None:
    """Remove and re-add: one connection, not two."""
    world = _world(make_world)
    await _install(world, "music")
    await _install(world, "movies")
    await _uninstall(world, "movies")

    again = await _install(world, "movies")

    assert again.linked == 1
    assert await _pairs(world) == {("Music A", "Movies A")}


async def test_removing_the_declaring_pack_removes_the_link(
    make_world: MakeWorld,
) -> None:
    """Its own links go with the rest of its connections."""
    world = _world(make_world)
    await _install(world, "music")
    await _install(world, "movies")

    await _uninstall(world, "music")

    assert await _pairs(world) == set()
    names = {
        n.name
        for n in await world.graph_repos.nodes.list(
            scope=AccessScope.everyone(), after=None, limit=50
        )
    }
    assert names == {"Movies A", "Movies B"}


@pytest.mark.parametrize("remove", ["movies", "music"])
async def test_an_edited_link_is_kept_and_keeps_its_item(
    make_world: MakeWorld, remove: str
) -> None:
    """Editing the link makes it the person's: it stays, and so does the item."""
    world = _world(make_world)
    await _install(world, "music")
    await _install(world, "movies")
    [edge] = await world.graph_repos.edges.list(
        after=None, limit=10, scope=AccessScope.everyone()
    )
    edge.attributes = {"note": "mine"}
    await world.graph_repos.edges.save(edge)

    removed = await _uninstall(world, remove)

    assert (EntityKind.CONNECTION, KEEP_EDITED) in {
        (k.kind, k.reason) for k in removed.kept
    }
    assert await _pairs(world) == {("Music A", "Movies A")}


async def test_a_kept_link_is_not_duplicated_when_the_pack_comes_back(
    make_world: MakeWorld,
) -> None:
    """The kept connection already satisfies the link."""
    world = _world(make_world)
    await _install(world, "music")
    await _install(world, "movies")
    [edge] = await world.graph_repos.edges.list(
        after=None, limit=10, scope=AccessScope.everyone()
    )
    edge.attributes = {"note": "mine"}
    await world.graph_repos.edges.save(edge)
    await _uninstall(world, "movies")

    again = await _install(world, "movies")

    assert again.linked == 0
    assert len(await _pairs(world)) == 1


async def test_nothing_is_refused_in_either_order(make_world: MakeWorld) -> None:
    """Links never block removal."""
    world = _world(make_world)
    await _install(world, "movies")
    await _install(world, "music")

    await _uninstall(world, "movies")
    await _uninstall(world, "music")

    assert await _pairs(world) == set()
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && uv run pytest tests/modules/examples/application/test_pack_links.py -q --no-cov`
Expected: FAIL (removing `movies` leaves the link, then item removal refuses or keeps).

- [ ] **Step 3: Implement**

`removal.py`: add after `settle_installation`:

```python
async def settle_records(
    installation: Installation,
    records: Sequence[EntityRecord],
    *,
    presets: PresetTarget,
    graph: GraphTarget,
    collections: CollectionTarget,
    covers: CoverTarget,
    persist: Callable[[Installation], Awaitable[None]],
) -> list[KeptEntity]:
    """Remove or keep just `records` of `installation`, then save it once."""
    kept: list[KeptEntity] = []
    for record in records:
        reason = await _settle_one(
            installation,
            record,
            presets=presets,
            graph=graph,
            collections=collections,
            covers=covers,
            types_shared=False,
        )
        if reason is not None:
            kept.append(
                KeptEntity(
                    kind=record.kind, ref=record.ref, label=record.label, reason=reason
                )
            )
    await persist(installation)
    return kept
```
and add `from collections.abc import Awaitable, Callable, Sequence` under `TYPE_CHECKING` (extend the existing import there).

`uninstall_example_pack.py`:
- Import `settle_records` from `removal` and `link_ref` is not needed; use the prefix directly.
- In `handle`, immediately before `history = await self._pack_history(...)`, add:

```python
        link_kept = await self._settle_incoming_links(
            command.pack_id, installation, active
        )
```
- After `kept = await settle_installation(...)`, add `kept = [*link_kept, *kept]`.
- Add the method:

```python
    async def _settle_incoming_links(
        self, pack_id: str, removing: Installation, active: list[Installation]
    ) -> list[KeptEntity]:
        """Settle links other packs hold with `pack_id`, before its items go."""
        prefix = f"link:{pack_id}:"
        kept: list[KeptEntity] = []
        for other in active:
            if other.id == removing.id:
                continue
            records = [
                r for r in other.owned(EntityKind.CONNECTION) if r.ref.startswith(prefix)
            ]
            if records:
                kept += await settle_records(
                    other,
                    records,
                    presets=self._presets,
                    graph=self._graph,
                    collections=self._collections,
                    covers=self._covers,
                    persist=self._persist,
                )
        return kept
```
The `active` list was read earlier in `handle` (`repos.installations.list_active(scope=scope)`), so it is the same person's installations only.

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && uv run pytest tests/modules/examples -q --no-cov`
Expected: PASS, existing uninstall tests unchanged.

- [ ] **Step 5: Checkpoint**

Run: `uv run poe lint-backend && uv run poe typecheck-backend`. Expected clean. Do not commit.

---

### Task 6: API fields and the generated client

**Files:**
- Modify: `application/list_example_packs.py`, `adapters/api/example/schemas.py` (under `backend/src/app/modules/examples/`)
- Test: `backend/tests/modules/examples/adapters/test_example_router.py` (modify) and `backend/tests/modules/examples/application/test_list_example_packs.py` (modify)

**Interfaces:**
- Produces: `ExamplePackStatus.links_with: tuple[PackSummary, ...] = ()`; `ExamplePackResponse.links_with: list[PackRefResponse]`; `InstallResultResponse.linked: int`.

- [ ] **Step 1: Write the failing tests**

In `test_list_example_packs.py` add the imports `from app.modules.examples.domain.pack import ExamplePack, PackItem, PackItemType, PackLink, PackRelationshipType` and this helper and test:

```python
def _linking_packs() -> tuple[ExamplePack, ExamplePack]:
    """`music` links with `movies`; each has one item type and two items."""

    def side(pack_id: str, *links: PackLink) -> ExamplePack:
        return ExamplePack(
            id=pack_id,
            relationship_types=(
                PackRelationshipType(ref="tie", slug=f"{pack_id}-tie", label="Tie"),
            ),
            item_types=(
                PackItemType(ref="thing", slug=f"{pack_id}-thing", label="Thing"),
            ),
            items=(PackItem(ref="a", type_ref="thing", name=f"{pack_id} A"),),
            links=links,
        )

    link = PackLink(
        with_pack="movies", source_ref="a", target_ref="movies:a", type_ref="tie"
    )
    return side("music", link), side("movies")


async def test_a_pack_lists_the_packs_it_links_with(make_world: MakeWorld) -> None:
    """`links_with` carries the other packs' names, not only their ids."""
    world = make_world(*_linking_packs())

    result = await ListExamplePacks(
        ExampleRepos(installations=world.installations),
        OwnerAccessPolicy(),
        world.catalogue,
    ).handle(ListExamplePacksQuery(), world.actor)

    by_id = {s.summary.id: s for s in result}
    assert [p.id for p in by_id["music"].links_with] == ["movies"]
    assert by_id["movies"].links_with == ()
```

In `test_example_router.py` add (it already imports `ExamplePack`, `PackItem`, `PackItemType`; add `PackLink` and `PackRelationshipType` to its `domain.pack` import, and copy the `_linking_packs` helper above into the file under that name):

```python
def test_links_show_in_the_list_and_the_install_result(make_world: MakeWorld) -> None:
    """`links_with` names the partner; `linked` counts the connections made."""
    client = _client(make_world(*_linking_packs()))

    listed = {p["id"]: p for p in client.get("/api/v1/example").json()}
    assert listed["music"]["links_with"] == [{"id": "movies", "name": "Movies"}]
    assert listed["movies"]["links_with"] == []

    first = client.put("/api/v1/example/music/installation").json()
    second = client.put("/api/v1/example/movies/installation").json()
    assert (first["linked"], second["linked"]) == (0, 1)
```
(The test file's `_client(world)` helper is the one used by the add-on tests in that file; the in-memory catalogue names a pack by its title-cased id unless `make_world` says otherwise, so "movies" lists as "Movies" like "base" lists as "Base" in the existing add-on test.)

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && uv run pytest tests/modules/examples/application/test_list_example_packs.py tests/modules/examples/adapters/test_example_router.py -q --no-cov`
Expected: FAIL (no `links_with`, no `linked`).

- [ ] **Step 3: Implement**

`list_example_packs.py`: add `links_with: tuple[PackSummary, ...] = ()` to `ExamplePackStatus` and, in the list comprehension, `links_with=tuple(by_id[r] for r in s.links_with if r in by_id),`.

`schemas.py`:
- In `ExamplePackResponse` add (after `required_by`):

```python
    links_with: list[PackRefResponse] = Field(
        default=[],
        description=(
            "Sets this one connects to automatically when both are added. "
            "They never block adding or removing."
        ),
    )
```
and, in `from_status`, `links_with=[PackRefResponse.from_summary(r) for r in status.links_with],`; add `"links_with": [],` to the `json_schema_extra` example.
- In `InstallResultResponse` add `linked: int = Field(default=0, description="Connections to other added sets this install created, in either set.")` and `linked=result.linked` in `from_domain`; add `"linked": 0` to its example.

Also extend the `PUT /example/{pack_id}/installation` description in `router.py` (near line 102) with one sentence: "`linked` counts connections to other added sets that were created because of this install."

- [ ] **Step 4: Run to verify pass, regenerate the client**

Run: `cd backend && uv run pytest tests/modules/examples -q --no-cov` → PASS.
Run (repo root): `uv run poe generate-frontend-client` → the generated types gain `links_with` and `linked`. `git status` must show no tracked change under `frontend/src/lib/api/generated/` (it is gitignored) and none to `openapi.json` (untracked).

- [ ] **Step 5: Checkpoint**

Run: `uv run poe lint-backend && uv run poe typecheck-backend`. Expected clean. Do not commit.

---

### Task 7: Shipped content (Music links, soundtracks removed)

**Files:**
- Modify: `backend/src/app/modules/examples/packs/music.json`, `packs/index.json`, `backend/README.md`, `docs/DECISIONS.md`
- Delete: `backend/src/app/modules/examples/packs/soundtracks.json`
- Modify tests: `backend/tests/modules/examples/application/test_shipped_add_ons.py`, `test_shipped_packs.py` (counts if asserted)

**Interfaces:**
- Consumes: parser v5 (Task 2), install and removal (Tasks 4 and 5).
- Produces: shipped `music` pack at version 5 with the relationship type `music-soundtrack-of` and four links with `movies`; no `soundtracks` pack.

- [ ] **Step 1: Write the failing test**

Replace the soundtracks tests in `test_shipped_add_ons.py` with (keep the `games-extras` tests as they are; look at the existing soundtracks test to see which helper names it uses and delete only it):

```python
async def test_music_and_movies_link_their_soundtracks(make_world: MakeWorld) -> None:
    """Adding both shipped packs, in either order, connects records to films."""
    for first, second in (("music", "movies"), ("movies", "music")):
        world = _world(make_world)
        await _install(world, first)
        result = await _install(world, second)

        assert result.linked == 4
        edges = await _edges(world)
        assert ("Night Drive", "Cold Harbour", "music-soundtrack-of") in edges
        assert ("Thirteen Bells", "Marmalade", "music-soundtrack-of") in edges

        await _uninstall(world, "movies")
        assert not [e for e in await _edges(world) if e[2] == "music-soundtrack-of"]
        await _uninstall(world, "music")
        assert await _live(world) == 0
```
(Use the file's own `_edges` and `_live` helpers; if `_live` counts something else, assert that everything is gone the same way the existing games-extras test does. Names `Thirteen Bells` and `Marmalade` are the item `name`s of refs `thirteen-bells` and `marmalade`; open the two pack files and use their real names.)

Also add to `tests/modules/examples/application/test_shipped_packs.py` (or the existing catalogue test there) an assertion that `FilePackCatalogue().list_packs()` has no pack with id `soundtracks` and that the `music` summary has `links_with == ("movies",)`.

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && uv run pytest tests/modules/examples/application/test_shipped_add_ons.py tests/modules/examples/application/test_shipped_packs.py -q --no-cov`
Expected: FAIL.

- [ ] **Step 3: Implement**

`music.json`:
- Set `"version": 5`.
- Append to `relationship_types`:

```json
{
  "ref": "soundtrack-of",
  "slug": "music-soundtrack-of",
  "label": "Soundtrack of",
  "reverse_label": "Soundtrack",
  "description": "Which film a record is the soundtrack of.",
  "directional": true
}
```
- Add a top-level `"links"` array (after `connections`/`collections`, matching the file's key order):

```json
"links": [
  { "with": "movies", "from": "night-drive", "to": "movies:cold-harbour", "type": "soundtrack-of" },
  { "with": "movies", "from": "paper-lanterns", "to": "movies:the-night-bus-sessions", "type": "soundtrack-of" },
  { "with": "movies", "from": "salt-marsh-sessions", "to": "movies:quiet-hours", "type": "soundtrack-of" },
  { "with": "movies", "from": "thirteen-bells", "to": "movies:marmalade", "type": "soundtrack-of" }
]
```
Format the file the way the others are formatted (run `uv run poe format` if it covers JSON, otherwise match indentation by hand).

Delete `packs/soundtracks.json`; remove its entry from `packs/index.json`.

Docs: in `backend/README.md` replace the sentence naming the `soundtracks` add-on with a sentence about links (Music declares its soundtrack links to Movies). In `docs/DECISIONS.md`, amend the add-on entry's line that says two add-ons ship (`games-extras` and `soundtracks`): say one add-on ships (`games-extras`) and the soundtrack connections are links declared by Music, with a pointer to the new entry added in Task 9.

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && uv run pytest tests/modules/examples -q --no-cov` → PASS (parser accepts the shipped files; `validate_catalogue` accepts the links).

- [ ] **Step 5: Checkpoint**

Run: `uv run poe lint-backend && uv run poe typecheck-backend`. Expected clean. Do not commit.

---

### Task 8: Frontend text (note and install message)

**Files:**
- Modify: `frontend/src/lib/examples.ts`, `frontend/tests/examples.test.ts`
- Modify (via the Svelte editor agent): `frontend/src/routes/settings/examples/+page.svelte`

**Interfaces:**
- Consumes: generated types with `links_with` and `linked` (Task 6).
- Produces: `linksNote(pack: PackLinks): string | null` returning `Also connects to Movies when both are added` (null when none); `describeInstall` mentions links.

- [ ] **Step 1: Write the failing tests** (in `frontend/tests/examples.test.ts`, import `linksNote`)

```ts
describe('linksNote', () => {
	const movies = { id: 'movies', name: 'Movies' };
	const music = { id: 'music', name: 'Music' };

	it('is null for a pack with no links', () => {
		expect(linksNote({})).toBeNull();
		expect(linksNote({ links_with: [] })).toBeNull();
	});

	it('names the packs it connects to', () => {
		expect(linksNote({ links_with: [movies] })).toBe('Also connects to Movies when both are added');
		expect(linksNote({ links_with: [movies, music] })).toBe(
			'Also connects to Movies and Music when both are added'
		);
	});
});

describe('describeInstall with links', () => {
	it('mentions connections made to other examples', () => {
		expect(
			describeInstall({ pack_id: 'movies', created: zero, adopted: zero, linked: 4 })
		).toBe('Examples added. 4 connections to your other examples were made.');
		expect(
			describeInstall({ pack_id: 'movies', created: zero, adopted: zero, linked: 1 })
		).toBe('Examples added. 1 connection to your other examples was made.');
	});

	it('keeps the existing messages when nothing was linked', () => {
		expect(describeInstall({ pack_id: 'music', created: zero, adopted: zero, linked: 0 })).toBe(
			'Examples added'
		);
	});
});
```
Existing `describeInstall` tests pass objects without `linked`; update them to include `linked: 0` where the generated type now requires it.

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && npx vitest run tests/examples.test.ts`
Expected: FAIL (no `linksNote`; message lacks links).

- [ ] **Step 3: Implement**

`examples.ts`:
- Extend the type: `type PackLinks = { requires?: PackRef[]; required_by?: PackRef[]; links_with?: PackRef[] };`
- Add after `addOnNote`:

```ts
/** "Also connects to Movies when both are added"; null for a pack with no links. */
export function linksNote(pack: PackLinks): string | null {
	const links = pack.links_with ?? [];
	return links.length === 0
		? null
		: `Also connects to ${joinNames(links.map(refName))} when both are added`;
}
```
- Change `describeInstall` to:

```ts
export function describeInstall(result: InstallResultResponse): string {
	const adopted = describeCounts(result.adopted);
	const linked = result.linked
		? ` ${plural(result.linked, 'connection', 'connections')} to your other examples ${result.linked === 1 ? 'was' : 'were'} made.`
		: '';
	if (!adopted) return linked ? `Examples added.${linked}` : 'Examples added';
	const total = Object.values(result.adopted).reduce((sum, n) => sum + n, 0);
	return `Examples added. ${adopted} you'd kept ${total === 1 ? 'was' : 'were'} already here.${linked}`;
}
```

`+page.svelte`: dispatch the `svelte:svelte-file-editor` subagent with this instruction: "In `frontend/src/routes/settings/examples/+page.svelte`, import `linksNote` from `$lib/examples` and, inside the card content directly after the existing `{#if note}…{/if}` block, render `const lnote = linksNote(pack)` as `<p class="mb-1">{lnote}</p>` when non-null. Do not change anything else. Run `uv run poe lint-frontend`, `uv run poe typecheck-frontend`, `uv run poe test-frontend` and report results."

- [ ] **Step 4: Run to verify pass**

Run (repo root): `uv run poe lint-frontend && uv run poe typecheck-frontend && uv run poe test-frontend`
Expected: all pass.

- [ ] **Step 5: Checkpoint**

Do not commit.

---

### Task 9: End-to-end tests, helpers, docs, final gates

**Files:**
- Modify: `frontend/tests/e2e/examples-helpers.ts`, `frontend/tests/e2e/helpers.ts`, `frontend/tests/e2e/examples-add-ons.spec.ts`
- Create: `frontend/tests/e2e/examples-links.spec.ts`
- Modify: `docs/DECISIONS.md`, `docs/superpowers/specs/2026-10-14-pack-links-design.md` (status line)

- [ ] **Step 1: Update helpers and the add-on spec**

- `helpers.ts`: remove `'soundtracks'` from `EXAMPLE_PACK_IDS` and from the `EXAMPLE_SLUG_PREFIXES` regexp (the type slug is now `music-soundtrack-of`, already matched by `music-`).
- `examples-helpers.ts`: delete the `SOUNDTRACKS` export.
- `examples-add-ons.spec.ts`: delete the `SOUNDTRACKS` import and the whole "a bridge add-on needs both packs…" test (its behaviour moves to the new spec).

- [ ] **Step 2: Write the new e2e spec** `examples-links.spec.ts` (model it on `examples-add-ons.spec.ts`: same imports, `test.describe.configure({ mode: 'serial' })`, `exampleData()` cleanup in `beforeEach` and `afterEach`):

```ts
import { test, expect } from './fixtures';
import {
	MOVIES,
	MUSIC,
	exampleData,
	install,
	nodeNamed,
	packCard,
	remove
} from './examples-helpers';

test.describe.configure({ mode: 'serial' });

const { cleanUp } = exampleData();

test.beforeEach(({ request }) => cleanUp(request));
test.afterEach(({ request }) => cleanUp(request));

test('music and movies connect themselves, in either order, and nothing blocks removal', async ({
	page,
	request
}) => {
	await page.goto('/settings/examples');
	await expect(packCard(page, 'Music: records, gigs and friends')).toContainText(
		'Also connects to Movies when both are added'
	);

	await install(page, MUSIC);
	await install(page, MOVIES);

	const film = await nodeNamed(request, 'Cold Harbour');
	await page.goto(`/items/${film.id}`);
	await expect(page.getByText('Soundtrack', { exact: true }).first()).toBeVisible();
	await page.getByRole('link', { name: 'Night Drive' }).first().click();
	await expect(page.getByText('Soundtrack of', { exact: true }).first()).toBeVisible();

	await page.goto('/settings/examples');
	await remove(page, MOVIES);
	const record = await nodeNamed(request, 'Night Drive');
	await page.goto(`/items/${record.id}`);
	await expect(page.getByText('Soundtrack of', { exact: true })).toHaveCount(0);

	await page.goto('/settings/examples');
	await install(page, MOVIES);
	await page.goto(`/items/${record.id}`);
	await expect(page.getByText('Soundtrack of', { exact: true }).first()).toBeVisible();
});
```
(Use the real exported constant names from `examples-helpers.ts`: it exports `GAMES`, `GAMES_EXTRAS`, `MOVIES`; add `export const MUSIC = /^Music/;` beside them if it does not exist, matching the existing regexp style. The pack card title for Music is "Music: records, gigs and friends".)

- [ ] **Step 3: Run the examples specs**

Run (repo root): the repo runner has no spec filter, so run its steps for one worker: `E2E_WORKERS=1 uv run poe sync-backend && uv run poe e2e-db-up && uv run poe e2e-build && uv run poe e2e-migrate && (cd frontend && E2E_WORKERS=1 npx playwright test tests/e2e/examples-links.spec.ts tests/e2e/examples-add-ons.spec.ts --workers=1); uv run poe e2e-db-down`
Expected: all pass.

- [ ] **Step 4: Documentation**

- `docs/DECISIONS.md`: add a section "Optional links between example packs (2026-10-14)" after the existing add-on packs section, recording: pack format v5 `links`; links recorded under the declaring pack's installation as `link:<with>:<n>` connections; applied after install in either order for the same person only; skip-if-exists and quiet skips; removal settles incoming links first and never blocks; edited links kept; `soundtracks` converted into Music's links; the known limit (two simultaneous installs could duplicate a link); the choice between `requires` and `links`.
- Spec status line: change "awaiting written-spec review. No code yet." to "implemented (see the plan `2026-10-14-pack-links.md`)".

- [ ] **Step 5: Final gates**

Run (repo root, in this order):
1. `uv run poe lint && uv run poe typecheck && uv run poe test-frontend`
2. `uv run poe coverage` (backend full suite plus coverage floors; takes about 7 minutes).
Expected: all green and the floors met. Do not commit; report the results and list the changed files for the user to review and commit.
