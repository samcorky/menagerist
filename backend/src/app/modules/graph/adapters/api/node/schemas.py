import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.graph.application.create_node import CreateNodeCommand
from app.modules.graph.application.duplicate_node import DuplicateNodeCommand
from app.modules.graph.application.update_node import UpdateNodeCommand
from app.modules.graph.domain.query import ItemFieldUse, TypeCount  # noqa: TC001
from app.platform.request_model import RequestModel

if TYPE_CHECKING:
    from app.modules.graph.application.search_node_counts import SearchCount
    from app.modules.graph.application.search_nodes import SearchNodesResult
    from app.modules.graph.domain.node import Node

_NODE_EXAMPLE: dict[str, Any] = {
    "id": "01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e10",
    "name": "Alien",
    "type": "film",
    "description": "A 1979 science fiction horror film directed by Ridley Scott.",
    "attributes": {"year": 1979},
    "favourite": False,
    "tags": ["sci-fi", "horror"],
    "extra_schema": None,
    "created_at": "2026-08-23T10:14:44.465954Z",
    "updated_at": "2026-08-23T10:14:44.465954Z",
}

_NODE_MINIMAL_EXAMPLE: dict[str, Any] = {
    "id": "01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e11",
    "name": "Untitled capture",
    "type": None,
    "description": None,
    "attributes": {},
    "favourite": False,
    "tags": [],
    "extra_schema": None,
    "created_at": "2026-08-23T10:14:44.465954Z",
    "updated_at": "2026-08-23T10:14:44.465954Z",
}


class DuplicateNodeRequest(RequestModel):
    """Request body for copying an item. The copy's `name` is required.

    The original's fields and tags are always copied. Each flag adds one more
    thing from it; connections, media and cover default to off, collections to on.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"name": "Copy of Alien"},
                {
                    "name": "Alien (director's cut)",
                    "copy_relationships": True,
                    "copy_media": True,
                    "copy_cover": True,
                    "copy_collections": False,
                },
            ]
        }
    )

    name: str = Field(description="The copy's name.")
    copy_relationships: bool = Field(
        description="Also copy the item's connections.", default=False
    )
    copy_media: bool = Field(
        description="Also attach the item's media to the copy.", default=False
    )
    copy_cover: bool = Field(
        description="Also give the copy the item's cover.", default=False
    )
    copy_collections: bool = Field(
        description="Also add the copy to the item's collections.", default=True
    )

    def to_command(self, node_id: uuid.UUID) -> DuplicateNodeCommand:
        """Convert this request into a `DuplicateNodeCommand` for `node_id`."""
        return DuplicateNodeCommand(
            node_id=node_id,
            name=self.name,
            copy_relationships=self.copy_relationships,
            copy_media=self.copy_media,
            copy_cover=self.copy_cover,
            copy_collections=self.copy_collections,
        )


class CreateNodeRequest(RequestModel):
    """Request body for creating a node. Only `name` is required."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "Alien",
                    "type": "film",
                    "description": (
                        "A 1979 science fiction horror "
                        + "film directed by Ridley Scott."
                    ),
                    "attributes": {"year": 1979},
                },
                {"name": "Quick capture"},
            ]
        }
    )

    name: str = Field(description="The item's name.")
    type: str | None = Field(
        description="The slug of its item type; none for an untyped item.", default=None
    )
    description: str | None = Field(
        description="Free text about the item.", default=None
    )
    attributes: dict[str, Any] = Field(
        description="Its field values, keyed by field key.", default_factory=dict
    )
    favourite: bool = Field(description="Whether it is a favourite.", default=False)
    tags: list[str] = Field(description="Its tags.", default_factory=list)
    extra_schema: dict[str, Any] | None = Field(
        description="Fields of its own, beyond its type's, as a JSON Schema.",
        default=None,
    )

    @field_validator("type", mode="before")
    @classmethod
    def coerce_empty_type_to_none(cls, v: object) -> object:
        """Treat an empty or whitespace-only type string as absent."""
        if isinstance(v, str) and not v.strip():
            return None
        return v

    def to_command(self) -> CreateNodeCommand:
        """Convert this request into a `CreateNodeCommand`."""
        return CreateNodeCommand(
            name=self.name,
            type=self.type,
            description=self.description,
            attributes=self.attributes,
            favourite=self.favourite,
            tags=self.tags,
            extra_schema=self.extra_schema,
        )


