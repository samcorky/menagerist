import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from app.modules.collections.application.add_items_to_collection import (
    MAX_ITEMS_PER_REQUEST,
)
from app.modules.collections.application.create_collection import (
    CreateCollectionCommand,
)
from app.modules.collections.application.update_collection import (
    UpdateCollectionCommand,
)
from app.modules.collections.domain.collection import MAX_NAME_LENGTH, CollectionKind
from app.platform.request_model import RequestModel

if TYPE_CHECKING:
    from app.modules.collections.application.get_collection import CollectionSummary

_DEFINITION_EXAMPLE: dict[str, Any] = {
    "v": 1,
    "where": {
        "op": "and",
        "children": [
            {"kind": "type", "in": ["film"]},
            {"kind": "field", "type": "film", "key": "rating", "op": ">=", "value": 4},
        ],
    },
    "sort": [{"by": "name"}],
}
_DEFINITION_DESCRIPTION = (
    "A search query (as for `POST /node/search`) that makes this a smart "
    + "collection. Stored as sent once it validates."
)

_COLLECTION_EXAMPLE: dict[str, Any] = {
    "id": "01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e20",
    "name": "Weekend watchlist",
    "slug": "weekend-watchlist",
    "description": "Things to watch soon.",
    "kind": "manual",
    "visibility": "private",
    "definition": None,
    "item_count": 3,
    "item_count_capped": False,
    "warnings": [],
    "created_at": "2026-08-23T10:14:44.465954Z",
    "updated_at": "2026-08-23T10:14:44.465954Z",
}


class CreateCollectionRequest(RequestModel):
    """Request body for creating a collection."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"name": "Weekend watchlist", "description": "Things to watch soon."},
                {"name": "Well rated films", "definition": _DEFINITION_EXAMPLE},
            ]
        }
    )

    name: str = Field(max_length=MAX_NAME_LENGTH)
    description: str | None = Field(default=None)
    slug: str | None = Field(
        default=None, description="Derived from the name when omitted."
    )
    definition: dict[str, Any] | None = Field(
        default=None, description=_DEFINITION_DESCRIPTION
    )

    def to_command(self) -> CreateCollectionCommand:
        """Convert this request into a `CreateCollectionCommand`."""
        return CreateCollectionCommand(
            name=self.name,
            description=self.description,
            slug=self.slug,
            definition=self.definition,
        )


class UpdateCollectionRequest(RequestModel):
    """Request body for updating a collection.

    `slug` and the kind are immutable. Omitted fields are left unchanged; a
    blank description clears it. Only a smart collection takes a `definition`.
    """

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"name": "Watchlist", "description": ""}]}
    )

    name: str | None = Field(default=None, max_length=MAX_NAME_LENGTH)
    description: str | None = Field(default=None)
    definition: dict[str, Any] | None = Field(
        default=None, description="Replaces a smart collection's search query."
    )

    def to_command(self, collection_id: uuid.UUID) -> UpdateCollectionCommand:
        """Convert this request into an `UpdateCollectionCommand`."""
        return UpdateCollectionCommand(
            collection_id=collection_id,
            name=self.name,
            description=self.description,
            definition=self.definition,
        )


class AddItemsRequest(RequestModel):
    """Request body for putting items on a collection."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"item_ids": ["01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e30"]}]
        }
    )

    item_ids: list[uuid.UUID] = Field(max_length=MAX_ITEMS_PER_REQUEST)


class AddItemsResponse(BaseModel):
    """Outcome of adding items to a collection."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"added": 2}]})

    added: int = Field(description="How many items were not already on it.")


class DefinitionWarningResponse(BaseModel):
    """A part of a smart collection's definition that no longer applies."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "path": "where.children[1]",
                    "message": "The field 'rating' of 'film' no longer exists.",
                }
            ]
        }
    )

    path: str = Field(description="JSON path of the condition in the definition.")
    message: str


class CollectionResponse(BaseModel):
    """A collection as returned by the API."""

    model_config = ConfigDict(json_schema_extra={"examples": [_COLLECTION_EXAMPLE]})

    id: uuid.UUID
    name: str
    slug: str
    description: str | None = Field(default=None)
    kind: CollectionKind
    visibility: str
    definition: dict[str, Any] | None = Field(
        default=None, description="A smart collection's search query; null if manual."
    )
    item_count: int = Field(
        description="Live items on it; for a smart collection, capped at 1000."
    )
    item_count_capped: bool = Field(
        default=False, description="True when the real count is above `item_count`."
    )
    warnings: list[DefinitionWarningResponse] = Field(
        default_factory=list,
        description=(
            "Conditions that no longer apply; filled for a single smart collection, "
            + "empty in lists."
        ),
    )
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, summary: CollectionSummary) -> CollectionResponse:
        """Build a response from a collection summary."""
        collection = summary.collection
        return cls(
            id=collection.id,
            name=collection.name,
            slug=str(collection.slug),
            description=collection.description,
            kind=collection.kind,
            visibility=str(collection.visibility),
            definition=collection.definition,
            item_count=summary.item_count,
            item_count_capped=summary.item_count_capped,
            warnings=[
                DefinitionWarningResponse(path=w.path, message=w.message)
                for w in summary.warnings
            ],
            created_at=collection.created_at,
            updated_at=collection.updated_at,
        )
