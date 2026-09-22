import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import structlog

from app.modules.graph.application.schema_meta import archived_keys
from app.modules.graph.application.update_node import UpdateNode, UpdateNodeCommand
from app.modules.graph.application.update_node_type import (
    UpdateNodeType,
    UpdateNodeTypeCommand,
)
from app.modules.graph.domain.errors import (
    InvalidSchemaError,
    NodeNotFoundError,
    NodeTypeNotFoundError,
)
from app.modules.graph.ports.unit_of_work import GraphUnitOfWork
from app.shared_kernel.cqrs import CommandHandler
from app.shared_kernel.unit_of_work import JoinedUnitOfWork

if TYPE_CHECKING:
    from app.modules.graph.domain.node import Node
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()

_BASE_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {},
}


@dataclass(kw_only=True)
class PromoteExtraSchemaFieldCommand:
    """Move one field's definition from a node's overlay onto its item type."""

    node_id: uuid.UUID
    node_type_id: uuid.UUID
    key: str


class PromoteExtraSchemaField(
    CommandHandler[GraphUnitOfWork, PromoteExtraSchemaFieldCommand, "Node"]
):
    """Move an overlay field definition onto the item type; its value is untouched.

    Composes `UpdateNodeType` (add the property) and `UpdateNode` (remove it from
    the overlay) through `JoinedUnitOfWork`, one commit: leaving the key defined
    on both the type and the overlay is invalid (`merge_attribute_schemas`
    rejects the collision on the node's next load), so this cannot be two
    separate requests.
    """

    async def handle(
        self, command: PromoteExtraSchemaFieldCommand, actor: Actor
    ) -> Node:
        """Move `command.key` from the node's overlay to the item type's schema."""
        async with self._uow as repos:
            joined = JoinedUnitOfWork(repos, owner=self._uow)

            node = await repos.nodes.get(command.node_id)
            if node is None:
                raise NodeNotFoundError(f"Node {command.node_id} not found")
            extra_properties: dict[str, Any] = (node.extra_schema or {}).get(
                "properties"
            ) or {}
            if command.key not in extra_properties:
                raise InvalidSchemaError(
                    f"{command.key!r} is not defined on this item's extra fields"
                )

            node_type = await repos.node_types.get(command.node_type_id)
            if node_type is None:
                raise NodeTypeNotFoundError(
                    f"NodeType {command.node_type_id} not found"
                )
            type_schema: dict[str, Any] = node_type.attributes_schema or dict(
                _BASE_SCHEMA
            )
            type_properties: dict[str, Any] = dict(type_schema.get("properties") or {})
            if command.key in type_properties or command.key in archived_keys(
                type_schema
            ):
                raise InvalidSchemaError(
                    f"{command.key!r} already exists on this item type"
                )

            new_type_schema = {
                **type_schema,
                "properties": {
                    **type_properties,
                    command.key: extra_properties[command.key],
                },
            }
            await UpdateNodeType(joined).handle(
                UpdateNodeTypeCommand(
                    node_type_id=command.node_type_id,
                    attributes_schema=new_type_schema,
                ),
                actor,
            )

            remaining = {k: v for k, v in extra_properties.items() if k != command.key}
            new_extra_schema = {**(node.extra_schema or {}), "properties": remaining}
            updated_node = await UpdateNode(joined).handle(
                UpdateNodeCommand(
                    node_id=command.node_id, extra_schema=new_extra_schema
                ),
                actor,
            )

            await self._uow.commit()
        logger.info(
            "extra schema field promoted",
            node_id=command.node_id,
            node_type_id=command.node_type_id,
            key=command.key,
        )
        return updated_node
