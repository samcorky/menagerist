"""Integration tests for the graph-to-collections membership bridge."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from app.entrypoints.api.shared.collection_members import CollectionsMembers
from app.modules.collections.adapters.persistence.unit_of_work import (
    build_collections_repos,
)
from app.modules.collections.domain.collection import Collection, Membership
from app.shared_kernel.slug import Slug

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

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

    assert await members.item_ids(uuid.uuid7()) is None


async def test_empty_collection_is_an_empty_set(db_session: AsyncSession) -> None:
    """A live collection with no items yields an empty set, not None."""
    members, shelf = await _shelf(db_session)

    assert await members.item_ids(shelf.id) == set()


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

    assert await members.item_ids(shelf.id) == item_ids


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

    assert await members.item_ids(shelf.id) is None
