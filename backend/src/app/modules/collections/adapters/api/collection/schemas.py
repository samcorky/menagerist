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
from app.modules.collections.domain.collection import MAX_NAME_LENGTH
from app.platform.request_model import RequestModel

if TYPE_CHECKING:
    from app.modules.collections.application.get_collection import CollectionSummary

_COLLECTION_EXAMPLE: dict[str, Any] = {
    "id": "01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e20",
    "name": "Weekend watchlist",
    "slug": "weekend-watchlist",
    "description": "Things to watch soon.",
    "kind": "manual",
    "visibility": "private",
    "item_count": 3,
    "created_at": "2026-08-23T10:14:44.465954Z",
    "updated_at": "2026-08-23T10:14:44.465954Z",
}


class CreateCollectionRequest(RequestModel):
    """Request body for creating a collection."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"name": "Weekend watchlist", "description": "Things to watch soon."}
            ]
        }
    )

    name: str = Field(max_length=MAX_NAME_LENGTH)
    description: str | None = Field(default=None)
    slug: str | None = Field(
        default=None, description="Derived from the name when omitted."
    )

    def to_command(self) -> CreateCollectionCommand:
        """Convert this request into a `CreateCollectionCommand`."""
        return CreateCollectionCommand(
            name=self.name, description=self.description, slug=self.slug
        )


class UpdateCollectionRequest(RequestModel):
    """Request body for updating a collection.

    `slug` is immutable. Omitted fields are left unchanged; a blank
    description clears it.
    """

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"name": "Watchlist", "description": ""}]}
    )

    name: str | None = Field(default=None, max_length=MAX_NAME_LENGTH)
    description: str | None = Field(default=None)

    def to_command(self, collection_id: uuid.UUID) -> UpdateCollectionCommand:
        """Convert this request into an `UpdateCollectionCommand`."""
        return UpdateCollectionCommand(
            collection_id=collection_id,
            name=self.name,
            description=self.description,
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


class CollectionResponse(BaseModel):
    """A collection as returned by the API."""

    model_config = ConfigDict(json_schema_extra={"examples": [_COLLECTION_EXAMPLE]})

    id: uuid.UUID
    name: str
    slug: str
    description: str | None = Field(default=None)
    kind: str
    visibility: str
    item_count: int
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
            kind=str(collection.kind),
            visibility=str(collection.visibility),
            item_count=summary.item_count,
            created_at=collection.created_at,
            updated_at=collection.updated_at,
        )
