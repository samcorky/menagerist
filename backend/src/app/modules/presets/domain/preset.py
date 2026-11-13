import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.shared_kernel.errors import ValidationError
from app.shared_kernel.mixins import Identifiable, Owned, SoftDeletable

# `field` (a single field), `field_set` (a named group of fields, "field group" in
# the UI) and `choice_list` (a reusable set of choice options).
VALID_KINDS = frozenset({"field", "field_set", "choice_list"})


@dataclass(kw_only=True, eq=False)
class Preset(Identifiable, Owned, SoftDeletable):
    """A saved, reusable field definition - a saved field, field group or list.

    Owned by one person; nobody else sees or edits it.
    """

    kind: str
    label: str
    description: str | None = None
    definition: dict[str, Any] = field(default_factory=dict)
    version: int = 1

    def __post_init__(self) -> None:
        """Validate invariants after construction."""
        if self.kind not in VALID_KINDS:
            raise ValidationError(f"kind must be one of {sorted(VALID_KINDS)}")
        if self.label.strip() == "":
            raise ValidationError("label must be provided")

    @classmethod
    def create(
        cls,
        *,
        owner_id: uuid.UUID,
        kind: str,
        label: str,
        description: str | None = None,
        definition: dict[str, Any],
    ) -> Preset:
        """Create a new preset, generating its id and timestamps."""
        now = datetime.now(UTC)
        return cls(
            id=uuid.uuid7(),
            owner_id=owner_id,
            kind=kind,
            label=label,
            description=description,
            definition=definition,
            version=1,
            created_at=now,
            updated_at=now,
        )

    def update(
        self,
        *,
        label: str | None = None,
        description: str | None = None,
        definition: dict[str, Any] | None = None,
    ) -> None:
        """Apply partial changes, bumping `version` when the definition changes."""
        if label is not None:
            if label.strip() == "":
                raise ValidationError("label must be provided")
            self.label = label
        if description is not None:
            self.description = description
        if definition is not None:
            self.definition = definition
            self.version += 1
        self.touch()
