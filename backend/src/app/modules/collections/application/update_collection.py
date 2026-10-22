import uuid
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
from app.modules.collections.domain.errors import (
    CollectionNotFoundError,
    InvalidCollectionError,
)
from app.modules.collections.ports.definition_checker import (
    DefinitionChecker,  # noqa: TC001
)
from app.modules.collections.ports.unit_of_work import CollectionsUnitOfWork
from app.shared_kernel.access import Access, Content
from app.shared_kernel.errors import ConflictError
from app.shared_kernel.guarded import GuardedCommandHandler

if TYPE_CHECKING:
    from app.modules.collections.ports.collection_repository import CollectionRepository
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor
    from app.shared_kernel.content_filter import ContentFilter
    from app.shared_kernel.slug import Slug

logger = structlog.get_logger()


@dataclass(kw_only=True)
class UpdateCollectionCommand:
    """Request to update a collection's name, description, slug or definition.

    `slug` sets the slug; `regenerate_slug` rebuilds it from the (new) name. The
    two are exclusive. The kind is immutable.
    """

    collection_id: uuid.UUID
    name: str | None = None
    description: str | None = None
    definition: dict[str, Any] | None = None
    slug: str | None = None
    regenerate_slug: bool = False


class UpdateCollection(
    GuardedCommandHandler[CollectionsUnitOfWork, UpdateCollectionCommand, Collection]
):
    """Update an existing collection's editable fields."""

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
        self, command: UpdateCollectionCommand, actor: Actor
    ) -> Collection:
        """Apply `command`'s changes to the collection and commit.

        A blank `description` clears it; `None` leaves it unchanged.

        Raises:
            CollectionNotFoundError: If the collection does not exist or is deleted.
            InvalidCollectionError: If the new name is not 1 to 120 characters, the
                slug is unusable or looks like an id, or both `slug` and
                `regenerate_slug` are given.
            ConflictError: If the slug belongs to another live collection of the
                actor.
            CollectionKindError: If a definition is given for a manual collection.
            InvalidDefinitionError: If the definition is malformed, with its path, or
                is too large, too deeply nested or not storable text.

        A definition for a manual collection is a `CollectionKindError` whatever
        it holds: the kind is checked before the definition is.
        """
        if command.slug is not None and command.regenerate_slug:
            raise InvalidCollectionError("Give either a slug or regenerate_slug.")
        wanted = None if command.slug is None else explicit_slug(command.slug)
        scope = self.scope(actor)
        async with self._uow as repos:
            collection = await repos.collections.get(command.collection_id, scope=scope)
            if collection is None:
                raise CollectionNotFoundError(
                    f"Collection {command.collection_id} not found"
                )
            self._guard.assert_can_modify(actor, collection.owner_id)
            if command.definition is not None:
                collection.ensure_dynamic()
                ensure_definition_within_limits(command.definition)
                await self._checker.check(command.definition, scope)
            if command.name is not None:
                collection.rename(command.name)
            if command.description is not None:
                collection.description = command.description.strip() or None
            if command.definition is not None:
                collection.replace_definition(command.definition)
            await self._apply_slug(
                repos.collections, collection, command, wanted, scope
            )
            collection.touch()
            await repos.collections.save(collection)
            await self._uow.commit()
        logger.info("collection updated", collection_id=command.collection_id)
        return collection

    @staticmethod
    async def _apply_slug(
        collections: CollectionRepository,
        collection: Collection,
        command: UpdateCollectionCommand,
        wanted: Slug | None,
        scope: ContentFilter,
    ) -> None:
        if wanted is not None:
            if wanted == collection.slug:
                return
            if await slug_is_held(
                collections, wanted.value, scope, excluding=collection.id
            ):
                raise ConflictError(f"A collection with slug '{wanted}' already exists")
            collection.rename_slug(wanted)
        elif command.regenerate_slug:
            collection.rename_slug(
                await free_slug(
                    collections, collection.name, scope, excluding=collection.id
                )
            )