class UpdateNodeRequest(RequestModel):
    """Request body for updating a node. Omitted fields are left unchanged.

    `type` sets or changes the item type, and `null` removes it (leave it out to
    keep it). The
    item keeps its attribute values either way; ones the new type has no field for
    simply have no field to show them.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "Alien (1979)",
                    "description": "Now with a corrected release year.",
                    "attributes": {"year": 1979},
                }
            ]
        }
    )

    name: str | None = Field(description="The item's name.", default=None)
    type: str | None = Field(
        description="The slug of its item type; null makes it untyped.", default=None
    )
    description: str | None = Field(
        description="Free text about the item.", default=None
    )
    attributes: dict[str, Any] | None = Field(
        description="Its field values, keyed by field key; replaces them all.",
        default=None,
    )
    favourite: bool | None = Field(
        description="Whether it is a favourite.", default=None
    )
    tags: list[str] | None = Field(
        description="Its tags; replaces them all.", default=None
    )
    extra_schema: dict[str, Any] | None = Field(
        description="Fields of its own, beyond its type's, as a JSON Schema.",
        default=None,
    )

    def to_command(self, node_id: uuid.UUID) -> UpdateNodeCommand:
        """Convert this request into an `UpdateNodeCommand` for `node_id`."""
        return UpdateNodeCommand(
            node_id=node_id,
            name=self.name,
            type=self.type,
            clear_type="type" in self.model_fields_set and self.type is None,
            description=self.description,
            attributes=self.attributes,
            favourite=self.favourite,
            tags=self.tags,
            extra_schema=self.extra_schema,
        )


class PromoteExtraSchemaFieldRequest(RequestModel):
    """Request body for promoting one overlay field onto the item type."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"node_type_id": "01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e20"}]
        }
    )

    node_type_id: uuid.UUID = Field(description="The item type to move the field to.")


class NodeResponse(BaseModel):
    """A node as returned by the API."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [_NODE_EXAMPLE, _NODE_MINIMAL_EXAMPLE]}
    )

    id: uuid.UUID = Field(description="The item's id.")
    name: str = Field(description="Its name.")
    type: str | None = Field(
        description="The slug of its item type; null if untyped.", default=None
    )
    description: str | None = Field(description="Free text about it.", default=None)
    attributes: dict[str, Any] = Field(
        description="Its field values, keyed by field key."
    )
    favourite: bool = Field(description="Whether it is a favourite.")
    tags: list[str] = Field(description="Its tags.")
    extra_schema: dict[str, Any] | None = Field(
        description="Fields of its own, beyond its type's, as a JSON Schema.",
        default=None,
    )
    created_at: datetime = Field(description="When it was created.")
    updated_at: datetime = Field(description="When it last changed.")
    cover_thumbnail_url: str | None = Field(
        description="Where to fetch its cover's thumbnail. Only lists and searches "
        + "fill it in, so a card can show its picture without a request of its own; "
        + "null if it has no cover or this response does not say.",
        default=None,
    )

    @classmethod
    def from_domain(
        cls, node: Node, *, cover_thumbnail_url: str | None = None
    ) -> NodeResponse:
        """Build a response from a domain `Node`."""
        return cls(
            cover_thumbnail_url=cover_thumbnail_url,
            id=node.id,
            name=node.name,
            type=node.type,
            description=node.description,
            attributes=node.attributes,
            favourite=node.favourite,
            tags=node.tags,
            extra_schema=node.extra_schema,
            created_at=node.created_at,
            updated_at=node.updated_at,
        )


class NodeContentsEntryResponse(BaseModel):
    """An item found inside another, and how many steps in it sits."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"item": _NODE_EXAMPLE, "depth": 1}]}
    )

    item: NodeResponse
    depth: int = Field(
        description="1 for an item held directly, 2 for one held by that, and so on.",
        examples=[1],
    )


class DeletedNodeResponse(BaseModel):
    """A deleted item as listed in Recently deleted."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e10",
                    "name": "Alien",
                    "type": "film",
                    "deleted_at": "2026-10-25T09:30:12.104233Z",
                },
                {
                    "id": "01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e11",
                    "name": "Untitled capture",
                    "type": None,
                    "deleted_at": "2026-10-24T18:02:47.551920Z",
                },
            ]
        }
    )

    id: uuid.UUID = Field(description="The item's id.")
    name: str = Field(description="Its name.")
    type: str | None = Field(
        description="The slug of its item type; null if untyped.", default=None
    )
    deleted_at: datetime = Field(description="When it was deleted.")

    @classmethod
    def from_domain(cls, node: Node) -> DeletedNodeResponse:
        """Build a response from a deleted domain `Node`."""
        # The repository only lists deleted rows, so the mark is always set.
        return cls(
            id=node.id,
            name=node.name,
            type=node.type,
            deleted_at=cast("datetime", node.deleted_at),
        )


class NodeSearchRequest(RequestModel):
    """Request body for searching items with a condition tree."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "query": {
                        "v": 1,
                        "where": {
                            "op": "and",
                            "children": [
                                {
                                    "kind": "field",
                                    "type": "film",
                                    "key": "rating",
                                    "op": ">=",
                                    "value": 4,
                                }
                            ],
                        },
                        "sort": [{"by": "name"}],
                    },
                    "limit": 50,
                }
            ]
        }
    )

    query: dict[str, Any] = Field(
        description="The condition tree: `v`, an optional `where` group and `sort`."
    )
    limit: int = Field(
        description="Most items to return on this page.",
        default=50,
        ge=1,
        le=200,
        strict=True,
    )
    cursor: str | None = Field(
        default=None, description="The `next_cursor` of the previous page."
    )


