import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.graph.adapters.api.node_type.schemas import (
    NODE_TYPE_EXAMPLE,
    NodeTypeResponse,
)
from app.modules.graph.application.create_node import CreateNodeCommand
from app.modules.graph.application.delete_nodes import DeleteNodesCommand
from app.modules.graph.application.duplicate_node import DuplicateNodeCommand
from app.modules.graph.application.tag_nodes import TagNodesCommand
from app.modules.graph.application.update_node import UpdateNodeCommand
from app.modules.graph.domain.query import ItemFieldUse, TypeCount  # noqa: TC001
from app.platform.request_model import RequestModel

if TYPE_CHECKING:
    from app.modules.graph.application.aggregate_nodes import AggregateNodesResult
    from app.modules.graph.application.search_node_counts import SearchCount
    from app.modules.graph.application.search_nodes import SearchNodesResult
    from app.modules.graph.domain.aggregate import MeasureValue
    from app.modules.graph.domain.node import Node

# Written out, not an alias, so the schema lists the functions inline.
_Function = Literal["count", "sum", "avg", "min", "max", "distinct"]

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


class DeleteNodesRequest(RequestModel):
    """Request body for deleting several items at once (at most 200)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "ids": [
                        "01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e10",
                        "01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e11",
                    ]
                }
            ]
        }
    )

    ids: list[uuid.UUID] = Field(description="The items to delete.")

    def to_command(self) -> DeleteNodesCommand:
        """Convert this request into a `DeleteNodesCommand`."""
        return DeleteNodesCommand(node_ids=self.ids)


class TagNodesRequest(RequestModel):
    """Request body for adding and removing tags on several items at once."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "ids": ["01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e10"],
                    "add": ["to-watch"],
                    "remove": ["watched"],
                }
            ]
        }
    )

    ids: list[uuid.UUID] = Field(description="The items to change.")
    add: list[str] = Field(default_factory=list, description="Tags to add.")
    remove: list[str] = Field(default_factory=list, description="Tags to remove.")

    def to_command(self) -> TagNodesCommand:
        """Convert this request into a `TagNodesCommand`."""
        return TagNodesCommand(node_ids=self.ids, add=self.add, remove=self.remove)


class TagNodesResponse(BaseModel):
    """How many of the items the tag change altered."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"changed": 3}]})

    changed: int = Field(description="Items whose tags changed; the rest matched.")


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
        description="Where to fetch its cover's thumbnail. Only lists, searches and "
        + "the random pick fill it in, so a card can show its picture without a "
        + "request of its own; null if it has no cover or this response does not say.",
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


class NodeMeasureRequest(RequestModel):
    """One function over one field of the items a query matches."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"fn": "sum", "type": "film", "key": "price"},
                {"fn": "avg", "origin": "01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e20"},
                {"fn": "count"},
            ]
        }
    )

    fn: _Function = Field(
        description=(
            "`count`, `sum`, `avg`, `min`, `max` or `distinct`. `sum` and `avg` read "
            + "numbers, durations, ratings and money; `min` and `max` also dates; "
            + "`distinct` and `count` any of those and text, choice and yes/no "
            + "values. `count` with no field counts the items."
        )
    )
    type: str | None = Field(
        None, description="Slug of the item type whose field is read, with `key`."
    )
    key: str | None = Field(None, description="The field's key on that item type.")
    origin: str | None = Field(
        None,
        description=(
            "Id of a saved field, to read every item type field copied from it "
            + "instead of naming `type` and `key`."
        ),
    )


