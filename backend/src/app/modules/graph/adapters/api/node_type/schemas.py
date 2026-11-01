import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from app.modules.graph.application.create_node_type import CreateNodeTypeCommand
from app.modules.graph.application.update_node_type import UpdateNodeTypeCommand
from app.modules.graph.domain.node_type import TYPE_COLOURS
from app.platform.request_model import RequestModel

if TYPE_CHECKING:
    from app.modules.graph.domain.node_type import NodeType

_NODE_TYPE_EXAMPLE: dict[str, Any] = {
    "id": "01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e20",
    "slug": "film",
    "label": "Film",
    "description": "A motion picture.",
    "attributes_schema": None,
    "icon": "clapperboard",
    "colour": "red",
    "created_at": "2026-08-23T10:14:44.465954Z",
    "updated_at": "2026-08-23T10:14:44.465954Z",
}


_ICON_DESCRIPTION = (
    "A Lucide icon name in lower-case words joined by dashes, such as `film`."
)
_COLOUR_DESCRIPTION = (
    f"One of: {', '.join(TYPE_COLOURS)}. A colour name, not a free colour, so "
    + "every client can draw it with the right contrast."
)


class CreateNodeTypeRequest(RequestModel):
    """Request body for creating a node type."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "slug": "film",
                    "label": "Film",
                    "description": "A motion picture.",
                    "icon": "clapperboard",
                    "colour": "red",
                }
            ]
        }
    )

    slug: str
    label: str
    description: str | None = Field(default=None)
    attributes_schema: dict[str, Any] | None = Field(default=None)
    icon: str | None = Field(default=None, description=_ICON_DESCRIPTION)
    colour: str | None = Field(default=None, description=_COLOUR_DESCRIPTION)

    def to_command(self) -> CreateNodeTypeCommand:
        """Convert this request into a `CreateNodeTypeCommand`."""
        return CreateNodeTypeCommand(
            slug=self.slug,
            label=self.label,
            description=self.description,
            attributes_schema=self.attributes_schema,
            icon=self.icon,
            colour=self.colour,
        )


class UpdateNodeTypeRequest(RequestModel):
    """Request body for updating a node type.

    `slug` is immutable. Omitted fields are left unchanged. Send `null` for
    `icon` or `colour` to remove it.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "label": "Motion Picture",
                    "description": "A film or movie.",
                }
            ]
        }
    )

    label: str | None = Field(default=None)
    description: str | None = Field(default=None)
    attributes_schema: dict[str, Any] | None = Field(default=None)
    icon: str | None = Field(default=None, description=_ICON_DESCRIPTION)
    colour: str | None = Field(default=None, description=_COLOUR_DESCRIPTION)

    def to_command(self, node_type_id: uuid.UUID) -> UpdateNodeTypeCommand:
        """Convert this request into an `UpdateNodeTypeCommand` for `node_type_id`."""
        return UpdateNodeTypeCommand(
            node_type_id=node_type_id,
            label=self.label,
            description=self.description,
            attributes_schema=self.attributes_schema,
            icon=self.icon,
            colour=self.colour,
            clear_icon="icon" in self.model_fields_set and self.icon is None,
            clear_colour="colour" in self.model_fields_set and self.colour is None,
        )


class NodeTypeResponse(BaseModel):
    """A node type as returned by the API."""

    model_config = ConfigDict(json_schema_extra={"examples": [_NODE_TYPE_EXAMPLE]})

    id: uuid.UUID
    slug: str
    label: str
    description: str | None = Field(default=None)
    attributes_schema: dict[str, Any] | None = Field(default=None)
    icon: str | None = Field(default=None, description=_ICON_DESCRIPTION)
    colour: str | None = Field(default=None, description=_COLOUR_DESCRIPTION)
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, node_type: NodeType) -> NodeTypeResponse:
        """Build a response from a domain `NodeType`."""
        return cls(
            id=node_type.id,
            slug=str(node_type.slug),
            label=node_type.label,
            description=node_type.description,
            attributes_schema=node_type.attributes_schema,
            icon=node_type.icon,
            colour=node_type.colour,
            created_at=node_type.created_at,
            updated_at=node_type.updated_at,
        )


class AttributeValueCountResponse(BaseModel):
    """A previously-used attribute value and how many nodes hold it."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"value": "Draft", "count": 12}]}
    )

    value: str
    count: int
