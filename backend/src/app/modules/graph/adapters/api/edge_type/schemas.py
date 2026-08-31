import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from app.modules.graph.application.create_edge_type import CreateEdgeTypeCommand
from app.modules.graph.application.update_edge_type import UpdateEdgeTypeCommand

if TYPE_CHECKING:
    from app.modules.graph.domain.edge_type import EdgeType


class CreateEdgeTypeRequest(BaseModel):
    """Request body for POST /edge-type."""

    slug: str
    label: str
    reverse_label: str | None = Field(default=None)
    description: str | None = Field(default=None)
    directional: bool = Field(default=True)
    attributes_schema: dict[str, Any] | None = Field(default=None)

    def to_command(self) -> CreateEdgeTypeCommand:
        """Convert to the application-layer command."""
        return CreateEdgeTypeCommand(
            slug=self.slug,
            label=self.label,
            reverse_label=self.reverse_label,
            description=self.description,
            directional=self.directional,
            attributes_schema=self.attributes_schema,
        )


class UpdateEdgeTypeRequest(BaseModel):
    """Request body for PATCH /edge-type/{id}."""

    label: str | None = Field(default=None)
    reverse_label: str | None = Field(default=None)
    description: str | None = Field(default=None)
    directional: bool | None = Field(default=None)
    attributes_schema: dict[str, Any] | None = Field(default=None)

    def to_command(self, edge_type_id: uuid.UUID) -> UpdateEdgeTypeCommand:
        """Convert to the application-layer command."""
        return UpdateEdgeTypeCommand(
            edge_type_id=edge_type_id,
            label=self.label,
            reverse_label=self.reverse_label,
            description=self.description,
            directional=self.directional,
            attributes_schema=self.attributes_schema,
        )


class EdgeTypeResponse(BaseModel):
    """Response shape for a single edge type."""

    id: uuid.UUID
    slug: str
    label: str
    reverse_label: str | None
    description: str | None
    directional: bool
    attributes_schema: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, edge_type: EdgeType) -> EdgeTypeResponse:
        """Build from a domain EdgeType."""
        return cls(
            id=edge_type.id,
            slug=str(edge_type.slug),
            label=edge_type.label,
            reverse_label=edge_type.reverse_label,
            description=edge_type.description,
            directional=edge_type.directional,
            attributes_schema=edge_type.attributes_schema,
            created_at=edge_type.created_at,
            updated_at=edge_type.updated_at,
        )
