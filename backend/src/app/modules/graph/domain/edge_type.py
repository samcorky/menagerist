import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final, Literal

from app.shared_kernel.errors import ValidationError
from app.shared_kernel.mixins import Identifiable, Owned, SoftDeletable
from app.shared_kernel.slug import Slug

type Holder = Literal["source", "target", "none"]
HOLDERS: Final[tuple[Holder, ...]] = ("source", "target", "none")


def _check_holder(holder: str, *, directional: bool) -> None:
    if holder not in HOLDERS:
        raise ValidationError(f"holder must be one of: {', '.join(HOLDERS)}")
    if holder != "none" and not directional:
        raise ValidationError("A connection with no direction cannot hold items")


@dataclass(kw_only=True, eq=False)
class EdgeType(Identifiable, Owned, SoftDeletable):
    """A controlled vocabulary entry for edge relationships, owned by one person.

    `holder` says which end of a connection holds the other, for an item's
    contents and path: `source` for "Contains" (the box is the source), `target`
    for "Located in" (the box is the target), `none` when neither holds the
    other ("Published by"). Only a relationship with a direction can hold.
    """

    slug: Slug
    label: str
    reverse_label: str | None = None
    description: str | None = None
    directional: bool = True
    attributes_schema: dict[str, Any] | None = None
    holder: Holder = "none"

    def __post_init__(self) -> None:
        """Validate required fields after dataclass initialisation."""
        if not self.label or not self.label.strip():
            raise ValidationError("label must be provided")
        _check_holder(self.holder, directional=self.directional)

    @classmethod
    def create(
        cls,
        *,
        owner_id: uuid.UUID,
        slug: str,
        label: str,
        reverse_label: str | None = None,
        description: str | None = None,
        directional: bool = True,
        attributes_schema: dict[str, Any] | None = None,
        holder: Holder = "none",
    ) -> EdgeType:
        """Create a new EdgeType, generating its id and timestamps."""
        now = datetime.now(UTC)
        return cls(
            id=uuid.uuid7(),
            owner_id=owner_id,
            slug=Slug(slug),
            label=label,
            reverse_label=reverse_label,
            description=description,
            directional=directional,
            attributes_schema=attributes_schema,
            holder=holder,
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
        holder: Holder | None = None,
    ) -> None:
        """Apply partial changes. Slug is immutable.

        Raises:
            ValidationError: For a blank label, or a holder on a connection
                with no direction.
        """
        _check_holder(
            self.holder if holder is None else holder,
            directional=self.directional if directional is None else directional,
        )
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
        if holder is not None:
            self.holder = holder
        self.touch()
