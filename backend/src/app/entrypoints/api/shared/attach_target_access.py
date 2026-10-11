"""The media module's view of the graph: which items and connections a person sees."""

from typing import TYPE_CHECKING, Annotated

from fastapi import Depends

from app.modules.graph.adapters.persistence.unit_of_work import build_graph_repos
from app.modules.media.domain.media_attachment import AttachmentTarget
from app.platform.database import get_session_factory

if TYPE_CHECKING:
    import uuid
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.modules.graph.ports.unit_of_work import GraphRepos
    from app.shared_kernel.access_scope import AccessScope


class GraphAttachTargetAccess:
    """Reports whether an item or connection is live and inside a scope."""

    def __init__(self, repos: GraphRepos) -> None:
        self._repos = repos

    async def can_attach(
        self, target_type: AttachmentTarget, target_id: uuid.UUID, scope: AccessScope
    ) -> bool:
        """Whether the target exists, is not deleted and is inside `scope`."""
        if target_type is AttachmentTarget.NODE:
            return await self._repos.nodes.get(target_id, scope=scope) is not None
        return await self._repos.edges.get(target_id, scope=scope) is not None


async def get_attach_target_access(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
) -> AsyncIterator[GraphAttachTargetAccess]:
    """Yield the target check, backed by a read session on the graph tables."""
    async with session_factory() as session:
        yield GraphAttachTargetAccess(build_graph_repos(session))
