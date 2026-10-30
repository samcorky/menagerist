import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.shared_kernel.errors import ValidationError
from app.shared_kernel.mixins import Identifiable, Owned, SoftDeletable
from app.shared_kernel.slug import slugify


def _normalise_tags(tags: list[str]) -> list[str]:
    """Trim and lowercase tags, dropping blanks and duplicates while keeping order."""
    return list(dict.fromkeys(t for tag in tags if (t := tag.strip().lower())))


@dataclass(kw_only=True, eq=False)
class Node(Identifiable, Owned, SoftDeletable):
    """A single item in the collection graph - a collectible, person, event, etc."""

    name: str
    type: str | None = None
    description: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    favourite: bool = False
    tags: list[str] = field(default_factory=list)
    extra_schema: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        """Validate invariants and normalise fields after construction."""
        if self.name is None or self.name.strip() == "":
            raise ValidationError("name must be provided")

        if self.type is not None:
            self.type = slugify(self.type)
            if self.type == "":
                raise ValidationError("type must be a non-empty string when provided")

        self.attributes = self.attributes or {}
        self.tags = _normalise_tags(self.tags)

    @classmethod
    def create(
        cls,
        *,
        owner_id: uuid.UUID,
        name: str,
        type: str | None = None,
        description: str | None = None,
        attributes: dict[str, Any] | None = None,
        favourite: bool = False,
        tags: list[str] | None = None,
        extra_schema: dict[str, Any] | None = None,
    ) -> Node:
        """Create a new node, generating its id and timestamps."""
        now = datetime.now(UTC)
        return cls(
            id=uuid.uuid7(),
            owner_id=owner_id,
            name=name,
            type=type,
            description=description,
            attributes=attributes or {},
            favourite=favourite,
            tags=tags or [],
            extra_schema=extra_schema,
            created_at=now,
            updated_at=now,
        )

    def _set_if_given(self, **kwargs: object) -> None:
        """Set each attribute that is not None. For simple fields with no validation."""
        for attr, val in kwargs.items():
            if val is not None:
                setattr(self, attr, val)

    def _apply_type(self, type: str) -> None:
        normalised = slugify(type)
        if normalised == "":
            raise ValidationError("type must be a non-empty string when provided")
        self.type = normalised

    def clear_type(self) -> None:
        """Remove the type. The attribute values are kept."""
        self.type = None
        self.touch()

    def update(
        self,
        *,
        name: str | None = None,
        type: str | None = None,
        description: str | None = None,
        attributes: dict[str, Any] | None = None,
        favourite: bool | None = None,
        tags: list[str] | None = None,
        extra_schema: dict[str, Any] | None = None,
    ) -> None:
        """Apply partial changes to editable fields, validating invariants.

        `extra_schema` follows the same convention as `attributes_schema` on a
        node type: `None` leaves it unchanged (there is no way to clear it yet).
        `type` is replaced by a slug and left alone when `None`; use
        `clear_type` to remove it. The attributes are never touched by a type
        change.
        """
        if name is not None:
            if name.strip() == "":
                raise ValidationError("name must be provided")
            self.name = name

        if type is not None:
            self._apply_type(type)

        self._set_if_given(
            description=description,
            attributes=attributes,
            favourite=favourite,
            extra_schema=extra_schema,
        )
        if tags is not None:
            self.tags = _normalise_tags(tags)
        self.touch()
