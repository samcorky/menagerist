import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from app.modules.graph.application.create_edge import CreateEdgeCommand
from app.modules.graph.application.create_edges import CreateEdgesCommand
from app.modules.graph.application.update_edge import UpdateEdgeCommand
from app.platform.request_model import RequestModel

if TYPE_CHECKING:
    from app.modules.graph.domain.edge import Edge

_EDGE_EXAMPLE: dict[str, Any] = {
    "id": "01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e11",
    "source_id": "01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e10",
    "target_id": "01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e12",
    "type": "directed-by",
    "attributes": {},
    "created_at": "2026-08-23T10:14:44.465954Z",
    "updated_at": "2026-08-23T10:14:44.465954Z",
}


class CreateEdgeRequest(RequestModel):
    """Request body for creating an edge between two node."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "source_id": "01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e10",
                    "target_id": "01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e12",
                    "type": "directed-by",
                    "attributes": {},
                }
            ]
        }
    )

    source_id: uuid.UUID = Field(description="The item the connection starts from.")
    target_id: uuid.UUID = Field(description="The item it goes to.")
    type: str = Field(description="The slug of its connection type.")
    attributes: dict[str, Any] = Field(
        description="Its field values, keyed by field key.", default_factory=dict
    )

    def to_command(self) -> CreateEdgeCommand:
        """Convert this request into a `CreateEdgeCommand`."""
        return CreateEdgeCommand(
            source_id=self.source_id,
            target_id=self.target_id,
            type=self.type,
            attributes=self.attributes,
        )


_REVERSE_DESCRIPTION = (
    "Run each connection from its target to `source_id`, not from it."
)


class CreateEdgesRequest(RequestModel):
    """Request body for connecting one source to several targets at once.

    Attributes apply to every edge. A target already connected to the source
    by an edge of the same type is skipped, not duplicated.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "source_id": "01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e10",
                    "target_ids": [
                        "01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e12",
                        "01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e13",
                    ],
                    "type": "pictured-with",
                    "attributes": {},
                }
            ]
        }
    )

    source_id: uuid.UUID = Field(description="The item the connections start from.")
    target_ids: list[uuid.UUID] = Field(description="The items they go to.")
    type: str = Field(description="The slug of their connection type.")
    attributes: dict[str, Any] = Field(
        description="Field values given to every new connection.", default_factory=dict
    )
    reverse: bool = Field(
        default=False,
        description=_REVERSE_DESCRIPTION,
    )

    def to_command(self) -> CreateEdgesCommand:
        """Convert this request into a `CreateEdgesCommand`."""
        return CreateEdgesCommand(
            source_id=self.source_id,
            target_ids=self.target_ids,
            type=self.type,
            attributes=self.attributes,
            reverse=self.reverse,
        )


class UpdateEdgeRequest(RequestModel):
    """Request body for updating an edge. Omitted fields are left unchanged."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"attributes": {"since": "1979"}}]}
    )

    attributes: dict[str, Any] | None = Field(
        description="Its field values, keyed by field key; replaces them all.",
        default=None,
    )

    def to_command(self, edge_id: uuid.UUID) -> UpdateEdgeCommand:
        """Convert this request into an `UpdateEdgeCommand` for `edge_id`."""
        return UpdateEdgeCommand(edge_id=edge_id, attributes=self.attributes)


class EdgeResponse(BaseModel):
    """An edge as returned by the API."""

    model_config = ConfigDict(json_schema_extra={"examples": [_EDGE_EXAMPLE]})

    id: uuid.UUID = Field(description="The connection's id.")
    source_id: uuid.UUID = Field(description="The item it starts from.")
    target_id: uuid.UUID = Field(description="The item it goes to.")
    type: str = Field(description="The slug of its connection type.")
    attributes: dict[str, Any] = Field(
        description="Its field values, keyed by field key."
    )
    created_at: datetime = Field(description="When it was created.")
    updated_at: datetime = Field(description="When it last changed.")

    @classmethod
    def from_domain(cls, edge: Edge) -> EdgeResponse:
        """Build a response from a domain `Edge`."""
        return cls(
            id=edge.id,
            source_id=edge.source_id,
            target_id=edge.target_id,
            type=edge.type,
            attributes=edge.attributes,
            created_at=edge.created_at,
            updated_at=edge.updated_at,
        )


class CreateEdgesResponse(BaseModel):
    """Edges created, and targets skipped because a matching edge already existed."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "created": [_EDGE_EXAMPLE],
                    "skipped": ["01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e13"],
                }
            ]
        }
    )

    created: list[EdgeResponse] = Field(description="The connections made.")
    skipped: list[uuid.UUID] = Field(
        description="Targets left alone because they were already connected."
    )
