"""Removing an unused item type is serialised with concurrent item writes."""

import asyncio
import uuid
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.entrypoints.api.shared.authorization import RoleAuthorizationAdapter
from app.modules.graph.adapters.persistence.models import NodeModel, NodeTypeModel
from app.modules.graph.adapters.persistence.node_repository import (
    SqlAlchemyNodeRepository,
)
from app.modules.graph.adapters.persistence.node_type_repository import (
    SqlAlchemyNodeTypeRepository,
)
from app.modules.graph.adapters.persistence.unit_of_work import create_graph_uow
from app.modules.graph.application.delete_unused_node_type import (
    DeleteUnusedNodeType,
    DeleteUnusedNodeTypeCommand,
)
from app.modules.graph.domain.errors import NodeTypeInUseError
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.node_type import NodeType
from app.shared_kernel.access_scope import AccessScope
from app.shared_kernel.actor import SYSTEM_ACTOR

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

OWNER = uuid.UUID(int=1)


@pytest_asyncio.fixture
async def factory(
    postgres_url: str,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Committing sessions over real connections; removes what the tests add."""
    engine = create_async_engine(postgres_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield sessions
    finally:
        async with sessions.begin() as session:
            await session.execute(delete(NodeModel))
            await session.execute(delete(NodeTypeModel))
        await engine.dispose()


async def _add_type(factory: async_sessionmaker[AsyncSession], slug: str) -> NodeType:
    node_type = NodeType.create(slug=slug, label=slug)
    async with factory.begin() as session:
        await SqlAlchemyNodeTypeRepository(session).add(node_type)
    return node_type


def _remove(
    factory: async_sessionmaker[AsyncSession], node_type: NodeType
) -> asyncio.Task[None]:
    use_case = DeleteUnusedNodeType(
        create_graph_uow(factory), RoleAuthorizationAdapter()
    )
    return asyncio.create_task(
        use_case.handle(
            DeleteUnusedNodeTypeCommand(node_type_id=node_type.id), SYSTEM_ACTOR
        )
    )


async def test_an_unused_type_is_removed(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """With no items the type is soft-deleted."""
    node_type = await _add_type(factory, "unused")

    await _remove(factory, node_type)

    async with factory() as session:
        assert await SqlAlchemyNodeTypeRepository(session).get(node_type.id) is None


async def test_an_item_being_added_keeps_the_type(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """The removal waits for the writer, then sees its item and refuses."""
    node_type = await _add_type(factory, "film")
    async with factory() as writer:
        types = SqlAlchemyNodeTypeRepository(writer)
        assert await types.get_by_slug("film", guard_item_write=True) is not None
        await SqlAlchemyNodeRepository(writer).add(
            Node.create(owner_id=OWNER, name="Heat", type="film")
        )
        await writer.flush()

        removal = _remove(factory, node_type)
        await asyncio.sleep(0.5)
        assert not removal.done()
        await writer.commit()

    with pytest.raises(NodeTypeInUseError):
        await removal
    async with factory() as session:
        assert await SqlAlchemyNodeTypeRepository(session).get(node_type.id)
        items = await SqlAlchemyNodeRepository(session).list(
            scope=AccessScope.everyone(), after=None, limit=10, type="film"
        )
        assert [item.type for item in items] == ["film"]


async def test_a_writer_waits_for_a_removal_in_progress(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """An item write started during the removal waits, then finds the type gone."""
    node_type = await _add_type(factory, "game")
    async with factory() as remover:
        types = SqlAlchemyNodeTypeRepository(remover)
        locked = await types.get_for_removal(node_type.id)
        assert locked is not None

        async def write() -> NodeType | None:
            async with factory() as writer:
                return await SqlAlchemyNodeTypeRepository(writer).get_by_slug(
                    "game", guard_item_write=True
                )

        writing = asyncio.create_task(write())
        await asyncio.sleep(0.5)
        assert not writing.done()

        locked.soft_delete()
        await types.save(locked)
        await remover.commit()

    assert await writing is None
