import uuid
from collections.abc import Mapping, Sequence  # noqa: TC003
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from app.modules.examples.domain.installation import EntityKind  # noqa: TC001
from app.modules.examples.domain.pack import (  # noqa: TC001
    PackConnection,
    PackItem,
    PackItemType,
    PackPreset,
    PackRelationshipType,
)


@dataclass(kw_only=True, frozen=True, eq=False)
class Created:
    """An entity a target created; `content` is what the pack defines, as stored."""

    entity_id: uuid.UUID
    content: dict[str, Any]


@dataclass(kw_only=True, frozen=True, eq=False)
class Inspection:
    """An entity as it is now; `content` is comparable with `Created.content`."""

    content: dict[str, Any]
    has_user_data: bool = False
    still_in_use: bool = False


@dataclass(kw_only=True, frozen=True, eq=False)
class PresetOutcome:
    """One pack preset resolved to a real preset; `created` is false if it existed."""

    ref: str
    entity_id: uuid.UUID
    created: bool
    content: dict[str, Any]


class RemoveResult(Enum):
    """What happened when a target was asked to remove an entity."""

    REMOVED = "removed"
    ALREADY_GONE = "already_gone"
    REFUSED_IN_USE = "refused_in_use"


class PresetTarget(Protocol):
    """Creates, inspects and removes presets, owned by another module."""

    async def ensure(self, presets: Sequence[PackPreset]) -> list[PresetOutcome]:
        """Create each preset unless an identical one exists; one outcome each."""
        ...

    async def inspect(self, preset_id: uuid.UUID) -> Inspection | None:
        """Return the preset as it is now, or `None` if it is gone."""
        ...

    async def remove(self, preset_id: uuid.UUID) -> RemoveResult:
        """Remove the preset, or report that it is gone or still referenced."""
        ...


class GraphTarget(Protocol):
    """Creates, inspects and removes types, items and connections."""

    async def slug_taken(self, kind: EntityKind, slug: str) -> bool:
        """Whether a live item type or relationship type already has `slug`."""
        ...

    async def create_relationship_type(
        self, spec: PackRelationshipType, presets: Mapping[str, uuid.UUID]
    ) -> Created:
        """Create the relationship type, resolving `$preset` markers with `presets`."""
        ...

    async def create_item_type(
        self, spec: PackItemType, presets: Mapping[str, uuid.UUID]
    ) -> Created:
        """Create the item type, resolving `$preset` markers with `presets`."""
        ...

    async def create_item(self, spec: PackItem, *, type_slug: str) -> Created:
        """Create the item under the item type `type_slug`."""
        ...

    async def create_connection(
        self,
        spec: PackConnection,
        *,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
        type_slug: str,
    ) -> Created:
        """Create the connection between two created items."""
        ...

    async def inspect(
        self, kind: EntityKind, entity_id: uuid.UUID
    ) -> Inspection | None:
        """Return the entity as it is now, or `None` if it is gone."""
        ...

    async def remove(self, kind: EntityKind, entity_id: uuid.UUID) -> RemoveResult:
        """Remove the entity, or report that it is gone or still in use."""
        ...
