import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from app.modules.collections.domain.errors import InvalidCollectionError
from app.shared_kernel.mixins import Identifiable, SoftDeletable
from app.shared_kernel.slug import Slug

MAX_NAME_LENGTH = 120


class CollectionKind(StrEnum):
    """How a collection decides what it holds."""

    MANUAL = "manual"


class Visibility(StrEnum):
    """Who may see a collection."""

    PRIVATE = "private"


def _clean_name(name: str) -> str:
    cleaned = name.strip()
    if not 1 <= len(cleaned) <= MAX_NAME_LENGTH:
        raise InvalidCollectionError(
            f"A collection name must be 1 to {MAX_NAME_LENGTH} characters."
        )
    return cleaned


@dataclass(kw_only=True, eq=False)
class Collection(Identifiable, SoftDeletable):
    """A named shelf that refers to items by id and never owns them."""

    name: str
    slug: Slug
    description: str | None = None
    kind: CollectionKind = CollectionKind.MANUAL
    owner_id: uuid.UUID
    visibility: Visibility = Visibility.PRIVATE

    @classmethod
    def create(
        cls,
        *,
        name: str,
        slug: Slug,
        owner_id: uuid.UUID,
        description: str | None = None,
    ) -> Collection:
        """Create a manual, private collection with a new id and timestamps.

        Raises:
            InvalidCollectionError: If the trimmed name is not 1 to 120 characters.
        """
        now = datetime.now(UTC)
        return cls(
            id=uuid.uuid7(),
            name=_clean_name(name),
            slug=slug,
            description=description,
            owner_id=owner_id,
            created_at=now,
            updated_at=now,
        )

    def rename(self, name: str) -> None:
        """Change the name, leaving the slug alone so links keep working.

        Raises:
            InvalidCollectionError: If the trimmed name is not 1 to 120 characters.
        """
        self.name = _clean_name(name)
        self.touch()


@dataclass(kw_only=True, frozen=True, eq=False)
class Membership:
    """An item's place on a collection."""

    collection_id: uuid.UUID
    item_id: uuid.UUID
    added_at: datetime
