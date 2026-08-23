import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.shared_kernel.errors import ValidationError
from app.shared_kernel.mixins import Identifiable, SoftDeletable


@dataclass(kw_only=True, eq=False)
class Node(Identifiable, SoftDeletable):
    """A single item in the collection graph - a collectible, person, event, etc.

    `type` is a free-text string rather than an enum or a per-type table -
    new collectible kinds are added by writing a new `type` value, not a
    migration. `attributes` is the type-specific payload.
    """

    type: str
    attributes: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate invariants and normalise fields after construction."""
        if self.type is None or self.type.strip() == "":
            raise ValidationError("type must be provided")

        self.attributes = self.attributes or {}

    @classmethod
    def create(cls, *, type: str, attributes: dict[str, Any] | None = None) -> Node:
        """Create a new node, generating its id and timestamps."""
        now = datetime.now(UTC)
        return cls(
            id=uuid.uuid7(),
            type=type,
            attributes=attributes or {},
            created_at=now,
            updated_at=now,
        )
