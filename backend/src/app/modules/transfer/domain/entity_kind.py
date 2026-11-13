"""What kind of entity a bundle creates."""

from enum import StrEnum


class EntityKind(StrEnum):
    """What kind of entity an installation created."""

    PRESET = "preset"
    RELATIONSHIP_TYPE = "relationship_type"
    ITEM_TYPE = "item_type"
    ITEM = "item"
    CONNECTION = "connection"
    COLLECTION = "collection"
    COVER = "cover"
