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
    """Summaries follow insertion order and carry the pack's counts."""
    catalogue = InMemoryPackCatalogue()
    catalogue.add(_pack("one"), name="One", description="First")
    catalogue.add(_pack("two"), name="Two", description="Second")

    summaries = await catalogue.list_packs()

    assert [s.id for s in summaries] == ["one", "two"]
    assert summaries[0].name == "One"
    assert summaries[0].counts.items == 1


async def test_get_returns_the_pack_or_none() -> None:
    """`get` returns the stored pack, or `None` when absent."""
    catalogue = InMemoryPackCatalogue()
    pack = _pack("one")
    catalogue.add(pack, name="One", description="First")

    assert await catalogue.get("one") is pack
    assert await catalogue.get("missing") is None
