import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from app.modules.graph.application.create_edge import CreateEdgeCommand
from app.modules.graph.application.update_edge import UpdateEdgeCommand

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


class CreateEdgeRequest(BaseModel):
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

    source_id: uuid.UUID
    target_id: uuid.UUID
    type: str
    attributes: dict[str, Any] = Field(default_factory=dict)

    def to_command(self) -> CreateEdgeCommand:
        """Convert this request into a `CreateEdgeCommand`."""
        return CreateEdgeCommand(
            source_id=self.source_id,
            target_id=self.target_id,
            type=self.type,
            attributes=self.attributes,
        )


class UpdateEdgeRequest(BaseModel):
    """Request body for updating an edge. Omitted fields are left unchanged."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"attributes": {"since": "1979"}}]}
    )

    attributes: dict[str, Any] | None = Field(default=None)

    def to_command(self, edge_id: uuid.UUID) -> UpdateEdgeCommand:
        """Convert this request into an `UpdateEdgeCommand` for `edge_id`."""
        return UpdateEdgeCommand(edge_id=edge_id, attributes=self.attributes)


class EdgeResponse(BaseModel):
    """An edge as returned by the API."""

    model_config = ConfigDict(json_schema_extra={"examples": [_EDGE_EXAMPLE]})

    id: uuid.UUID
    source_id: uuid.UUID
    target_id: uuid.UUID
    type: str
    attributes: dict[str, Any]
    created_at: datetime
    updated_at: datetime

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


class ListEdgesResponse(BaseModel):
    """A page of edge."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"items": [_EDGE_EXAMPLE]}]}
    )

    items: list[EdgeResponse]
