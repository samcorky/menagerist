import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.shared_kernel.errors import ValidationError
from app.shared_kernel.mixins import Identifiable, SoftDeletable
from app.shared_kernel.slug import slugify


@dataclass(kw_only=True, eq=False)
class NodeType(Identifiable, SoftDeletable):
    """A controlled vocabulary entry for the node type field."""

    slug: str
    label: str
    description: str | None = None
    attributes_schema: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        """Validate required fields after dataclass initialisation."""
        if not self.slug or not self.slug.strip():
            raise ValidationError("slug must be provided")
        if not self.label or not self.label.strip():
            raise ValidationError("label must be provided")

    @classmethod
    def create(
        cls,
        *,
        slug: str,
        label: str,
        description: str | None = None,
        attributes_schema: dict[str, Any] | None = None,
    ) -> NodeType:
        """Create a new NodeType, generating its id and timestamps."""
        now = datetime.now(UTC)
        return cls(
            id=uuid.uuid7(),
            slug=slugify(slug),
            label=label,
            description=description,
            attributes_schema=attributes_schema,
            created_at=now,
            updated_at=now,
        )

    def update(
        self,
        *,
        label: str | None = None,
        description: str | None = None,
        attributes_schema: dict[str, Any] | None = None,
    ) -> None:
        """Apply partial changes to editable fields. Slug is immutable."""
        if label is not None:
            if not label.strip():
                raise ValidationError("label must be provided")
            self.label = label
        if description is not None:
            self.description = description
        if attributes_schema is not None:
            self.attributes_schema = attributes_schema
        self.touch()
