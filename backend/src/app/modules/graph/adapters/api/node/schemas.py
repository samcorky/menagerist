import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.graph.application.create_node import CreateNodeCommand
from app.modules.graph.application.update_node import UpdateNodeCommand

if TYPE_CHECKING:
    from app.modules.graph.domain.node import Node

_NODE_EXAMPLE: dict[str, Any] = {
    "id": "01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e10",
    "name": "Alien",
    "type": "film",
    "description": "A 1979 science fiction horror film directed by Ridley Scott.",
    "attributes": {"year": 1979},
    "favourite": False,
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
    "created_at": "2026-08-23T10:14:44.465954Z",
    "updated_at": "2026-08-23T10:14:44.465954Z",
}


class CreateNodeRequest(BaseModel):
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
        )


class UpdateNodeRequest(BaseModel):
    """Request body for updating a node. Omitted fields are left unchanged.

    `type` may only be set once — if the node already has a type this field is ignored.
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

    @field_validator("type", mode="before")
    @classmethod
    def coerce_empty_type_to_none(cls, v: object) -> object:
        """Treat an empty or whitespace-only type string as absent."""
        if isinstance(v, str) and not v.strip():
            return None
        return v

    def to_command(self, node_id: uuid.UUID) -> UpdateNodeCommand:
        """Convert this request into an `UpdateNodeCommand` for `node_id`."""
        return UpdateNodeCommand(
            node_id=node_id,
            name=self.name,
            type=self.type,
            description=self.description,
            attributes=self.attributes,
            favourite=self.favourite,
        )


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
            created_at=node.created_at,
            updated_at=node.updated_at,
        )
