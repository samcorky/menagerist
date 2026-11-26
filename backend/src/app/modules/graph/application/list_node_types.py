from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.graph.application.parent_type import type_view
from app.modules.graph.application.permissions import GraphPermission
from app.modules.graph.domain.node_type import NodeType

# Needed at runtime: the CQRS signature test evaluates __init__ annotations.
from app.modules.graph.ports.choice_list_source import ChoiceListSource  # noqa: TC001
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.access import Access, Content
from app.shared_kernel.cqrs import QueryHandler
from app.shared_kernel.paging import Cursor, Page, PageRequest, SortOrder

if TYPE_CHECKING:
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


class NodeTypeSort(StrEnum):
    """What a list of item types can be sorted by: fields of the response."""

    SLUG = "slug"
    LABEL = "label"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"


@dataclass(kw_only=True)
class ListNodeTypesQuery:
    """Request for a page of node types, by id unless `sort` says otherwise."""

    after: Cursor | None = None
    limit: int = 50
    sort: NodeTypeSort | None = None
    order: SortOrder = SortOrder.ASC


class ListNodeTypes(QueryHandler[GraphRepos, ListNodeTypesQuery, Page[NodeType]]):
    """List node types with keyset pagination."""

    access: ClassVar[Access] = Content(GraphPermission.TYPE_READ)

    def __init__(
        self,
        repos: GraphRepos,
        guard: AccessGuard,
        choice_lists: ChoiceListSource | None = None,
    ) -> None:
        super().__init__(repos, guard)
        self._choice_lists = choice_lists

    async def _handle(self, query: ListNodeTypesQuery, actor: Actor) -> Page[NodeType]:
        """Return a page of node types after `query.after`, up to `query.limit`."""
        scope = self.scope(actor)
        page = await self._repos.node_types.list(
            scope=scope,
            page=PageRequest(
                after=query.after,
                limit=query.limit,
                sort=None if query.sort is None else query.sort.value,
                order=query.order,
            ),
        )
        logger.debug("node types listed", count=len(page.items))
        return Page(
            items=[
                await type_view(
                    self._repos, node_type, scope=scope, choice_lists=self._choice_lists
                )
                for node_type in page.items
            ],
            next=page.next,
        )
