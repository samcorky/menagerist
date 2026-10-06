from typing import TYPE_CHECKING

import pytest

from app.modules.graph.adapters.persistence.unit_of_work import (
    build_graph_repos,
    create_in_memory_graph_uow,
)
from app.modules.graph.application.create_edge_type import (
    CreateEdgeType,
    CreateEdgeTypeCommand,
)
from app.modules.graph.application.create_node_type import (
    CreateNodeType,
    CreateNodeTypeCommand,
)
from app.modules.graph.application.delete_edge_type import (
    DeleteEdgeType,
    DeleteEdgeTypeCommand,
)
from app.modules.graph.application.delete_node_type import (
    DeleteNodeType,
    DeleteNodeTypeCommand,
)
from app.modules.graph.domain.errors import (
    EdgeTypeSlugConflictError,
    NodeTypeSlugConflictError,
)
from app.shared_kernel.actor import SYSTEM_ACTOR

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


async def test_node_type_slug_is_reusable_after_delete_on_postgres(
    db_session: AsyncSession,
) -> None:
    """Delete frees a slug and a live type holds it, in the use cases and the index."""
    uow = create_in_memory_graph_uow(build_graph_repos(db_session))
    first = await CreateNodeType(uow).handle(
        CreateNodeTypeCommand(slug="record", label="Record"), SYSTEM_ACTOR
    )
    await DeleteNodeType(uow).handle(
        DeleteNodeTypeCommand(node_type_id=first.id), SYSTEM_ACTOR
    )

    second = await CreateNodeType(uow).handle(
        CreateNodeTypeCommand(slug="record", label="Record again"), SYSTEM_ACTOR
    )

    assert second.id != first.id
    with pytest.raises(NodeTypeSlugConflictError):
        await CreateNodeType(uow).handle(
            CreateNodeTypeCommand(slug="record", label="Third"), SYSTEM_ACTOR
        )


async def test_edge_type_slug_is_reusable_after_delete_on_postgres(
    db_session: AsyncSession,
) -> None:
    """Delete frees a slug and a live type holds it, in the use cases and the index."""
    uow = create_in_memory_graph_uow(build_graph_repos(db_session))
    first = await CreateEdgeType(uow).handle(
        CreateEdgeTypeCommand(slug="signed-by", label="Signed by"), SYSTEM_ACTOR
    )
    await DeleteEdgeType(uow).handle(
        DeleteEdgeTypeCommand(edge_type_id=first.id), SYSTEM_ACTOR
    )

    second = await CreateEdgeType(uow).handle(
        CreateEdgeTypeCommand(slug="signed-by", label="Signed by again"), SYSTEM_ACTOR
    )

    assert second.id != first.id
    with pytest.raises(EdgeTypeSlugConflictError):
        await CreateEdgeType(uow).handle(
            CreateEdgeTypeCommand(slug="signed-by", label="Third"), SYSTEM_ACTOR
        )
