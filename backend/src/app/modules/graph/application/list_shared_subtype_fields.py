import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from app.modules.graph.application.permissions import GraphPermission
from app.modules.graph.application.subtype_fields import SharedField, shared_fields
from app.modules.graph.domain.errors import NodeTypeNotFoundError
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.access import Access, Content
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class ListSharedSubtypeFieldsQuery:
    """Ask which fields several subtypes of an item type each define for themselves."""

    node_type_id: uuid.UUID


class ListSharedSubtypeFields(
    QueryHandler[GraphRepos, ListSharedSubtypeFieldsQuery, list[SharedField]]
):
    """List the fields two or more subtypes of an item type define the same way.

    These are the fields that could move up to the parent. An item type with no
    subtypes, or a subtype, has none.
    """

    access: ClassVar[Access] = Content(GraphPermission.TYPE_READ)

    async def _handle(
        self, query: ListSharedSubtypeFieldsQuery, actor: Actor
    ) -> list[SharedField]:
        """Read the type's subtypes and group what they define."""
        scope = self.scope(actor)
        node_type = await self._repos.node_types.get(query.node_type_id, scope=scope)
        if node_type is None:
            raise NodeTypeNotFoundError(f"NodeType {query.node_type_id} not found")
        subtypes = await self._repos.node_types.list_subtypes(
            str(node_type.slug), scope=scope
        )
        return shared_fields(subtypes)
