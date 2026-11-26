"""The packs that show parent types (#772): their shape, installed and removed."""

from typing import TYPE_CHECKING

import pytest

from app.modules.examples.adapters.platform.file_pack_catalogue import FilePackCatalogue
from app.modules.examples.application.install_example_pack import (
    InstallExamplePack,
    InstallExamplePackCommand,
)
from app.modules.examples.application.uninstall_example_pack import (
    UninstallExamplePack,
    UninstallExamplePackCommand,
)
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.content_filter import ContentFilter

if TYPE_CHECKING:
    from tests.modules.examples.conftest import MakeWorld, World

# pack id -> (parent slug, subtype slugs)
_PACKS = {
    "music-formats": (
        "music-formats-media",
        {
            "music-formats-vinyl",
            "music-formats-cd",
            "music-formats-cassette",
            "music-formats-minidisc",
        },
    ),
    "film-formats": (
        "film-formats-media",
        {
            "film-formats-laserdisc",
            "film-formats-dvd",
            "film-formats-bluray",
            "film-formats-vhs",
        },
    ),
    "currency": (
        "currency-money",
        {"currency-coin", "currency-banknote", "currency-token"},
    ),
}


# Packs that gained a parent type later (#788): pack id -> parent ref -> subtype refs.
_REWORKED = {
    "parts": {"part": {"resistor", "capacitor", "semiconductor"}},
    "conventions": {"collectable": {"poster", "photo-print", "programme"}},
    "movies": {"memorabilia": {"poster", "ticket-stub", "programme"}},
}


@pytest.mark.parametrize("pack_id", list(_REWORKED))
async def test_a_reworked_pack_splits_its_type_into_subtypes(pack_id: str) -> None:
    """The parent gains its subtypes, and every item of its family is a subtype's."""
    pack = await FilePackCatalogue().get(pack_id)

    assert pack is not None
    for parent_ref, subtype_refs in _REWORKED[pack_id].items():
        parent = next(t for t in pack.item_types if t.ref == parent_ref)
        assert parent.parent is None
        assert {t.ref for t in pack.item_types if t.parent == parent_ref} == (
            subtype_refs
        )
        # Every subtype has an item; the parent may keep some that fit no subtype.
        assert {i.type_ref for i in pack.items if i.type_ref in subtype_refs} == (
            subtype_refs
        )


@pytest.mark.parametrize("pack_id", list(_REWORKED))
async def test_a_reworked_pack_keeps_no_field_on_both_a_parent_and_a_subtype(
    pack_id: str,
) -> None:
    """A subtype's own fields never repeat the parent's, so nothing is defined twice."""
    pack = await FilePackCatalogue().get(pack_id)

    assert pack is not None
    by_ref = {t.ref: t for t in pack.item_types}
    for subtype in pack.item_types:
        if subtype.parent is None:
            continue
        own = set((subtype.attributes_schema or {}).get("properties", {}))
        parent = by_ref[subtype.parent]
        inherited = set((parent.attributes_schema or {}).get("properties", {}))
        repeated = own & inherited
        assert own
        assert not repeated, f"{pack_id}: {subtype.ref} repeats {repeated}"


def _install(world: World, pack_id: str) -> InstallExamplePack:
    return InstallExamplePack(
        world.uow,
        InMemoryAccessGuard(),
        world.catalogue,
        world.presets,
        world.graph,
        world.collections,
        world.covers,
    )


async def _node_types(world: World) -> dict[str, str | None]:
    """Parent slug by type slug, for every live item type."""
    types = await world.graph_repos.node_types.list(
        after=None, limit=1000, scope=ContentFilter.everyone()
    )
    return {t.slug.value: t.parent for t in types}


@pytest.mark.parametrize("pack_id", list(_PACKS))
async def test_the_pack_has_one_parent_with_its_subtypes(pack_id: str) -> None:
    """The parent has no parent; each subtype names it; nothing else does."""
    parent_slug, subtype_slugs = _PACKS[pack_id]
    pack = await FilePackCatalogue().get(pack_id)

    assert pack is not None
    parent_ref = next(t.ref for t in pack.item_types if t.slug == parent_slug)
    by_slug = {t.slug: t for t in pack.item_types}
    assert by_slug[parent_slug].parent is None
    assert {t.slug for t in pack.item_types if t.parent == parent_ref} == subtype_slugs
    assert set(by_slug) == {parent_slug, *subtype_slugs}


@pytest.mark.parametrize("pack_id", list(_PACKS))
async def test_the_connection_type_is_limited_to_the_parent(pack_id: str) -> None:
    """Its ends name the parent, so every subtype is allowed at them."""
    parent_slug, _ = _PACKS[pack_id]
    pack = await FilePackCatalogue().get(pack_id)

    assert pack is not None
    assert len(pack.relationship_types) == 1
    relationship = pack.relationship_types[0]
    assert relationship.source_types == (parent_slug,)
    assert relationship.target_types == (parent_slug,)


@pytest.mark.parametrize("pack_id", list(_PACKS))
async def test_the_smart_collection_finds_the_parents_family(pack_id: str) -> None:
    """Filtering by the parent type is what the pack's collection does."""
    parent_slug, _ = _PACKS[pack_id]
    pack = await FilePackCatalogue().get(pack_id)

    assert pack is not None
    assert len(pack.collections) == 1
    definition = pack.collections[0].definition
    assert definition is not None
    where = definition["where"]
    assert where["children"] == [{"kind": "type", "in": [parent_slug]}]


@pytest.mark.parametrize("pack_id", list(_PACKS))
async def test_installing_makes_the_subtypes_and_removing_takes_them_all(
    pack_id: str, make_world: MakeWorld
) -> None:
    """The installed subtypes name the parent, and removal leaves no type behind."""
    parent_slug, subtype_slugs = _PACKS[pack_id]
    catalogue = FilePackCatalogue()
    pack = await catalogue.get(pack_id)
    assert pack is not None
    world = make_world(pack)

    await _install(world, pack_id).handle(
        InstallExamplePackCommand(pack_id=pack_id), world.actor
    )

    types = await _node_types(world)
    assert types[parent_slug] is None
    assert {slug for slug, parent in types.items() if parent == parent_slug} == (
        subtype_slugs
    )

    await UninstallExamplePack(
        world.uow,
        InMemoryAccessGuard(),
        world.catalogue,
        world.presets,
        world.graph,
        world.collections,
        world.covers,
    ).handle(UninstallExamplePackCommand(pack_id=pack_id), world.actor)

    assert await _node_types(world) == {}
