"""Slug rules shared by creating and updating a collection."""

import uuid
from typing import TYPE_CHECKING

from app.modules.collections.domain.errors import InvalidCollectionError
from app.shared_kernel.slug import Slug, slugify

if TYPE_CHECKING:
    from app.modules.collections.ports.collection_repository import CollectionRepository
    from app.shared_kernel.access_scope import AccessScope

_FALLBACK_SLUG = "collection"
MAX_SLUG_LENGTH = 120
# Leaves room for a `-2`, `-3`... suffix when a derived slug is taken.
_DERIVED_SLUG_LENGTH = MAX_SLUG_LENGTH - 8


_TOO_LONG = f"A collection slug can be up to {MAX_SLUG_LENGTH} characters."


def is_uuid_shaped(value: str) -> bool:
    """Whether `value` parses as a UUID, so would be read as an id in a path."""
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


def explicit_slug(value: str) -> Slug:
    """Normalise a caller-supplied slug, mapping an unusable one to a 400."""
    if len(value) > MAX_SLUG_LENGTH:
        raise InvalidCollectionError(_TOO_LONG)
    try:
        slug = Slug(value)
    except ValueError as exc:
        raise InvalidCollectionError(
            "A collection slug must contain letters or numbers."
        ) from exc
    if len(slug.value) > MAX_SLUG_LENGTH:
        raise InvalidCollectionError(_TOO_LONG)
    if is_uuid_shaped(slug.value):
        raise InvalidCollectionError("A collection slug cannot look like an id.")
    return slug


async def free_slug(
    collections: CollectionRepository,
    name: str,
    scope: AccessScope,
    *,
    excluding: uuid.UUID | None = None,
) -> Slug:
    """Derive a slug from `name`, suffixing `-2`, `-3`... until it is unused.

    A candidate that looks like an id is skipped too, so a derived slug is never
    ambiguous in a path. The collection `excluding` does not count as a holder.
    """
    base = slugify(name)[:_DERIVED_SLUG_LENGTH].strip("-") or _FALLBACK_SLUG
    candidate = base
    number = 2
    while is_uuid_shaped(candidate) or await _held(
        collections, candidate, scope, excluding
    ):
        candidate = f"{base}-{number}"
        number += 1
    return Slug(candidate)


async def slug_is_held(
    collections: CollectionRepository,
    slug: str,
    scope: AccessScope,
    *,
    excluding: uuid.UUID | None = None,
) -> bool:
    """Whether another live collection in `scope` already has `slug`."""
    return await _held(collections, slug, scope, excluding)


async def _held(
    collections: CollectionRepository,
    slug: str,
    scope: AccessScope,
    excluding: uuid.UUID | None,
) -> bool:
    found = await collections.get_by_slug(slug, scope=scope)
    return found is not None and found.id != excluding