class NodeGroupByRequest(RequestModel):
    """How to split the matching items into groups."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"by": "type"},
                {"by": "tag", "order": "count", "limit": 10},
                {"by": "field", "type": "film", "key": "format"},
            ]
        }
    )

    by: Literal["field", "type", "tag"] = Field(
        description=(
            "`field` for a text, choice, multiple-choice or yes/no field (named with "
            + "`type` and `key`, or `origin`), `type` for the item type, `tag` for "
            + "the tags."
        )
    )
    type: str | None = Field(None, description="With `by` of field: the item type.")
    key: str | None = Field(None, description="With `by` of field: the field's key.")
    origin: str | None = Field(
        None, description="With `by` of field: the saved field, instead of `type`."
    )
    order: Literal["key", "count", "measure"] = Field(
        "key",
        description=(
            "Sort the groups by their key, their number of items, or the value of "
            + "the measure at index `measure`. Groups with nothing to sort by, and "
            + "the unset group when sorting by key, come last."
        ),
    )
    measure: int | None = Field(
        None,
        ge=0,
        description="With `order` of measure: the index of a measure, not money.",
    )
    descending: bool | None = Field(
        None,
        description="High to low. Defaults to true for `count` and `measure`.",
    )
    limit: int = Field(100, ge=1, le=100, description="Most groups to list, 1 to 100.")


class NodeAggregateRequest(RequestModel):
    """Request body for aggregating fields of the items a condition tree matches."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "query": {
                        "v": 1,
                        "where": {
                            "op": "and",
                            "children": [{"kind": "type", "in": ["film"]}],
                        },
                    },
                    "measures": [
                        {"fn": "sum", "type": "film", "key": "price"},
                        {"fn": "avg", "type": "film", "key": "rating"},
                        {"fn": "count"},
                    ],
                }
            ]
        }
    )

    query: dict[str, Any] = Field(
        default_factory=lambda: {"v": 1},
        description=(
            "The condition tree to aggregate over, as for `POST /nodes/search`: "
            + "`v` and an optional `where` group. Leave it out for every item."
        ),
    )
    measures: list[NodeMeasureRequest] = Field(
        min_length=1, max_length=10, description="1 to 10 measures, answered in order."
    )
    group_by: NodeGroupByRequest | None = Field(
        None,
        description=(
            "Also give every measure within each group. An item in several groups "
            + "(a tag, a multiple-choice value) counts in each, so the groups can "
            + "add up to more than `items`."
        ),
    )


class NodeCurrencyValueResponse(BaseModel):
    """An aggregate of the amounts in one currency."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"currency": "GBP", "value": 1204.5}]}
    )

    currency: str = Field(description="The currency code the amounts are in.")
    value: float = Field(description="The aggregate of the amounts in this currency.")


class NodeMeasureResponse(BaseModel):
    """What one measure came to."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "fn": "sum",
                    "type": "film",
                    "key": "price",
                    "origin": None,
                    "value": None,
                    "currencies": [
                        {"currency": "GBP", "value": 1204.5},
                        {"currency": "USD", "value": 80},
                    ],
                },
                {
                    "fn": "avg",
                    "type": "film",
                    "key": "rating",
                    "origin": None,
                    "value": 3.75,
                    "currencies": [],
                },
            ]
        }
    )

    fn: _Function = Field(description="The function, as asked.")
    type: str | None = Field(None, description="The item type, as asked.")
    key: str | None = Field(None, description="The field's key, as asked.")
    origin: str | None = Field(None, description="The saved field, as asked.")
    value: float | int | str | None = Field(
        None,
        description=(
            "The answer: a number, or a date as text for `min` and `max` of a date "
            + "field. Null when no item had a value to read, when the field no longer "
            + "exists (see `warnings`), and for money, which is in `currencies`."
        ),
    )
    currencies: list[NodeCurrencyValueResponse] = Field(
        description=(
            "For money, one value per currency, sorted by currency code. Money is "
            + "never converted, so the currencies are never added together. Empty "
            + "for anything else, and for money when no item had an amount."
        )
    )


class NodeMeasureValueResponse(BaseModel):
    """What one measure came to within a group, in the order the measures were asked."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"value": 3.75, "currencies": []},
                {"value": None, "currencies": [{"currency": "GBP", "value": 96.5}]},
            ]
        }
    )

    value: float | int | str | None = Field(
        None, description="As `value` of the measure. Null for money."
    )
    currencies: list[NodeCurrencyValueResponse] = Field(
        description="As `currencies` of the measure."
    )

    @classmethod
    def from_domain(cls, value: MeasureValue) -> NodeMeasureValueResponse:
        """Build one from a measure's value."""
        return cls(
            value=value.value,
            currencies=[
                NodeCurrencyValueResponse(currency=c.currency, value=c.value)
                for c in value.currencies
            ],
        )


