import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.graph.application.create_edge_type import CreateEdgeTypeCommand
from app.modules.graph.application.update_edge_type import UpdateEdgeTypeCommand
from app.platform.request_model import RequestModel

if TYPE_CHECKING:
    from app.modules.graph.domain.edge_type import EdgeType


HOLDER_DESCRIPTION = (
    "Which end holds the other, for an item's contents and path: `source` (the "
    + "source contains the target, as Contains), `target` (the target contains "
    + "the source, as Located in) or `none`. Needs a direction."
)


class CreateEdgeTypeRequest(RequestModel):
    """Request body for POST /edge-type."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "slug": "directed-by",
                    "label": "Directed by",
                    "reverse_label": "Directed",
                    "description": "Links a film to its director.",
                    "directional": True,
                    "holder": "none",
                }
            ]
        }
    )

    slug: str = Field(
        description="Its short name, unique among yours; connections refer to it."
    )
    label: str = Field(description="Its name, read from the source item.")
    reverse_label: str | None = Field(
        description="Its name read from the target item, such as `owned by`.",
        default=None,
    )
    description: str | None = Field(description="Free text about it.", default=None)
    directional: bool = Field(
        description="Whether the connection has a direction.", default=True
    )
    holder: Literal["source", "target", "none"] = Field(
        description=HOLDER_DESCRIPTION, default="none"
    )
    attributes_schema: dict[str, Any] | None = Field(
        description="Its fields, as a JSON Schema.", default=None
    )

    def to_command(self) -> CreateEdgeTypeCommand:
        """Convert to the application-layer command."""
        return CreateEdgeTypeCommand(
            slug=self.slug,
            label=self.label,
            reverse_label=self.reverse_label,
            description=self.description,
            directional=self.directional,
            holder=self.holder,
            attributes_schema=self.attributes_schema,
        )


class UpdateEdgeTypeRequest(RequestModel):
    """Request body for PATCH /edge-type/{id}."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"label": "Directed by", "directional": False}]}
    )

    label: str | None = Field(
        description="Its name, read from the source item.", default=None
    )
    reverse_label: str | None = Field(
        description="Its name read from the target item.", default=None
    )
    description: str | None = Field(description="Free text about it.", default=None)
    directional: bool | None = Field(
        description="Whether the connection has a direction.", default=None
    )
    holder: Literal["source", "target", "none"] | None = Field(
        description=HOLDER_DESCRIPTION, default=None
    )
    attributes_schema: dict[str, Any] | None = Field(
        description="Its fields, as a JSON Schema; replaces them all.", default=None
    )

    def to_command(self, edge_type_id: uuid.UUID) -> UpdateEdgeTypeCommand:
        """Convert to the application-layer command."""
        return UpdateEdgeTypeCommand(
            edge_type_id=edge_type_id,
            label=self.label,
            reverse_label=self.reverse_label,
            description=self.description,
            directional=self.directional,
            holder=self.holder,
            attributes_schema=self.attributes_schema,
        )


class EdgeTypeResponse(BaseModel):
    """Response shape for a single edge type."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e40",
                    "slug": "directed-by",
                    "label": "Directed by",
                    "reverse_label": "Directed",
                    "description": "Links a film to its director.",
                    "directional": True,
                    "holder": "none",
                    "attributes_schema": {"type": "object"},
                    "created_at": "2026-08-23T10:14:44.465954Z",
                    "updated_at": "2026-08-23T10:14:44.465954Z",
                }
            ]
        }
    )

    id: uuid.UUID = Field(description="The connection type's id.")
    slug: str = Field(description="Its short name; connections refer to it.")
    label: str = Field(description="Its name, read from the source item.")
    reverse_label: str | None = Field(
        description="Its name read from the target item; null if the same."
    )
    description: str | None = Field(description="Free text about it.")
    directional: bool = Field(description="Whether the connection has a direction.")
    holder: Literal["source", "target", "none"] = Field(description=HOLDER_DESCRIPTION)
    attributes_schema: dict[str, Any] | None = Field(
        description="Its fields, as a JSON Schema."
    )
    created_at: datetime = Field(description="When it was created.")
    updated_at: datetime = Field(description="When it last changed.")

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
            holder=edge_type.holder,
            attributes_schema=edge_type.attributes_schema,
            created_at=edge_type.created_at,
            updated_at=edge_type.updated_at,
        )
