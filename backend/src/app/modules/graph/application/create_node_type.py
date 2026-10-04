from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import jsonschema
import structlog

from app.modules.graph.application.choice_lists import check_list_refs, strip_list_enums
from app.modules.graph.application.schema_meta import check_meta_shape
from app.modules.graph.domain.errors import (
    InvalidSchemaError,
    NodeTypeSlugConflictError,
)
from app.modules.graph.domain.node_type import NodeType

# Needed at runtime: the CQRS signature test evaluates __init__ annotations.
from app.modules.graph.ports.choice_list_source import ChoiceListSource  # noqa: TC001
from app.modules.graph.ports.unit_of_work import GraphUnitOfWork
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class CreateNodeTypeCommand:
    """Request to create a new node type."""

    slug: str
    label: str
    description: str | None = field(default=None)
    attributes_schema: dict[str, Any] | None = field(default=None)


class CreateNodeType(CommandHandler[GraphUnitOfWork, CreateNodeTypeCommand, NodeType]):
    """Create and persist a new node type."""

    def __init__(
        self, uow: GraphUnitOfWork, choice_lists: ChoiceListSource | None = None
    ) -> None:
        super().__init__(uow)
        self._choice_lists = choice_lists

    async def handle(self, command: CreateNodeTypeCommand, actor: Actor) -> NodeType:
        """Create a node type from `command` and commit it."""
        if command.attributes_schema is not None:
            try:
                jsonschema.validators.validator_for(
                    command.attributes_schema
                ).check_schema(command.attributes_schema)
            except jsonschema.SchemaError as exc:
                raise InvalidSchemaError(str(exc.message)) from exc
            check_meta_shape(command.attributes_schema)
            attributes_schema = strip_list_enums(command.attributes_schema)
            await check_list_refs(attributes_schema, self._choice_lists)
        else:
            attributes_schema = None
        async with self._uow as repos:
            if await repos.node_types.get_by_slug(command.slug) is not None:
                raise NodeTypeSlugConflictError(
                    f"NodeType with slug '{command.slug}' already exists"
                )
            node_type = NodeType.create(
                slug=command.slug,
                label=command.label,
                description=command.description,
                attributes_schema=attributes_schema,
            )
            await repos.node_types.add(node_type)
            await self._uow.commit()
        logger.info("node type created", node_type_id=node_type.id, slug=command.slug)
        return node_type
