import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.shared_kernel.errors import ValidationError
from app.shared_kernel.mixins import Identifiable, SoftDeletable
from app.shared_kernel.slug import Slug


@dataclass(kw_only=True, eq=False)
class EdgeType(Identifiable, SoftDeletable):
    """A controlled vocabulary entry for edge relationships."""

    slug: Slug
    label: str
    reverse_label: str | None = None
    description: str | None = None
    directional: bool = True
    attributes_schema: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        """Validate required fields after dataclass initialisation."""
        if not self.label or not self.label.strip():
            raise ValidationError("label must be provided")

    @classmethod
    def create(
        cls,
        *,
        slug: str,
        label: str,
        reverse_label: str | None = None,
        description: str | None = None,
        directional: bool = True,
        attributes_schema: dict[str, Any] | None = None,
    ) -> EdgeType:
        """Create a new EdgeType, generating its id and timestamps."""
        now = datetime.now(UTC)
        return cls(
            id=uuid.uuid7(),
            slug=Slug(slug),
            label=label,
            reverse_label=reverse_label,
            description=description,
            directional=directional,
            attributes_schema=attributes_schema,
            created_at=now,
            updated_at=now,
        )

    def update(
        self,
        *,
        label: str | None = None,
        reverse_label: str | None = None,
        description: str | None = None,
        directional: bool | None = None,
        attributes_schema: dict[str, Any] | None = None,
    ) -> None:
        """Apply partial changes. Slug is immutable."""
        if label is not None:
            if not label.strip():
                raise ValidationError("label must be provided")
            self.label = label
        if reverse_label is not None:
            self.reverse_label = reverse_label
        if description is not None:
            self.description = description
        if directional is not None:
            self.directional = directional
        if attributes_schema is not None:
            self.attributes_schema = attributes_schema
        self.touch()
