from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from app.modules.catalogue.domain.entry import EntrySection

if TYPE_CHECKING:
    from app.modules.catalogue.application.install_catalogue_entry import InstallOutcome
    from app.modules.catalogue.application.list_catalogue_entries import EntryStatus


ENTRY_EXAMPLE: dict[str, Any] = {
    "id": "condition-grades",
    "title": "Condition grades",
    "description": "Mint through Poor, for rating condition.",
    "section": "choice_list",
    "installed": False,
    "present": 0,
    "total": 1,
    "contents": ["Condition grades"],
}


class CatalogueEntryResponse(BaseModel):
    """A shipped entry and how much of it the person already has."""

    model_config = ConfigDict(json_schema_extra={"examples": [ENTRY_EXAMPLE]})

    id: str = Field(description="Stable id of the entry, used to install it.")
    title: str = Field(description="What the entry is called.")
    description: str = Field(description="What the entry holds, in a sentence.")
    section: EntrySection
    installed: bool = Field(
        description="Whether everything in the entry is already yours."
    )
    present: int = Field(description="How many of the entry's things you already have.")
    total: int = Field(description="How many things the entry holds.")
    contents: list[str] = Field(description="The names of the things the entry holds.")

    @classmethod
    def from_domain(cls, status: EntryStatus) -> CatalogueEntryResponse:
        """Build from an entry status."""
        entry = status.entry
        labels = [
            *(p.label for p in entry.presets),
            *(t.label for t in entry.item_types),
            *(t.label for t in entry.relationship_types),
        ]
        return cls(
            id=entry.id,
            title=entry.title,
            description=entry.description,
            section=entry.section,
            installed=status.installed,
            present=status.present,
            total=status.total,
            contents=labels,
        )


CATALOGUE_EXAMPLE: list[dict[str, Any]] = [ENTRY_EXAMPLE]


OUTCOME_EXAMPLE: dict[str, Any] = {
    "entry_id": "starter-types",
    "presets_created": 0,
    "presets_skipped": 0,
    "item_types_created": 5,
    "item_types_skipped": 1,
    "relationship_types_created": 4,
    "relationship_types_skipped": 0,
}


class InstallOutcomeResponse(BaseModel):
    """What installing an entry created, and what the person already had."""

    model_config = ConfigDict(json_schema_extra={"examples": [OUTCOME_EXAMPLE]})

    entry_id: str = Field(description="The entry that was installed.")
    presets_created: int = Field(description="Saved lists, fields or groups added.")
    presets_skipped: int = Field(
        description="Saved lists, fields or groups you already had."
    )
    item_types_created: int = Field(description="Item types added.")
    item_types_skipped: int = Field(
        description="Item types skipped because the name was taken."
    )
    relationship_types_created: int = Field(description="Relationship types added.")
    relationship_types_skipped: int = Field(
        description="Relationship types skipped because the name was taken."
    )

    @classmethod
    def from_domain(cls, outcome: InstallOutcome) -> InstallOutcomeResponse:
        """Build from the install outcome."""
        return cls(
            entry_id=outcome.entry_id,
            presets_created=outcome.presets_created,
            presets_skipped=outcome.presets_skipped,
            item_types_created=outcome.item_types_created,
            item_types_skipped=outcome.item_types_skipped,
            relationship_types_created=outcome.relationship_types_created,
            relationship_types_skipped=outcome.relationship_types_skipped,
        )
