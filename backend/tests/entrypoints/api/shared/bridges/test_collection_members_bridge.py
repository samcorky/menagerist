"""Integration tests for the graph-to-collections membership bridge."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from app.entrypoints.api.shared.bridges.collection_members import CollectionsMembers
from app.modules.collections.adapters.persistence.unit_of_work import (
    build_collections_repos,
)
from app.modules.collections.domain.collection import Collection, Membership
from app.modules.graph.ports.collection_members import ManualSource, SmartSource
from app.shared_kernel.slug import Slug

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from app.shared_kernel.content_filter import ContentFilter

ALL = ContentFilter.everyone()
pytestmark = pytest.mark.integration


async def _shelf(session: AsyncSession) -> tuple[CollectionsMembers, Collection]:
    """Store a collection and return the bridge over the same session."""
    repos = build_collections_repos(session)
    collection = Collection.create(
        name="Shelf", slug=Slug("shelf"), owner_id=uuid.uuid7()
    )
    await repos.collections.add(collection)
    return CollectionsMembers(repos), collection


async def test_unknown_collection_is_none(db_session: AsyncSession) -> None:
    """A collection that does not exist yields None."""
    members, _ = await _shelf(db_session)

    assert await members.resolve(uuid.uuid7(), ALL) is None


async def test_empty_collection_is_an_empty_set(db_session: AsyncSession) -> None:
    """A live collection with no items yields no ids, not None."""
    members, shelf = await _shelf(db_session)

    assert await members.resolve(shelf.id, ALL) == ManualSource(ids=frozenset())


async def test_returns_the_item_ids_on_the_collection(
    db_session: AsyncSession,
) -> None:
    """The ids are exactly the memberships, whether or not the items still exist."""
    members, shelf = await _shelf(db_session)
    repos = build_collections_repos(db_session)
    item_ids = {uuid.uuid7(), uuid.uuid7()}
    for item_id in item_ids:
        await repos.memberships.add(
            Membership(
                collection_id=shelf.id, item_id=item_id, added_at=datetime.now(UTC)
            )
        )

    assert await members.resolve(shelf.id, ALL) == ManualSource(ids=frozenset(item_ids))


async def test_soft_deleted_collection_is_none(db_session: AsyncSession) -> None:
    """A soft-deleted collection yields None even though its rows remain."""
    members, shelf = await _shelf(db_session)
    repos = build_collections_repos(db_session)
    await repos.memberships.add(
        Membership(
            collection_id=shelf.id, item_id=uuid.uuid7(), added_at=datetime.now(UTC)
        )
    )
    shelf.soft_delete()
    await repos.collections.save(shelf)

    assert await members.resolve(shelf.id, ALL) is None


async def test_collection_of_another_owner_is_none(db_session: AsyncSession) -> None:
    """A collection outside the scope reads as missing, memberships and all."""
    members, shelf = await _shelf(db_session)
    repos = build_collections_repos(db_session)
    await repos.memberships.add(
        Membership(
            collection_id=shelf.id, item_id=uuid.uuid7(), added_at=datetime.now(UTC)
        )
    )

    assert await members.resolve(shelf.id, ContentFilter.of(shelf.owner_id)) is not None
    assert await members.resolve(shelf.id, ContentFilter.of(uuid.uuid7())) is None


_DEFINITION = {
    "v": 1,
    "where": {"op": "and", "children": [{"kind": "text", "q": "alien"}]},
    "sort": [{"by": "name"}],
}


async def _smart(session: AsyncSession) -> tuple[CollectionsMembers, Collection]:
    """Store a smart collection and return the bridge over the same session."""
    repos = build_collections_repos(session)
    collection = Collection.create(
        name="Aliens",
        slug=Slug("aliens"),
        owner_id=uuid.uuid7(),
        definition=_DEFINITION,
    )
    await repos.collections.add(collection)
    return CollectionsMembers(repos), collection


async def test_smart_collection_resolves_to_its_definition(
    db_session: AsyncSession,
) -> None:
    """A smart collection yields its stored definition, never a list of ids."""
    members, smart = await _smart(db_session)

    assert await members.resolve(smart.id, ContentFilter.of(smart.owner_id)) == (
        SmartSource(definition=_DEFINITION)
    )


async def test_smart_collection_of_another_owner_is_none(
    db_session: AsyncSession,
) -> None:
    """Another person's smart collection reads as missing."""
    members, smart = await _smart(db_session)

    assert await members.resolve(smart.id, ContentFilter.of(uuid.uuid7())) is None


async def test_soft_deleted_smart_collection_is_none(db_session: AsyncSession) -> None:
    """A soft-deleted smart collection yields None."""
    members, smart = await _smart(db_session)
    smart.soft_delete()
    await build_collections_repos(db_session).collections.save(smart)

    assert await members.resolve(smart.id, ALL) is None
