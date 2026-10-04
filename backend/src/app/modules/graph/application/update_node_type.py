import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import jsonschema
import structlog

from app.modules.graph.application.choice_lists import check_list_refs, strip_list_enums
from app.modules.graph.application.schema_meta import check_meta_shape
from app.modules.graph.domain.errors import InvalidSchemaError, NodeTypeNotFoundError
from app.modules.graph.domain.node_type import NodeType

# Needed at runtime: the CQRS signature test evaluates __init__ annotations.
from app.modules.graph.ports.choice_list_source import ChoiceListSource  # noqa: TC001
from app.modules.graph.ports.unit_of_work import GraphUnitOfWork
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class UpdateNodeTypeCommand:
    """Request to update a node type's editable fields. `slug` is immutable."""

    node_type_id: uuid.UUID
    label: str | None = field(default=None)
    description: str | None = field(default=None)
    attributes_schema: dict[str, Any] | None = field(default=None)


class UpdateNodeType(CommandHandler[GraphUnitOfWork, UpdateNodeTypeCommand, NodeType]):
    """Update an existing node type's editable fields."""

    def __init__(
        self, uow: GraphUnitOfWork, choice_lists: ChoiceListSource | None = None
    ) -> None:
        super().__init__(uow)
        self._choice_lists = choice_lists

    async def handle(self, command: UpdateNodeTypeCommand, actor: Actor) -> NodeType:
        """Apply `command`'s changes to the node type and commit."""
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
            node_type = await repos.node_types.get(command.node_type_id)
            if node_type is None:
                raise NodeTypeNotFoundError(
                    f"NodeType {command.node_type_id} not found"
                )

            node_type.update(
                label=command.label,
                description=command.description,
                attributes_schema=attributes_schema,
            )

            await repos.node_types.save(node_type)
            await self._uow.commit()
        logger.info("node type updated", node_type_id=command.node_type_id)
        return node_type
