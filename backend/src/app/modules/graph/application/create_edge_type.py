from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import jsonschema
import structlog

from app.modules.graph.application.schema_meta import check_meta_shape
from app.modules.graph.domain.edge_type import EdgeType
from app.modules.graph.domain.errors import (
    EdgeTypeSlugConflictError,
    InvalidSchemaError,
)
from app.modules.graph.ports.unit_of_work import GraphUnitOfWork
from app.shared_kernel.cqrs import CommandHandler
from app.shared_kernel.slug import slugify

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class CreateEdgeTypeCommand:
    """Request to create a new edge type."""

    slug: str
    label: str
    reverse_label: str | None = field(default=None)
    description: str | None = field(default=None)
    directional: bool = field(default=True)
    attributes_schema: dict[str, Any] | None = field(default=None)


class CreateEdgeType(CommandHandler[GraphUnitOfWork, CreateEdgeTypeCommand, EdgeType]):
    """Create and persist a new edge type."""

    async def handle(self, command: CreateEdgeTypeCommand, actor: Actor) -> EdgeType:
        """Create an edge type from `command` and commit it."""
        if command.attributes_schema is not None:
            try:
                jsonschema.validators.validator_for(
                    command.attributes_schema
                ).check_schema(command.attributes_schema)
            except jsonschema.SchemaError as exc:
                raise InvalidSchemaError(str(exc.message)) from exc
            check_meta_shape(command.attributes_schema)
        async with self._uow as repos:
            slug = slugify(command.slug)
            if await repos.edge_types.get_by_slug(slug) is not None:
                raise EdgeTypeSlugConflictError(
                    f"Edge type with slug '{slug}' already exists"
                )
            edge_type = EdgeType.create(
                slug=slug,
                label=command.label,
                reverse_label=command.reverse_label,
                description=command.description,
                directional=command.directional,
                attributes_schema=command.attributes_schema,
            )
            await repos.edge_types.add(edge_type)
            await self._uow.commit()
        logger.info(
            "edge type created", edge_type_id=edge_type.id, slug=str(edge_type.slug)
        )
        return edge_type