class NodeAggregateGroupResponse(BaseModel):
    """One group of the matching items."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "key": "dvd",
                    "label": "dvd",
                    "count": 12,
                    "measures": [
                        {
                            "value": None,
                            "currencies": [{"currency": "GBP", "value": 96.5}],
                        }
                    ],
                }
            ]
        }
    )

    key: str | None = Field(
        None,
        description=(
            "The tag, field value or item type slug; null for the items with none "
            + "(`label` is `Unset`)."
        ),
    )
    label: str = Field(description="What to show for the group.")
    count: int = Field(description="How many items are in the group.")
    measures: list[NodeMeasureValueResponse] = Field(
        description="One entry per measure asked, in the same order."
    )


class NodeAggregateOtherResponse(BaseModel):
    """The items in the groups the `limit` left out."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "groups": 4,
                    "count": 9,
                    "measures": [
                        {
                            "value": None,
                            "currencies": [{"currency": "GBP", "value": 31}],
                        }
                    ],
                }
            ]
        }
    )

    groups: int = Field(description="How many groups were left out.")
    count: int = Field(description="Items in any of them, each counted once.")
    measures: list[NodeMeasureValueResponse] = Field(
        description="One entry per measure asked, over those items."
    )


class NodeAggregateResponse(BaseModel):
    """The aggregates of the items a query matches."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "items": 232,
                    "measures": [
                        {
                            "fn": "avg",
                            "type": "film",
                            "key": "rating",
                            "origin": None,
                            "value": 3.75,
                            "currencies": [],
                        }
                    ],
                    "warnings": [],
                }
            ]
        }
    )

    items: int = Field(description="How many items the query matches, exactly.")
    measures: list[NodeMeasureResponse] = Field(
        description="One entry per measure asked, in the same order."
    )
    warnings: list[QueryWarningResponse] = Field(
        description="Parts of the query, measures or grouping that no longer apply."
    )
    groups: list[NodeAggregateGroupResponse] | None = Field(
        None,
        description=(
            "With `group_by`, up to `limit` groups, each with its own count and "
            + "measures. Null without it."
        ),
    )
    other: NodeAggregateOtherResponse | None = Field(
        None,
        description="Present when the `limit` left groups out, covering their items.",
    )

    @classmethod
    def from_result(
        cls, asked: list[NodeMeasureRequest], result: AggregateNodesResult
    ) -> NodeAggregateResponse:
        """Build a response from what an `AggregateNodes` returned."""
        return cls(
            items=result.items,
            measures=[
                NodeMeasureResponse(
                    fn=measure.fn,
                    type=measure.type,
                    key=measure.key,
                    origin=measure.origin,
                    value=value.value,
                    currencies=[
                        NodeCurrencyValueResponse(currency=c.currency, value=c.value)
                        for c in value.currencies
                    ],
                )
                for measure, value in zip(asked, result.values, strict=True)
            ],
            warnings=[
                QueryWarningResponse(path=w.path, message=w.message)
                for w in result.warnings
            ],
            groups=None
            if result.groups is None
            else [
                NodeAggregateGroupResponse(
                    key=g.key,
                    label=g.label,
                    count=g.count,
                    measures=[
                        NodeMeasureValueResponse.from_domain(v) for v in g.values
                    ],
                )
                for g in result.groups
            ],
            other=None
            if result.other is None
            else NodeAggregateOtherResponse(
                groups=result.other.groups,
                count=result.other.count,
                measures=[
                    NodeMeasureValueResponse.from_domain(v) for v in result.other.values
                ],
            ),
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


class PromotedItemFieldResponse(BaseModel):
    """What promoting a per-item field onto its item type changed."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"items": 12, "node_type": NODE_TYPE_EXAMPLE}]}
    )

    items: int = Field(description="How many items the field moved off.")
    node_type: NodeTypeResponse = Field(description="The item type, with the field.")


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
