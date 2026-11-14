"""A catalogue entry: a named group of presets, or of starter types, to install."""

from dataclasses import dataclass
from enum import StrEnum

from app.modules.catalogue.domain.errors import InvalidEntryError
from app.modules.transfer.domain.bundle import (
    PackItemType,
    PackPreset,
    PackRelationshipType,
)


class EntrySection(StrEnum):
    """Where an entry is shown, and what kind of thing it installs."""

    CHOICE_LIST = "choice_list"
    FIELD = "field"
    FIELD_GROUP = "field_group"
    STARTER_TYPES = "starter_types"


@dataclass(kw_only=True, frozen=True, eq=False)
class CatalogueEntry:
    """Something a person can install: presets, or item and relationship types."""

    id: str
    title: str
    description: str
    section: EntrySection
    presets: tuple[PackPreset, ...] = ()
    item_types: tuple[PackItemType, ...] = ()
    relationship_types: tuple[PackRelationshipType, ...] = ()

    def __post_init__(self) -> None:
        """Reject an empty entry, or one that mixes presets with types."""
        types = bool(self.item_types or self.relationship_types)
        if not self.presets and not types:
            raise InvalidEntryError(f"entry '{self.id}' has nothing to install")
        if self.presets and types:
            raise InvalidEntryError(f"entry '{self.id}' mixes presets with types")
