from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import jsonschema
import structlog

from app.modules.graph.domain.errors import InvalidAttributesError
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.node_type import NodeType
from app.modules.graph.ports.unit_of_work import GraphUnitOfWork
from app.shared_kernel.cqrs import CommandHandler
from app.shared_kernel.slug import slugify

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class CreateNodeCommand:
    """Request to create a new node."""

    name: str
    type: str | None = field(default=None)
    description: str | None = field(default=None)
    attributes: dict[str, Any] = field(default_factory=dict)
    favourite: bool = field(default=False)
    tags: list[str] = field(default_factory=list)


class CreateNode(CommandHandler[GraphUnitOfWork, CreateNodeCommand, Node]):
    """Create and persist a new node, auto-creating its NodeType if not yet known."""

    async def handle(self, command: CreateNodeCommand, actor: Actor) -> Node:
        """Create a node from `command` and commit it.

        If no NodeType exists for the given type slug, one is created automatically
        so the vocabulary builds itself as nodes are added.
        """
        node = Node.create(
            name=command.name,
            type=command.type,
            description=command.description,
            attributes=command.attributes,
            favourite=command.favourite,
            tags=command.tags,
        )
        async with self._uow as repos:
            if command.type is not None:
                slug = slugify(command.type)
                node_type = await repos.node_types.get_by_slug(slug)
                if node_type is None:
                    await repos.node_types.add(
                        NodeType.create(slug=slug, label=command.type)
                    )
                elif node_type.attributes_schema is not None:
                    _schema = node_type.attributes_schema
                    _cls = jsonschema.validators.validator_for(_schema)
                    try:
                        _cls(_schema, format_checker=_cls.FORMAT_CHECKER).validate(
                            command.attributes
                        )
                    except jsonschema.ValidationError as exc:
                        raise InvalidAttributesError(exc.message) from exc
            await repos.nodes.add(node)
            await self._uow.commit()
        logger.info("node created", node_id=node.id, node_type=node.type)
        return node
