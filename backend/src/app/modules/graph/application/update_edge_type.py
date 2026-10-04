import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import jsonschema
import structlog

from app.modules.graph.application.choice_lists import check_list_refs, strip_list_enums
from app.modules.graph.application.schema_meta import check_meta_shape
from app.modules.graph.domain.edge_type import EdgeType
from app.modules.graph.domain.errors import EdgeTypeNotFoundError, InvalidSchemaError

# Needed at runtime: the CQRS signature test evaluates __init__ annotations.
from app.modules.graph.ports.choice_list_source import ChoiceListSource  # noqa: TC001
from app.modules.graph.ports.unit_of_work import GraphUnitOfWork
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class UpdateEdgeTypeCommand:
    """Request to update an existing edge type."""

    edge_type_id: uuid.UUID
    label: str | None = field(default=None)
    reverse_label: str | None = field(default=None)
    description: str | None = field(default=None)
    directional: bool | None = field(default=None)
    attributes_schema: dict[str, Any] | None = field(default=None)


class UpdateEdgeType(CommandHandler[GraphUnitOfWork, UpdateEdgeTypeCommand, EdgeType]):
    """Apply partial updates to an existing edge type."""

    def __init__(
        self, uow: GraphUnitOfWork, choice_lists: ChoiceListSource | None = None
    ) -> None:
        super().__init__(uow)
        self._choice_lists = choice_lists

    async def handle(self, command: UpdateEdgeTypeCommand, actor: Actor) -> EdgeType:
        """Apply the update and commit."""
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
            edge_type = await repos.edge_types.get(command.edge_type_id)
            if edge_type is None:
                raise EdgeTypeNotFoundError(
                    f"Edge type {command.edge_type_id} not found"
                )
            edge_type.update(
                label=command.label,
                reverse_label=command.reverse_label,
                description=command.description,
                directional=command.directional,
                attributes_schema=attributes_schema,
            )
            await repos.edge_types.save(edge_type)
            await self._uow.commit()
        logger.info("edge type updated", edge_type_id=command.edge_type_id)
        return edge_type