class QueryWarningResponse(BaseModel):
    """A part of the query that no longer applies."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "path": "where.children[0]",
                    "message": "The field 'rating' no longer exists on 'film'.",
                }
            ]
        }
    )

    path: str = Field(
        description="Where it is in the query, such as `where.children[0]`."
    )
    message: str = Field(description="Why it no longer applies.")


class NodeSearchResponse(BaseModel):
    """One page of search results."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "items": [_NODE_EXAMPLE],
                    "total": 1,
                    "total_capped": False,
                    "next_cursor": None,
                    "warnings": [],
                }
            ]
        }
    )

    items: list[NodeResponse] = Field(description="This page of matching items.")
    total: int = Field(description="How many items match.")
    total_capped: bool = Field(
        description="True when `total` is a lower bound, not the exact count."
    )
    next_cursor: str | None = Field(
        description="Pass as `cursor` for the next page; null on the last.",
        default=None,
    )
    warnings: list[QueryWarningResponse] = Field(
        description="Parts of the query that no longer apply."
    )

    @classmethod
    def from_result(cls, result: SearchNodesResult) -> NodeSearchResponse:
        """Build a response from a `SearchNodesResult`."""
        return cls(
            items=[
                NodeResponse.from_domain(
                    node, cover_thumbnail_url=result.covers.get(node.id)
                )
                for node in result.items
            ],
            total=result.total,
            total_capped=result.total_capped,
            next_cursor=result.next_cursor,
            warnings=[
                QueryWarningResponse(path=w.path, message=w.message)
                for w in result.warnings
            ],
        )


class NodeSearchCountsRequest(RequestModel):
    """Request body for counting the items several condition trees match."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "queries": {
                        "everything": {"v": 1, "where": None, "sort": []},
                        "no_photo": {
                            "v": 1,
                            "where": {
                                "op": "and",
                                "children": [{"kind": "media", "mode": "none"}],
                            },
                            "sort": [],
                        },
                    }
                }
            ]
        }
    )

    queries: dict[str, dict[str, Any]] = Field(
        description=(
            "Named condition trees (`v`, an optional `where` group and `sort`), "
            + "1 to 20 of them. A name is 1 to 64 letters, digits, dots, dashes "
            + "or underscores."
        )
    )


class NodeSearchCountResponse(BaseModel):
    """The number of items one query matches."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"total": 232, "total_capped": False, "warnings": []}]
        }
    )

    total: int = Field(description="How many items match.")
    total_capped: bool = Field(
        description="True when `total` is a lower bound, not the exact count."
    )
    warnings: list[QueryWarningResponse] = Field(
        description="Parts of the query that no longer apply."
    )


class NodeSearchCountsResponse(BaseModel):
    """The match count for each named query."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "counts": {
                        "everything": {
                            "total": 1284,
                            "total_capped": False,
                            "warnings": [],
                        },
                        "no_photo": {
                            "total": 232,
                            "total_capped": False,
                            "warnings": [],
                        },
                    }
                }
            ]
        }
    )

    counts: dict[str, NodeSearchCountResponse] = Field(
        description="Each query's count, under the name it was sent with."
    )

    @classmethod
    def from_result(cls, result: dict[str, SearchCount]) -> NodeSearchCountsResponse:
        """Build a response from the counts a `SearchNodeCounts` returned."""
        return cls(
            counts={
                name: NodeSearchCountResponse(
                    total=count.total,
                    total_capped=count.capped,
                    warnings=[
                        QueryWarningResponse(path=w.path, message=w.message)
                        for w in count.warnings
                    ],
                )
                for name, count in result.items()
            }
        )


class NodeCountResponse(BaseModel):
    """The exact number of items matching a filter."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"count": 1234}]})

    count: int = Field(description="Matching live items, with no cap.")


class NodeTypeCountResponse(BaseModel):
    """How many of your items have an item type."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"type": "film", "count": 12}]}
    )

    type: str | None = Field(
        description="The item type's slug, or null for items with no type."
    )
    count: int = Field(description="Your live items of that type.")

    @classmethod
    def from_domain(cls, row: TypeCount) -> NodeTypeCountResponse:
        """Build a response from a `TypeCount`."""
        return cls(type=row.type, count=row.count)


class ItemFieldResponse(BaseModel):
    """A field individual items carry in their own overlay."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"key": "signed", "kind": "boolean", "label": "Signed copy", "count": 3}
            ]
        }
    )

    key: str = Field(description="The field's key.")
    kind: str = Field(description="The field kind, such as `text` or `number`.")
    label: str = Field(description="The most common label, or the key if none.")
    count: int = Field(description="How many of your items declare the field.")

    @classmethod
    def from_domain(cls, use: ItemFieldUse) -> ItemFieldResponse:
        """Build a response from an `ItemFieldUse`."""
        return cls(key=use.key, kind=use.kind, label=use.label, count=use.count)
