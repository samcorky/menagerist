import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.shared_kernel.errors import ValidationError
from app.shared_kernel.mixins import Identifiable, SoftDeletable
from app.shared_kernel.slug import slugify


@dataclass(kw_only=True, eq=False)
class Edge(Identifiable, SoftDeletable):
    """A typed relationship connecting two node in the collection graph."""

    source_id: uuid.UUID
    target_id: uuid.UUID
    type: str
    attributes: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate invariants and normalise fields after construction."""
        if self.type is None or self.type.strip() == "":
            raise ValidationError("type must be provided")

        self.type = slugify(self.type)
        if self.type == "":
            raise ValidationError("type must be provided")

        if self.source_id == self.target_id:
            raise ValidationError("an edge cannot connect a node to itself")

        self.attributes = self.attributes or {}

    @classmethod
    def create(
        cls,
        *,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
        type: str,
        attributes: dict[str, Any] | None = None,
    ) -> Edge:
        """Create a new edge, generating its id and timestamps."""
        now = datetime.now(UTC)
        return cls(
            id=uuid.uuid7(),
            source_id=source_id,
            target_id=target_id,
            type=type,
            attributes=attributes or {},
            created_at=now,
            updated_at=now,
        )

    def update(self, *, attributes: dict[str, Any] | None = None) -> None:
        """Apply partial changes to editable fields, then touch `updated_at`.

        `source_id`, `target_id`, and `type` aren't editable here - changing
        what an edge connects or what it represents is a delete-and-recreate,
        not an edit.
        """
        if attributes is not None:
            self.attributes = attributes

        self.touch()
