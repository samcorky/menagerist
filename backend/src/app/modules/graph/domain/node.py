import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.shared_kernel.errors import ValidationError
from app.shared_kernel.mixins import Identifiable, SoftDeletable

_SLUG_INVALID_CHARS = re.compile(r"[^a-z0-9]+")


def _slugify(value: str) -> str:
    """Normalise a free-text value into a lowercase, hyphen-separated slug."""
    ascii_value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )
    return _SLUG_INVALID_CHARS.sub("-", ascii_value.lower()).strip("-")


@dataclass(kw_only=True, eq=False)
class Node(Identifiable, SoftDeletable):
    """A single item in the collection graph - a collectible, person, event, etc."""

    name: str
    type: str
    description: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate invariants and normalise fields after construction."""
        if self.name is None or self.name.strip() == "":
            raise ValidationError("name must be provided")

        if self.type is None or self.type.strip() == "":
            raise ValidationError("type must be provided")

        self.type = _slugify(self.type)
        if self.type == "":
            raise ValidationError("type must be provided")

        self.attributes = self.attributes or {}

    @classmethod
    def create(
        cls,
        *,
        name: str,
        type: str,
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
