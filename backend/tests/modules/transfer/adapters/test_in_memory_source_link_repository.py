"""Tests for the in-memory SourceLinkRepository."""

import uuid

from app.modules.transfer.adapters.persistence.in_memory_source_link_repository import (
    InMemorySourceLinkRepository,
)
from app.modules.transfer.domain.entity_kind import EntityKind
from app.modules.transfer.domain.source_link import SourceLink
from app.shared_kernel.content_filter import ContentFilter

OWNER = uuid.UUID(int=0xA1)
OTHER = uuid.UUID(int=0xB2)


def _link(
    key: str = "k1",
    *,
    source: str = "lddb",
    kind: EntityKind = EntityKind.ITEM,
    owner: uuid.UUID = OWNER,
) -> SourceLink:
    return SourceLink.create(
        owner_id=owner,
        source=source,
        kind=kind,
        key=key,
        entity_id=uuid.uuid7(),
        fields={"name": "h"},
    )


async def test_add_then_get_by_key() -> None:
    """Add then get by key."""
    repo = InMemorySourceLinkRepository()
    link = _link()
    await repo.add(link)
    found = await repo.get_by_key(
        "lddb", EntityKind.ITEM, "k1", scope=ContentFilter.of(OWNER)
    )
    assert found is link


async def test_get_by_key_misses_other_source_kind_and_key() -> None:
    """Get by key misses other source kind and key."""
    repo = InMemorySourceLinkRepository()
    await repo.add(_link())
    scope = ContentFilter.of(OWNER)
    assert await repo.get_by_key("x", EntityKind.ITEM, "k1", scope=scope) is None
    assert (
        await repo.get_by_key("lddb", EntityKind.COLLECTION, "k1", scope=scope) is None
    )
    assert await repo.get_by_key("lddb", EntityKind.ITEM, "k2", scope=scope) is None


async def test_another_owners_link_is_not_visible() -> None:
    """Another owners link is not visible."""
    repo = InMemorySourceLinkRepository()
    await repo.add(_link(owner=OTHER))
    found = await repo.get_by_key(
        "lddb", EntityKind.ITEM, "k1", scope=ContentFilter.of(OWNER)
    )
    assert found is None


async def test_save_replaces_the_stored_link() -> None:
    """Save replaces the stored link."""
    repo = InMemorySourceLinkRepository()
    link = _link()
    await repo.add(link)
    new_id = uuid.uuid7()
    link.record_import(new_id, {"name": "h2"})
    await repo.save(link)
    found = await repo.get_by_key(
        "lddb", EntityKind.ITEM, "k1", scope=ContentFilter.of(OWNER)
    )
    assert found is not None
    assert found.entity_id == new_id


async def test_list_by_keys_returns_only_the_asked_keys() -> None:
    """List by keys returns only the asked keys."""
    repo = InMemorySourceLinkRepository()
    for key in ("a", "b", "c"):
        await repo.add(_link(key))
    await repo.add(_link("a", source="other"))
    found = await repo.list_by_keys(
        "lddb", EntityKind.ITEM, ["a", "c", "z"], scope=ContentFilter.of(OWNER)
    )
    assert sorted(link.key for link in found) == ["a", "c"]


async def test_list_for_source_returns_every_kind_of_that_source() -> None:
    """List for source returns every kind of that source."""
    repo = InMemorySourceLinkRepository()
    await repo.add(_link("a"))
    await repo.add(_link("b", kind=EntityKind.COLLECTION))
    await repo.add(_link("c", source="other"))
    found = await repo.list_for_source("lddb", scope=ContentFilter.of(OWNER))
    assert sorted(link.key for link in found) == ["a", "b"]
