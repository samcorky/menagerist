import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from app.modules.examples.domain.installation import EntityKind
from app.modules.examples.ports.unit_of_work import ExampleRepos
from app.shared_kernel.access import Access, Content
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class ListExampleEntitiesQuery:
    """Request to list the entities owned by active example sets."""


@dataclass(kw_only=True, frozen=True, eq=False)
class ExampleEntities:
    """The ids of items, item types and collections an active example set owns."""

    item_ids: list[uuid.UUID]
    item_type_ids: list[uuid.UUID]
    collection_ids: list[uuid.UUID]


class ListExampleEntities(
    QueryHandler[ExampleRepos, ListExampleEntitiesQuery, ExampleEntities]
):
    """List what the viewer's own active example sets own."""

    access: ClassVar[Access] = Content()

    async def _handle(
        self,
        query: ListExampleEntitiesQuery,
        actor: Actor,
    ) -> ExampleEntities:
        """Return the owned item, item type and collection ids across installations."""
        active = await self._repos.installations.list_active(scope=self.scope(actor))
        return ExampleEntities(
            item_ids=[r.entity_id for i in active for r in i.owned(EntityKind.ITEM)],
            item_type_ids=[
                r.entity_id for i in active for r in i.owned(EntityKind.ITEM_TYPE)
            ],
            collection_ids=[
                r.entity_id for i in active for r in i.owned(EntityKind.COLLECTION)
            ],
        )
