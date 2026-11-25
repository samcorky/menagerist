import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

import jsonschema
import structlog

from app.modules.graph.application.choice_lists import check_list_refs, strip_list_enums
from app.modules.graph.application.parent_change import OnClash, OnDetach, ParentChange
from app.modules.graph.application.parent_type import plan_type_update, with_inherited
from app.modules.graph.application.permissions import GraphPermission
from app.modules.graph.domain.errors import InvalidSchemaError, NodeTypeNotFoundError
from app.modules.graph.domain.node_type import NodeType

# Needed at runtime: the CQRS signature test evaluates __init__ annotations.
from app.modules.graph.ports.choice_list_source import ChoiceListSource  # noqa: TC001
from app.modules.graph.ports.unit_of_work import GraphUnitOfWork
from app.shared_kernel.access import Access, Content
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor

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
    # What to do when the new parent defines a key the type does, and when the type
    # loses the fields it inherited: see `plan_parent_change`.
    on_clash: OnClash = field(default="refuse")
    on_detach: OnDetach = field(default="keep")


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

            plan = await plan_type_update(
                repos,
                node_type,
                parent=command.parent,
                clear_parent=command.clear_parent,
                new_schema=attributes_schema,
                change=ParentChange(
                    on_clash=command.on_clash, on_detach=command.on_detach
                ),
                scope=self.scope(actor),
            )
            node_type.update(
                label=command.label,
                description=command.description,
                attributes_schema=plan.schema,
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

            if plan.parent_type is not None and plan.parent_schema is not None:
                plan.parent_type.update(attributes_schema=plan.parent_schema)
                await repos.node_types.save(plan.parent_type)
            await repos.node_types.save(node_type)
            await self._uow.commit()
            updated = await with_inherited(repos, node_type, scope=self.scope(actor))
        logger.info("node type updated", node_type_id=command.node_type_id)
        return updated
