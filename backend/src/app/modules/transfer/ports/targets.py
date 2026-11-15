import uuid
from collections.abc import Mapping, Sequence  # noqa: TC003
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from app.modules.transfer.domain.bundle import (  # noqa: TC001
    BundleCollection,
    BundleConnection,
    BundleItem,
    BundleItemType,
    BundlePreset,
    BundleRelationshipType,
)
from app.modules.transfer.domain.entity_kind import EntityKind  # noqa: TC001


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


class EntityTarget(Protocol):
    """Inspects and removes entities of one kind by id, for removing a bundle.

    `PresetTarget` and `CollectionTarget` have this shape; a caller passes others
    (an example's generated covers) by kind.
    """

    async def inspect(self, entity_id: uuid.UUID, /) -> Inspection | None:
        """Return the entity as it is now, or `None` if it is gone."""
        ...

    async def remove(self, entity_id: uuid.UUID, /) -> RemoveResult:
        """Remove the entity, or report that it is gone or still in use."""
        ...


class PresetTarget(Protocol):
    """Creates, inspects and removes presets, owned by another module."""

    async def ensure(self, presets: Sequence[BundlePreset]) -> list[PresetOutcome]:
        """Create each preset unless an identical one exists; one outcome each."""
        ...

    async def existing(self, presets: Sequence[BundlePreset]) -> list[bool]:
        """Say, in order, whether the person already has an identical preset."""
        ...

    async def check(self, presets: Sequence[BundlePreset]) -> None:
        """Refuse the presets if `ensure` would refuse them; nothing is stored.

        Raises:
            ValidationError: a preset is malformed, or there are too many.
        """
        ...

    async def read(self, preset_ids: Sequence[uuid.UUID]) -> list[BundlePreset]:
        """Return the person's presets with `preset_ids`, in order; `ref` is the id.

        Raises:
            NotFoundError: an id is not one of the person's live presets.
        """
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
        self, spec: BundleRelationshipType, presets: Mapping[str, uuid.UUID]
    ) -> Created:
        """Create the relationship type, resolving `$preset` markers with `presets`."""
        ...

    async def create_item_type(
        self, spec: BundleItemType, presets: Mapping[str, uuid.UUID]
    ) -> Created:
        """Create the item type, resolving `$preset` markers with `presets`."""
        ...

    async def read_item_types(
        self, type_ids: Sequence[uuid.UUID]
    ) -> list[BundleItemType]:
        """Return the person's item types with `type_ids`, in order; `ref` is the id.

        A field that uses a saved list names it as a `$preset` marker whose ref is
        the list's id, so a bundle that holds the list can resolve it again.

        Raises:
            NotFoundError: an id is not one of the person's live item types.
        """
        ...

    async def read_relationship_types(
        self, type_ids: Sequence[uuid.UUID]
    ) -> list[BundleRelationshipType]:
        """Return the person's relationship types with `type_ids`, as item types are.

        Raises:
            NotFoundError: an id is not one of the person's live relationship types.
        """
        ...

    async def create_item(
        self, spec: BundleItem, *, type_slug: str | None
    ) -> Created:
        """Create the item under the item type `type_slug`."""
        ...

    async def create_connection(
        self,
        spec: BundleConnection,
        *,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
        type_slug: str,
    ) -> Created:
        """Create the connection between two created items."""
        ...

    async def connection_exists(
        self, source_id: uuid.UUID, target_id: uuid.UUID, type_slug: str
    ) -> bool:
        """Whether a live connection of `type_slug` already runs source to target."""
        ...

    async def inspect(
        self, kind: EntityKind, entity_id: uuid.UUID
    ) -> Inspection | None:
        """Return the entity as it is now, or `None` if it is gone."""
        ...

    async def remove(self, kind: EntityKind, entity_id: uuid.UUID) -> RemoveResult:
        """Remove the entity, or report that it is gone or still in use."""
        ...


class CollectionTarget(Protocol):
    """Creates, inspects and removes collections, owned by another module.

    For a collection, `Created.content` and `Inspection.content` are
    `{"name": ..., "description": ..., "members": [sorted UUID strings]}`, so the
    hash notices a rename, a description change and any change in membership.
    A smart collection also has `"definition"` (as stored) and no members.
    `Inspection.has_user_data` and `still_in_use` stay false: a changed membership
    already counts as an edit.
    """

    async def create_collection(
        self, spec: BundleCollection, *, item_ids: Sequence[uuid.UUID]
    ) -> Created:
        """Create the collection holding the created items `item_ids`, in order.

        A spec with a `definition` makes a smart collection and `item_ids` is empty.
        """
        ...

    async def inspect(self, collection_id: uuid.UUID) -> Inspection | None:
        """Return the collection as it is now, or `None` if it is gone."""
        ...

    async def remove(self, collection_id: uuid.UUID) -> RemoveResult:
        """Remove the collection, or report that it is already gone."""
        ...


class CoverTarget(Protocol):
    """Creates, inspects and removes the generated covers of example items.

    For a cover, `Created.content` and `Inspection.content` are
    `{"style": ..., "name": ..., "sha256": ...}`; `sha256` is of the image's bytes,
    or `None` once the image is no longer the item's cover. So a replaced image
    reads as an edit. `Created.entity_id` identifies the cover itself, not the item.
    `Inspection.has_user_data` and `still_in_use` stay false.
    """

    async def create(self, item_id: uuid.UUID, name: str, style: str) -> Created:
        """Draw a cover for `name` in `style` and make it the item's cover."""
        ...

    async def inspect(self, cover_id: uuid.UUID) -> Inspection | None:
        """Return the cover as it is now, or `None` if it is gone."""
        ...

    async def remove(self, cover_id: uuid.UUID) -> RemoveResult:
        """Remove the cover and its stored files, or report that it is gone."""
        ...

    async def has_cover(self, item_id: uuid.UUID) -> bool:
        """Whether the item already has a cover image (a pack's or the person's)."""
        ...
