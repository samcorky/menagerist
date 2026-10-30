import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.graph.application.create_node import CreateNodeCommand
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

    name: str
    type: str | None = Field(default=None)
    description: str | None = Field(default=None)
    attributes: dict[str, Any] = Field(default_factory=dict)
    favourite: bool = Field(default=False)
    tags: list[str] = Field(default_factory=list)
    extra_schema: dict[str, Any] | None = Field(default=None)

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

    name: str | None = Field(default=None)
    type: str | None = Field(default=None)
    description: str | None = Field(default=None)
    attributes: dict[str, Any] | None = Field(default=None)
    favourite: bool | None = Field(default=None)
    tags: list[str] | None = Field(default=None)
    extra_schema: dict[str, Any] | None = Field(default=None)

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

    node_type_id: uuid.UUID


class NodeResponse(BaseModel):
    """A node as returned by the API."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [_NODE_EXAMPLE, _NODE_MINIMAL_EXAMPLE]}
    )

    id: uuid.UUID
    name: str
    type: str | None = Field(default=None)
    description: str | None = Field(default=None)
    attributes: dict[str, Any]
    favourite: bool
    tags: list[str]
    extra_schema: dict[str, Any] | None = Field(default=None)
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, node: Node) -> NodeResponse:
        """Build a response from a domain `Node`."""
        return cls(
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

    id: uuid.UUID
    name: str
    type: str | None = Field(default=None)
    deleted_at: datetime

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
    limit: int = Field(default=50, ge=1, le=200, strict=True)
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

    path: str
    message: str


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

    items: list[NodeResponse]
    total: int
    total_capped: bool = Field(
        description="True when `total` is a lower bound, not the exact count."
    )
    next_cursor: str | None = Field(default=None)
    warnings: list[QueryWarningResponse]

    @classmethod
    def from_result(cls, result: SearchNodesResult) -> NodeSearchResponse:
        """Build a response from a `SearchNodesResult`."""
        return cls(
            items=[NodeResponse.from_domain(node) for node in result.items],
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

    total: int
    total_capped: bool = Field(
        description="True when `total` is a lower bound, not the exact count."
    )
    warnings: list[QueryWarningResponse]


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

    counts: dict[str, NodeSearchCountResponse]

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

    key: str
    kind: str = Field(description="The field kind, such as `text` or `number`.")
    label: str = Field(description="The most common label, or the key if none.")
    count: int = Field(description="How many of your items declare the field.")

    @classmethod
    def from_domain(cls, use: ItemFieldUse) -> ItemFieldResponse:
        """Build a response from an `ItemFieldUse`."""
        return cls(key=use.key, kind=use.kind, label=use.label, count=use.count)
