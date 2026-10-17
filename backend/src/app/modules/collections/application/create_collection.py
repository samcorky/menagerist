from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import structlog

from app.modules.collections.domain.collection import Collection
from app.modules.collections.domain.errors import InvalidCollectionError
from app.modules.collections.ports.definition_checker import (
    DefinitionChecker,  # noqa: TC001
)
from app.modules.collections.ports.unit_of_work import CollectionsUnitOfWork
from app.shared_kernel.access_policy import AccessPolicy  # noqa: TC001
from app.shared_kernel.cqrs import ScopedCommandHandler
from app.shared_kernel.errors import ConflictError
from app.shared_kernel.slug import Slug, slugify

if TYPE_CHECKING:
    from app.modules.collections.ports.collection_repository import CollectionRepository
    from app.shared_kernel.access_scope import AccessScope
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()

_FALLBACK_SLUG = "collection"


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
    ScopedCommandHandler[CollectionsUnitOfWork, CreateCollectionCommand, Collection]
):
    """Create and persist a new collection owned by the acting user."""

    def __init__(
        self,
        uow: CollectionsUnitOfWork,
        policy: AccessPolicy,
        checker: DefinitionChecker,
    ) -> None:
        super().__init__(uow, policy)
        self._checker = checker

    async def handle(
        self, command: CreateCollectionCommand, actor: Actor
    ) -> Collection:
        """Create a collection from `command` and commit it.

        Raises:
            InvalidCollectionError: If the name or an explicit slug is unusable.
            InvalidDefinitionError: If the definition is malformed, with its path.
            ConflictError: If an explicit slug belongs to a live collection of the
                actor.
        """
        # Slugs are unique per owner: only collections the actor can see count.
        scope = self._policy.scope_for(actor)
        if command.definition is not None:
            await self._checker.check(command.definition, scope)
        async with self._uow as repos:
            if command.slug is None:
                slug = await _free_slug(repos.collections, command.name, scope)
            else:
                slug = _explicit_slug(command.slug)
                if (
                    await repos.collections.get_by_slug(slug.value, scope=scope)
                    is not None
                ):
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


def _explicit_slug(value: str) -> Slug:
    """Normalise a caller-supplied slug, mapping an unusable one to a 422."""
    try:
        return Slug(value)
    except ValueError as exc:
        raise InvalidCollectionError(
            "A collection slug must contain letters or numbers."
        ) from exc


async def _free_slug(
    collections: CollectionRepository, name: str, scope: AccessScope
) -> Slug:
    """Derive a slug from `name`, suffixing `-2`, `-3`... until it is unused."""
    base = slugify(name) or _FALLBACK_SLUG
    candidate = base
    number = 2
    while await collections.get_by_slug(candidate, scope=scope) is not None:
        candidate = f"{base}-{number}"
        number += 1
    return Slug(candidate)
