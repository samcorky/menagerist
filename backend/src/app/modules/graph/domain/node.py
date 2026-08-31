import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.shared_kernel.errors import ValidationError
from app.shared_kernel.mixins import Identifiable, SoftDeletable
from app.shared_kernel.slug import slugify


@dataclass(kw_only=True, eq=False)
class Node(Identifiable, SoftDeletable):
    """A single item in the collection graph - a collectible, person, event, etc."""

    name: str
    type: str | None = None
    description: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate invariants and normalise fields after construction."""
        if self.name is None or self.name.strip() == "":
            raise ValidationError("name must be provided")

        if self.type is not None:
            self.type = slugify(self.type)
            if self.type == "":
                raise ValidationError("type must be a non-empty string when provided")

        self.attributes = self.attributes or {}

    @classmethod
    def create(
        cls,
        *,
        name: str,
        type: str | None = None,
        description: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> Node:
        """Create a new node, generating its id and timestamps."""
        now = datetime.now(UTC)
        return cls(
            id=uuid.uuid7(),
            name=name,
            type=type,
            description=description,
            attributes=attributes or {},
            created_at=now,
            updated_at=now,
        )

    def update(
        self,
        *,
        name: str | None = None,
        type: str | None = None,
        description: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        """Apply partial changes to editable fields, validating invariants.

        `type` can only be set once — it cannot be changed after it has a value.
        """
        if name is not None:
            if name.strip() == "":
                raise ValidationError("name must be provided")
            self.name = name

        if type is not None:
            if self.type is not None:
                raise ValidationError("type cannot be changed after it is set")
            normalised = slugify(type)
            if normalised == "":
                raise ValidationError("type must be a non-empty string when provided")
            self.type = normalised

        if description is not None:
            self.description = description

        if attributes is not None:
            self.attributes = attributes

        self.touch()
