import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog

from app.modules.graph.application._validate_attributes import validate_attributes
from app.modules.graph.application.extra_schema_limits import check_extra_schema_limits
from app.modules.graph.application.schema_meta import (
    check_schema_definition,
    merge_attribute_schemas,
)
from app.modules.graph.domain.errors import NodeNotFoundError
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.node_type import NodeType
from app.modules.graph.ports.unit_of_work import GraphRepos, GraphUnitOfWork
from app.shared_kernel.cqrs import CommandHandler
from app.shared_kernel.slug import slugify

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class UpdateNodeCommand:
    """Request to update a node's editable fields.

    A field left as `None` is unchanged. `type` is one-time-settable — it can
    be assigned when currently `None` but cannot be changed once set.
    """

    node_id: uuid.UUID
    name: str | None = field(default=None)
    type: str | None = field(default=None)
    description: str | None = field(default=None)
    attributes: dict[str, Any] | None = field(default=None)
    favourite: bool | None = field(default=None)
    tags: list[str] | None = field(default=None)
    extra_schema: dict[str, Any] | None = field(default=None)


class UpdateNode(CommandHandler[GraphUnitOfWork, UpdateNodeCommand, Node]):
    """Update an existing node's editable fields."""

    async def handle(self, command: UpdateNodeCommand, actor: Actor) -> Node:
        """Apply `command`'s changes to the node and commit."""
        if command.extra_schema is not None:
            check_schema_definition(command.extra_schema)
        async with self._uow as repos:
            node = await repos.nodes.get(command.node_id)
            if node is None:
                raise NodeNotFoundError(f"Node {command.node_id} not found")

            if command.extra_schema is not None:
                check_extra_schema_limits(
                    command.extra_schema, previous=node.extra_schema
                )

            if command.attributes is not None:
                await self._validate(repos, node, command.attributes, command)

            node.update(
                name=command.name,
                type=command.type,
                description=command.description,
                attributes=command.attributes,
                favourite=command.favourite,
                tags=command.tags,
                extra_schema=command.extra_schema,
            )

            if command.type is not None:
                slug = slugify(command.type)
                if await repos.node_types.get_by_slug(slug) is None:
                    await repos.node_types.add(
                        NodeType.create(slug=slug, label=command.type)
                    )

            await repos.nodes.save(node)
            await self._uow.commit()
        logger.info("node updated", node_id=command.node_id)
        return node

    async def _validate(
        self,
        repos: GraphRepos,
        node: Node,
        attributes: dict[str, Any],
        command: UpdateNodeCommand,
    ) -> None:
        """Validate `attributes` against the type's schema plus overlay."""
        type_schema: dict[str, Any] | None = None
        if node.type is not None:
            node_type = await repos.node_types.get_by_slug(slugify(node.type))
            type_schema = node_type.attributes_schema if node_type else None
        extra_schema = (
            command.extra_schema
            if command.extra_schema is not None
            else node.extra_schema
        )
        schema = merge_attribute_schemas(type_schema, extra_schema)
        if schema is not None:
            validate_attributes(schema, attributes, previous=node.attributes)
