from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

import structlog

from app.modules.collections.application.collection_slugs import (
    explicit_slug,
    free_slug,
    slug_is_held,
)
from app.modules.collections.application.definition_limits import (
    ensure_definition_within_limits,
)
from app.modules.collections.domain.collection import Collection
from app.modules.collections.ports.definition_checker import (
    DefinitionChecker,  # noqa: TC001
)
from app.modules.collections.ports.unit_of_work import CollectionsUnitOfWork
from app.shared_kernel.access import Access, Content
from app.shared_kernel.errors import ConflictError
from app.shared_kernel.guarded import GuardedCommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class CreateCollectionCommand:
    """Request to create a collection; the slug is derived from the name if omitted.

    A `definition` makes it a smart collection, stored as given.
    """

    name: str
    description: str | None = None
    slug: str | None = None
    definition: dict[str, Any] | None = None


class CreateCollection(
    GuardedCommandHandler[CollectionsUnitOfWork, CreateCollectionCommand, Collection]
):
    """Create and persist a new collection owned by the acting user."""

    access: ClassVar[Access] = Content()

    def __init__(
        self,
        uow: CollectionsUnitOfWork,
        guard: AccessGuard,
        checker: DefinitionChecker,
    ) -> None:
        super().__init__(uow, guard)
        self._checker = checker

    async def _handle(
        self, command: CreateCollectionCommand, actor: Actor
    ) -> Collection:
        """Create a collection from `command` and commit it.

        Raises:
            InvalidCollectionError: If the name or an explicit slug is unusable, or the
                slug looks like an id.
            InvalidDefinitionError: If the definition is malformed, with its path, or
                is too large, too deeply nested or not storable text.
            ConflictError: If an explicit slug belongs to a live collection of the
                actor.
        """
        # Slugs are unique per owner: only collections the actor can see count.
        scope = self.scope(actor)
        if command.definition is not None:
            ensure_definition_within_limits(command.definition)
            await self._checker.check(command.definition, scope)
        async with self._uow as repos:
            if command.slug is None:
                slug = await free_slug(repos.collections, command.name, scope)
            else:
                slug = explicit_slug(command.slug)
                if await slug_is_held(repos.collections, slug.value, scope):
                    raise ConflictError(
                        f"A collection with slug '{slug}' already exists"
                    )
            collection = Collection.create(
                name=command.name,
                slug=slug,
                owner_id=actor.id,
                description=(command.description or "").strip() or None,
                definition=command.definition,
            )
            await repos.collections.add(collection)
            await self._uow.commit()
        logger.info("collection created", collection_id=collection.id, slug=slug.value)
        return collection
