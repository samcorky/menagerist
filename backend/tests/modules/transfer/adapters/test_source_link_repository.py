import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.exc import IntegrityError

from app.modules.transfer.adapters.persistence.source_link_repository import (
    SqlAlchemySourceLinkRepository,
)
from app.modules.transfer.domain.entity_kind import EntityKind
from app.modules.transfer.domain.source_link import SourceLink
from app.shared_kernel.content_filter import ContentFilter

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

OWNER = uuid.UUID(int=0xA1)
OTHER = uuid.UUID(int=0xB2)

pytestmark = pytest.mark.integration


def _link(
    key: str = "k1", *, source: str = "lddb", owner: uuid.UUID = OWNER
) -> SourceLink:
    return SourceLink.create(
        owner_id=owner,
        source=source,
        kind=EntityKind.ITEM,
        key=key,
        entity_id=uuid.uuid7(),
        fields={"name": "h1", "attributes.year": "h2"},
    )


async def test_round_trips_fields_through_jsonb(db_session: AsyncSession) -> None:
    """Round trips fields through jsonb."""
    repo = SqlAlchemySourceLinkRepository(db_session)
    link = _link()
    await repo.add(link)
    db_session.expire_all()

    stored = await repo.get_by_key(
        "lddb", EntityKind.ITEM, "k1", scope=ContentFilter.everyone()
    )

    assert stored is not None
    assert stored.entity_id == link.entity_id
    assert stored.fields == {"name": "h1", "attributes.year": "h2"}
    assert stored.kind is EntityKind.ITEM


async def test_save_updates_the_link(db_session: AsyncSession) -> None:
    """Save updates the link."""
    repo = SqlAlchemySourceLinkRepository(db_session)
    link = _link()
    await repo.add(link)
    new_id = uuid.uuid7()
    link.record_import(new_id, {"name": "h9"})
    await repo.save(link)
    db_session.expire_all()

    stored = await repo.get_by_key(
        "lddb", EntityKind.ITEM, "k1", scope=ContentFilter.everyone()
    )

    assert stored is not None
    assert (stored.entity_id, stored.fields) == (new_id, {"name": "h9"})


async def test_duplicate_key_is_refused(db_session: AsyncSession) -> None:
    """Duplicate key is refused."""
    repo = SqlAlchemySourceLinkRepository(db_session)
    await repo.add(_link())
    with pytest.raises(IntegrityError):
        await repo.add(_link())


async def test_two_owners_may_share_a_key(db_session: AsyncSession) -> None:
    """Two owners may share a key."""
    repo = SqlAlchemySourceLinkRepository(db_session)
    await repo.add(_link())
    await repo.add(_link(owner=OTHER))

    mine = await repo.get_by_key(
        "lddb", EntityKind.ITEM, "k1", scope=ContentFilter.of(OWNER)
    )
    theirs = await repo.get_by_key(
        "lddb", EntityKind.ITEM, "k1", scope=ContentFilter.of(OTHER)
    )

    assert mine is not None
    assert theirs is not None
    assert mine.id != theirs.id


async def test_list_by_keys_and_list_for_source(db_session: AsyncSession) -> None:
    """List by keys and list for source."""
    repo = SqlAlchemySourceLinkRepository(db_session)
    for key in ("a", "b", "c"):
        await repo.add(_link(key))
    await repo.add(_link("a", source="other"))
    scope = ContentFilter.of(OWNER)

    some = await repo.list_by_keys(
        "lddb", EntityKind.ITEM, ["a", "c", "z"], scope=scope
    )
    every = await repo.list_for_source("lddb", scope=scope)

    assert sorted(link.key for link in some) == ["a", "c"]
    assert sorted(link.key for link in every) == ["a", "b", "c"]
