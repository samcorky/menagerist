import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from app.modules.graph.application.create_node import CreateNodeCommand

if TYPE_CHECKING:
    from app.modules.graph.domain.node import Node

_NODE_EXAMPLE: dict[str, Any] = {
    "id": "01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e10",
    "name": "Alien",
    "type": "film",
    "description": "A 1979 science fiction horror film directed by Ridley Scott.",
    "attributes": {"year": 1979},
    "created_at": "2026-08-23T10:14:44.465954Z",
    "updated_at": "2026-08-23T10:14:44.465954Z",
}


class CreateNodeRequest(BaseModel):
    """Request body for creating a node."""

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
                }
            ]
        }
    )

    name: str
    type: str
    description: str | None = Field(default=None)
    attributes: dict[str, Any] = Field(default_factory=dict)

    def to_command(self) -> CreateNodeCommand:
        """Convert this request into a `CreateNodeCommand`."""
        return CreateNodeCommand(
            name=self.name,
            type=self.type,
            description=self.description,
            attributes=self.attributes,
        )


class NodeResponse(BaseModel):
    """A node as returned by the API."""

    model_config = ConfigDict(json_schema_extra={"examples": [_NODE_EXAMPLE]})

    id: uuid.UUID
    name: str
    type: str
    description: str | None = Field(default=None)
    attributes: dict[str, Any]
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
            created_at=node.created_at,
            updated_at=node.updated_at,
        )


class ListNodesResponse(BaseModel):
    """A page of nodes."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"items": [_NODE_EXAMPLE]}]}
    )

    items: list[NodeResponse]
