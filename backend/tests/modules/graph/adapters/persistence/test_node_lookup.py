"""Tests for finding nodes by name or attribute value (Postgres)."""

import uuid
from typing import TYPE_CHECKING

import pytest

from app.modules.graph.adapters.persistence.node_repository import (
    SqlAlchemyNodeRepository,
)
from app.modules.graph.domain.node import Node
from app.shared_kernel.content_filter import ContentFilter

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

OWNER = uuid.UUID(int=1)
OTHER = uuid.UUID(int=2)


def _node(
    name: str = "n",
    *,
    type_: str | None = "film",
    attributes: dict[str, object] | None = None,
    owner: uuid.UUID = OWNER,
) -> Node:
    return Node.create(
        owner_id=owner, name=name, type=type_, attributes=attributes or {}
    )


async def test_ids_with_attribute_value_matches_strings_only(
    db_session: AsyncSession,
) -> None:
    """Ids with attribute value matches strings only."""
    repo = SqlAlchemyNodeRepository(db_session)
    hit = _node(attributes={"upc": "0123"})
    for node in (
        hit,
        _node(attributes={"upc": "9999"}),
        _node(attributes={"upc": ["0123"]}),
        _node(type_="book", attributes={"upc": "0123"}),
        _node(attributes={"upc": "0123"}, owner=OTHER),
    ):
        await repo.add(node)

    found = await repo.ids_with_attribute_value(
        "film", "upc", "0123", scope=ContentFilter.of(OWNER), limit=5
    )

    assert found == [hit.id]


async def test_ids_with_attribute_value_skips_deleted_and_limits(
    db_session: AsyncSession,
) -> None:
    """Ids with attribute value skips deleted and limits."""
    repo = SqlAlchemyNodeRepository(db_session)
    live = [_node(attributes={"upc": "1"}) for _ in range(3)]
    gone = _node(attributes={"upc": "1"})
    gone.soft_delete()
    for node in (*live, gone):
        await repo.add(node)

    found = await repo.ids_with_attribute_value(
        "film", "upc", "1", scope=ContentFilter.of(OWNER), limit=2
    )

    assert found == sorted(n.id for n in live)[:2]


async def test_ids_with_name_is_exact_and_scoped(db_session: AsyncSession) -> None:
    """Ids with name is exact and scoped."""
    repo = SqlAlchemyNodeRepository(db_session)
    alien = _node("Alien")
    for node in (
        alien,
        _node("alien"),
        _node("Aliens"),
        _node("Alien", type_="book"),
        _node("Alien", owner=OTHER),
    ):
        await repo.add(node)

    found = await repo.ids_with_name(
        "film", "Alien", scope=ContentFilter.of(OWNER), limit=5
    )

    assert found == [alien.id]
