import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from app.modules.presets.application.create_preset import CreatePresetCommand
from app.modules.presets.application.update_preset import UpdatePresetCommand

if TYPE_CHECKING:
    from app.modules.presets.domain.preset import Preset

_PRESET_EXAMPLE: dict[str, Any] = {
    "id": "01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e30",
    "kind": "field",
    "label": "Condition",
    "description": None,
    "definition": {
        "property": {
            "title": "Condition",
            "type": "string",
            "enum": ["Mint", "Near Mint", "VG+"],
            "x-menagerist": {"kind": "choice"},
        }
    },
    "version": 1,
    "builtin": False,
    "created_at": "2026-08-23T10:14:44.465954Z",
    "updated_at": "2026-08-23T10:14:44.465954Z",
}


class CreatePresetRequest(BaseModel):
    """Request body for saving a new preset."""

    model_config = ConfigDict(json_schema_extra={"examples": [_PRESET_EXAMPLE]})

    kind: str
    label: str
    description: str | None = Field(default=None)
    definition: dict[str, Any] = Field(default_factory=dict)

    def to_command(self) -> CreatePresetCommand:
        """Convert this request into a `CreatePresetCommand`."""
        return CreatePresetCommand(
            kind=self.kind,
            label=self.label,
            description=self.description,
            definition=self.definition,
        )


class UpdatePresetRequest(BaseModel):
    """Request body for updating a preset. Omitted fields are left unchanged.

    Setting `definition` bumps the preset's `version`.
    """

    label: str | None = Field(default=None)
    description: str | None = Field(default=None)
    definition: dict[str, Any] | None = Field(default=None)

    def to_command(self, preset_id: uuid.UUID) -> UpdatePresetCommand:
        """Convert this request into an `UpdatePresetCommand` for `preset_id`."""
        return UpdatePresetCommand(
            preset_id=preset_id,
            label=self.label,
            description=self.description,
            definition=self.definition,
        )


class PresetResponse(BaseModel):
    """A preset as returned by the API."""

    model_config = ConfigDict(json_schema_extra={"examples": [_PRESET_EXAMPLE]})

    id: uuid.UUID
    kind: str
    label: str
    description: str | None = Field(default=None)
    definition: dict[str, Any]
    version: int
    builtin: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, preset: Preset) -> PresetResponse:
        """Build a response from a domain `Preset`."""
        return cls(
            id=preset.id,
            kind=preset.kind,
            label=preset.label,
            description=preset.description,
            definition=preset.definition,
            version=preset.version,
            builtin=preset.builtin,
            created_at=preset.created_at,
            updated_at=preset.updated_at,
        )
