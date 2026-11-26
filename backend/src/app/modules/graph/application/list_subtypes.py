import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.graph.application.list_node_types import NodeTypeSort
from app.modules.graph.application.parent_type import type_view
from app.modules.graph.application.permissions import GraphPermission
from app.modules.graph.domain.errors import NodeTypeNotFoundError
from app.modules.graph.domain.node_type import NodeType

# Needed at runtime: the CQRS signature test evaluates __init__ annotations.
from app.modules.graph.ports.choice_list_source import ChoiceListSource  # noqa: TC001
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.access import Access, Content
from app.shared_kernel.cqrs import QueryHandler
from app.shared_kernel.paging import Page, PagedQuery

if TYPE_CHECKING:
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class ListSubtypesQuery(PagedQuery[NodeTypeSort]):
    """Request for a page of a parent type's subtypes, by id unless `sort` says."""

    node_type_id: uuid.UUID


class ListSubtypes(QueryHandler[GraphRepos, ListSubtypesQuery, Page[NodeType]]):
    """List the subtypes of one item type with keyset pagination."""

    access: ClassVar[Access] = Content(GraphPermission.TYPE_READ)

    def __init__(
        self,
        repos: GraphRepos,
        guard: AccessGuard,
        choice_lists: ChoiceListSource | None = None,
    ) -> None:
        super().__init__(repos, guard)
        self._choice_lists = choice_lists

    async def _handle(self, query: ListSubtypesQuery, actor: Actor) -> Page[NodeType]:
        """Return a page of the parent's subtypes after `query.after`."""
        scope = self.scope(actor)
        parent = await self._repos.node_types.get(query.node_type_id, scope=scope)
        if parent is None:
            raise NodeTypeNotFoundError(f"NodeType {query.node_type_id} not found")
        page = await self._repos.node_types.page_subtypes(
            str(parent.slug),
            scope=scope,
            page=query.page_request(),
        )
        logger.debug("subtypes listed", parent=str(parent.slug), count=len(page.items))
        return Page(
            items=[
                await type_view(
                    self._repos, subtype, scope=scope, choice_lists=self._choice_lists
                )
                for subtype in page.items
            ],
            next=page.next,
        )
