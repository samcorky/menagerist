import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.modules.presets.domain.errors import BuiltinPresetError
from app.shared_kernel.errors import ValidationError
from app.shared_kernel.mixins import Identifiable, SoftDeletable

# `field` (a single field), `field_set` (a named group of fields, "field group" in
# the UI) and `choice_list` (a reusable set of choice options).
VALID_KINDS = frozenset({"field", "field_set", "choice_list"})


@dataclass(kw_only=True, eq=False)
class Preset(Identifiable, SoftDeletable):
    """A saved, reusable field definition - a saved field, field group or list."""

    kind: str
    label: str
    description: str | None = None
    definition: dict[str, Any] = field(default_factory=dict)
    version: int = 1
    builtin: bool = False

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
        kind: str,
        label: str,
        description: str | None = None,
        definition: dict[str, Any],
        builtin: bool = False,
    ) -> Preset:
        """Create a new preset, generating its id and timestamps."""
        now = datetime.now(UTC)
        return cls(
            id=uuid.uuid7(),
            kind=kind,
            label=label,
            description=description,
            definition=definition,
            version=1,
            builtin=builtin,
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
        """Apply partial changes, bumping `version` when the definition changes.

        :raises BuiltinPresetError: a built-in preset cannot be edited.
        """
        if self.builtin:
            raise BuiltinPresetError(f"Preset {self.id} is built in and read-only")
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

    def soft_delete(self) -> None:
        """Mark this preset as deleted.

        :raises BuiltinPresetError: a built-in preset cannot be deleted.
        """
        if self.builtin:
            raise BuiltinPresetError(f"Preset {self.id} is built in and read-only")
        super().soft_delete()
