import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Final

from app.modules.collections.domain.errors import (
    CollectionKindError,
    InvalidCollectionError,
)
from app.shared_kernel.mixins import Identifiable, SoftDeletable
from app.shared_kernel.slug import Slug

MAX_NAME_LENGTH = 120


class CollectionKind(StrEnum):
    """How a collection decides what it holds."""

    MANUAL = "manual"
    DYNAMIC = "dynamic"


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
    definition: dict[str, Any] | None = None
    # The totals shown on the collection: null means "automatic", a list is the
    # person's own choice (possibly none). Opaque to this module beyond its shape.
    summary: list[dict[str, Any]] | None = None

    @classmethod
    def create(
        cls,
        *,
        name: str,
        slug: Slug,
        owner_id: uuid.UUID,
        description: str | None = None,
        definition: dict[str, Any] | None = None,
    ) -> Collection:
        """Create a private collection with a new id and timestamps.

        The collection is dynamic when a `definition` is given, otherwise manual.

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
            kind=(
                CollectionKind.MANUAL if definition is None else CollectionKind.DYNAMIC
            ),
            definition=definition,
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

    def rename_slug(self, slug: Slug) -> None:
        """Change the slug, and with it the collection's link."""
        self.slug = slug
        self.touch()

    def ensure_dynamic(self) -> None:
        """Guard a change to the definition.

        Raises:
            CollectionKindError: If the collection is manual.
        """
        if self.kind is not CollectionKind.DYNAMIC:
            raise CollectionKindError("Only a smart collection has a definition.")

    def replace_definition(self, definition: dict[str, Any]) -> None:
        """Replace a dynamic collection's definition.

        Raises:
            CollectionKindError: If the collection is manual.
        """
        self.ensure_dynamic()
        self.definition = definition
        self.touch()

    def replace_summary(self, summary: list[dict[str, Any]] | None) -> None:
        """Set the totals shown on the collection; None goes back to automatic.

        Raises:
            InvalidCollectionError: If it is not a short list of small objects.
        """
        if summary is not None:
            _check_summary(summary)
        self.summary = summary
        self.touch()

    def ensure_manual_membership(self) -> None:
        """Guard a change to the collection's items.

        Raises:
            CollectionKindError: If the collection is dynamic.
        """
        if self.kind is CollectionKind.DYNAMIC:
            raise CollectionKindError(
                "Items cannot be added to or removed from a smart collection."
            )


@dataclass(kw_only=True, frozen=True, eq=False)
class Membership:
    """An item's place on a collection."""

    collection_id: uuid.UUID
    item_id: uuid.UUID
    added_at: datetime


MAX_SUMMARY_ENTRIES: Final = 10
_SUMMARY_KEYS: Final = frozenset({"fn", "type", "key", "origin"})
_MAX_SUMMARY_TEXT: Final = 200


def _check_summary(summary: list[dict[str, Any]]) -> None:
    """Refuse a summary that is not up to ten flat objects of short text.

    Whether each entry names a real field and a function it can read is for the
    aggregate that runs it to say, since fields can change after it is saved.
    """
    if len(summary) > MAX_SUMMARY_ENTRIES:
        raise InvalidCollectionError(
            f"A summary has up to {MAX_SUMMARY_ENTRIES} totals."
        )
    for entry in summary:
        if not isinstance(entry, dict) or "fn" not in entry:
            raise InvalidCollectionError("Each total is an object with an `fn`.")
        if set(entry) - _SUMMARY_KEYS:
            raise InvalidCollectionError(
                "A total has only `fn`, `type`, `key` and `origin`."
            )
        for value in entry.values():
            if (
                not isinstance(value, str)
                or not value
                or len(value) > _MAX_SUMMARY_TEXT
                or "\x00" in value
            ):
                raise InvalidCollectionError(
                    "Each part of a total is short, non-empty text."
                )
