import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

import jsonschema
import structlog

from app.modules.graph.application.choice_lists import check_list_refs, strip_list_enums
from app.modules.graph.application.parent_type import (
    check_can_be_subtype,
    check_subtypes_keep_their_keys,
)
from app.modules.graph.application.permissions import GraphPermission
from app.modules.graph.application.schema_meta import check_meta_shape
from app.modules.graph.domain.errors import InvalidSchemaError, NodeTypeNotFoundError
from app.modules.graph.domain.node_type import NodeType

# Needed at runtime: the CQRS signature test evaluates __init__ annotations.
from app.modules.graph.ports.choice_list_source import ChoiceListSource  # noqa: TC001
from app.modules.graph.ports.unit_of_work import GraphUnitOfWork
from app.shared_kernel.access import Access, Content
from app.shared_kernel.cqrs import CommandHandler
from app.shared_kernel.slug import slugify

if TYPE_CHECKING:
    from app.modules.graph.ports.unit_of_work import GraphRepos
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor
    from app.shared_kernel.content_filter import ContentFilter

logger = structlog.get_logger()


@dataclass(kw_only=True)
class UpdateNodeTypeCommand:
    """Request to update a node type's editable fields. `slug` is immutable."""

    node_type_id: uuid.UUID
    label: str | None = field(default=None)
    description: str | None = field(default=None)
    attributes_schema: dict[str, Any] | None = field(default=None)
    icon: str | None = field(default=None)
    colour: str | None = field(default=None)
    clear_icon: bool = field(default=False)
    clear_colour: bool = field(default=False)
    parent: str | None = field(default=None)
    clear_parent: bool = field(default=False)


class UpdateNodeType(CommandHandler[GraphUnitOfWork, UpdateNodeTypeCommand, NodeType]):
    """Update an existing node type's editable fields."""

    access: ClassVar[Access] = Content(GraphPermission.TYPE_WRITE)

    def __init__(
        self,
        uow: GraphUnitOfWork,
        guard: AccessGuard,
        choice_lists: ChoiceListSource | None = None,
    ) -> None:
        super().__init__(uow, guard)
        self._choice_lists = choice_lists

    async def _handle(self, command: UpdateNodeTypeCommand, actor: Actor) -> NodeType:
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
            node_type = await repos.node_types.get(
                command.node_type_id, scope=self.scope(actor)
            )
            if node_type is None:
                raise NodeTypeNotFoundError(
                    f"NodeType {command.node_type_id} not found"
                )

            await self._check_parent_rules(
                repos, node_type, command, attributes_schema, self.scope(actor)
            )
            node_type.update(
                label=command.label,
                description=command.description,
                attributes_schema=attributes_schema,
                icon=command.icon,
                colour=command.colour,
                parent=command.parent,
            )
            if command.clear_icon:
                node_type.clear_icon()
            if command.clear_colour:
                node_type.clear_colour()
            if command.clear_parent and command.parent is None:
                node_type.clear_parent()

            await repos.node_types.save(node_type)
            await self._uow.commit()
        logger.info("node type updated", node_type_id=command.node_type_id)
        return node_type

    async def _check_parent_rules(
        self,
        repos: GraphRepos,
        node_type: NodeType,
        command: UpdateNodeTypeCommand,
        new_schema: dict[str, Any] | None,
        scope: ContentFilter,
    ) -> None:
        """Check the parent stays one level deep and its fields free of clashes.

        This runs before anything changes, so a refused update leaves the type alone.
        """
        if command.parent is not None:
            parent: str | None = slugify(command.parent)
        elif command.clear_parent:
            parent = None
        else:
            parent = node_type.parent
        schema_changed = command.attributes_schema is not None
        schema = new_schema if schema_changed else node_type.attributes_schema
        if parent is not None and (parent != node_type.parent or schema_changed):
            await check_can_be_subtype(
                repos,
                slug=str(node_type.slug),
                schema=schema,
                parent=parent,
                scope=scope,
            )
        if schema_changed:
            await check_subtypes_keep_their_keys(
                repos, parent=node_type, schema=schema, scope=scope
            )
