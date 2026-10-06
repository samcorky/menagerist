"""Contract every pack in `app/modules/examples/packs/` must meet.

Adding a pack to `index.json` adds it to these tests automatically.
"""

import json
import re
from dataclasses import asdict
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from app.modules.examples.adapters.platform.file_pack_catalogue import FilePackCatalogue
from app.modules.examples.adapters.platform.pack_parser import parse_index
from app.modules.examples.application.install_example_pack import (
    InstallExamplePack,
    InstallExamplePackCommand,
)
from app.modules.examples.application.uninstall_example_pack import (
    UninstallExamplePack,
    UninstallExamplePackCommand,
)
from app.modules.examples.domain.pack import ExamplePack, preset_refs
from app.shared_kernel.actor import SYSTEM_ACTOR

if TYPE_CHECKING:
    from collections.abc import Iterator

    from tests.modules.examples.conftest import MakeWorld, World

_PACK_IDS = [
    entry.id
    for entry in parse_index(
        json.loads(
            (
                Path(str(files("app.modules.examples"))) / "packs" / "index.json"
            ).read_text(encoding="utf-8")
        )
    )
]
_LIMIT = 1000
_AMERICAN = re.compile(
    r"\b(color|favorite|organize|center|theater|gray|realize|honor)(s|d|ed|ing)?\b",
    re.IGNORECASE,
)


async def _load(pack_id: str) -> ExamplePack:
    pack = await FilePackCatalogue().get(pack_id)
    assert pack is not None, f"{pack_id}: the index lists it but it did not load"
    return pack


async def _install(world: World, pack_id: str) -> Any:  # noqa: ANN401
    return await InstallExamplePack(
        world.uow, world.catalogue, world.presets, world.graph
    ).handle(InstallExamplePackCommand(pack_id=pack_id), SYSTEM_ACTOR)


async def _uninstall(world: World, pack_id: str) -> Any:  # noqa: ANN401
    return await UninstallExamplePack(world.uow, world.presets, world.graph).handle(
        UninstallExamplePackCommand(pack_id=pack_id), SYSTEM_ACTOR
    )


async def _live_counts(world: World) -> list[int]:
    repos = (
        world.graph_repos.node_types,
        world.graph_repos.nodes,
        world.graph_repos.edge_types,
        world.graph_repos.edges,
        world.preset_repos.presets,
    )
    return [len(await repo.list(after=None, limit=_LIMIT)) for repo in repos]


def _strings(value: Any) -> Iterator[str]:  # noqa: ANN401
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _strings(v)


def _texts(pack: ExamplePack) -> Iterator[tuple[str, str]]:
    """Yield (where, text) for every piece of prose in the pack."""
    for preset in pack.presets:
        yield (
            f"preset '{preset.ref}'",
            " ".join(_strings([preset.label, preset.description, preset.definition])),
        )
    for rel in pack.relationship_types:
        yield (
            f"relationship type '{rel.ref}'",
            " ".join(_strings([rel.label, rel.reverse_label, rel.description])),
        )
    for kind in pack.item_types:
        yield (
            f"item type '{kind.ref}'",
            " ".join(_strings([kind.label, kind.description])),
        )
    for item in pack.items:
        yield (
            f"item '{item.ref}'",
            " ".join(
                _strings([item.name, item.description, item.tags, item.attributes])
            ),
        )
    for c in pack.connections:
        yield (
            f"connection '{c.source_ref}' -> '{c.target_ref}'",
            " ".join(_strings(c.attributes)),
        )


@pytest.mark.parametrize("pack_id", _PACK_IDS)
async def test_pack_installs_and_removes_cleanly(
    pack_id: str, make_world: MakeWorld
) -> None:
    """A pack installs, uninstalls to nothing, and installs again."""
    pack = await _load(pack_id)
    world = make_world(pack)

    installed = await _install(world, pack_id)

    assert asdict(installed.created) == asdict(pack.counts), (
        f"{pack_id}: counts differ after install"
    )
    removed = await _uninstall(world, pack_id)
    assert removed.kept == (), f"{pack_id}: an untouched install kept {removed.kept}"
    assert await _live_counts(world) == [0] * 5, f"{pack_id}: entities remain"
    reinstalled = await _install(world, pack_id)
    assert asdict(reinstalled.created) == asdict(pack.counts), (
        f"{pack_id}: reinstall differs"
    )


@pytest.mark.parametrize("pack_id", _PACK_IDS)
async def test_pack_has_connections_and_items_for_every_type(pack_id: str) -> None:
    """Every item type is used and the pack shows at least one connection."""
    pack = await _load(pack_id)

    assert pack.connections, f"{pack_id}: has no connections"
    used = {item.type_ref for item in pack.items}
    for kind in pack.item_types:
        assert kind.ref in used, f"{pack_id}: item type '{kind.ref}' has no items"


@pytest.mark.parametrize("pack_id", _PACK_IDS)
async def test_pack_descriptions_are_filled_in(pack_id: str) -> None:
    """The index entry, item types and relationship types all have descriptions."""
    summaries = {s.id: s for s in await FilePackCatalogue().list_packs()}
    pack = await _load(pack_id)

    assert summaries[pack_id].description.strip(), f"{pack_id}: index description"
    for kind in pack.item_types:
        assert (kind.description or "").strip(), f"{pack_id}: item type '{kind.ref}'"
    for rel in pack.relationship_types:
        assert (rel.description or "").strip(), (
            f"{pack_id}: relationship type '{rel.ref}'"
        )


@pytest.mark.parametrize("pack_id", _PACK_IDS)
async def test_pack_presets_are_used_and_names_are_unique(pack_id: str) -> None:
    """Every preset is referenced by a schema; names are unique within a type."""
    pack = await _load(pack_id)

    used: set[str] = set()
    for schema in (
        *(t.attributes_schema for t in pack.item_types),
        *(t.attributes_schema for t in pack.relationship_types),
    ):
        used |= preset_refs(schema)
    for preset in pack.presets:
        assert preset.ref in used, f"{pack_id}: preset '{preset.ref}' is unused"
    seen: set[tuple[str, str]] = set()
    for item in pack.items:
        key = (item.type_ref, item.name)
        assert key not in seen, f"{pack_id}: duplicate name '{item.name}'"
        seen.add(key)


@pytest.mark.parametrize("pack_id", _PACK_IDS)
async def test_pack_slugs_are_prefixed_with_the_pack_id(pack_id: str) -> None:
    """Type slugs start with the pack id, so packs never clash with user types."""
    pack = await _load(pack_id)

    slugs = [t.slug for t in pack.item_types]
    slugs += [t.slug for t in pack.relationship_types]
    for slug in slugs:
        assert slug.startswith(f"{pack_id}-"), f"{pack_id}: slug '{slug}'"


@pytest.mark.parametrize("pack_id", _PACK_IDS)
async def test_pack_text_uses_british_spelling(pack_id: str) -> None:
    """No obviously American spellings in any text."""
    pack = await _load(pack_id)

    for where, text in _texts(pack):
        match = _AMERICAN.search(text)
        assert match is None, f"{pack_id}: {where} uses '{match and match.group()}'"
