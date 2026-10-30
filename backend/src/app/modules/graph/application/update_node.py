import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

import structlog

from app.modules.graph.application._validate_attributes import validate_attributes
from app.modules.graph.application.choice_lists import resolve_choice_lists
from app.modules.graph.application.extra_schema_limits import check_extra_schema_limits
from app.modules.graph.application.permissions import GraphPermission
from app.modules.graph.application.schema_meta import (
    check_schema_definition,
    merge_attribute_schemas,
)
from app.modules.graph.domain.errors import NodeNotFoundError
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.node_type import NodeType

# Needed at runtime: the CQRS signature test evaluates __init__ annotations.
from app.modules.graph.ports.choice_list_source import ChoiceListSource  # noqa: TC001
from app.modules.graph.ports.unit_of_work import GraphRepos, GraphUnitOfWork
from app.shared_kernel.access import Access, Content

# Needed at runtime: the CQRS signature test evaluates __init__ annotations.
from app.shared_kernel.cqrs import CommandHandler
from app.shared_kernel.slug import slugify

if TYPE_CHECKING:
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class UpdateNodeCommand:
    """Request to update a node's editable fields.

    A field left as `None` is unchanged. `type` can be set or changed, and
    `clear_type` removes it (it wins over `type`); the node's attributes are kept
    either way.
    """

    node_id: uuid.UUID
    name: str | None = field(default=None)
    type: str | None = field(default=None)
    clear_type: bool = field(default=False)
    description: str | None = field(default=None)
    attributes: dict[str, Any] | None = field(default=None)
    favourite: bool | None = field(default=None)
    tags: list[str] | None = field(default=None)
    extra_schema: dict[str, Any] | None = field(default=None)


class UpdateNode(CommandHandler[GraphUnitOfWork, UpdateNodeCommand, Node]):
    """Update an existing node's editable fields."""

    access: ClassVar[Access] = Content(GraphPermission.ITEM_WRITE)

    def __init__(
        self,
        uow: GraphUnitOfWork,
        guard: AccessGuard,
        choice_lists: ChoiceListSource | None = None,
    ) -> None:
        super().__init__(uow, guard)
        self._choice_lists = choice_lists

    async def _handle(self, command: UpdateNodeCommand, actor: Actor) -> Node:
        """Apply `command`'s changes to the node and commit."""
        if command.extra_schema is not None:
            check_schema_definition(command.extra_schema)
        async with self._uow as repos:
            node = await repos.nodes.get(command.node_id, scope=self.scope(actor))
            if node is None:
                raise NodeNotFoundError(f"Node {command.node_id} not found")
            self._guard.assert_can_modify(actor, node.owner_id)

            if command.extra_schema is not None:
                check_extra_schema_limits(
                    command.extra_schema, previous=node.extra_schema
                )

            # The type the item will have once this command is applied: clearing wins
            # over a type in the same command, and it is what the checks below use.
            new_type = None if command.clear_type else command.type
            target_type = self._target_type(node, new_type, command.clear_type)
            if command.attributes is not None or target_type != node.type:
                await self._validate(repos, node, target_type, command)

            if command.clear_type:
                node.clear_type()
            node.update(
                name=command.name,
                type=new_type,
                description=command.description,
                attributes=command.attributes,
                favourite=command.favourite,
                tags=command.tags,
                extra_schema=command.extra_schema,
            )

            if node.type is not None and new_type is not None:
                slug = node.type
                if (
                    await repos.node_types.get_by_slug(slug, guard_item_write=True)
                    is None
                ):
                    await repos.node_types.add(
                        NodeType.create(slug=slug, label=new_type)
                    )

            await repos.nodes.save(node)
            await self._uow.commit()
        logger.info("node updated", node_id=command.node_id)
        return node

    @staticmethod
    def _target_type(node: Node, new_type: str | None, clearing: bool) -> str | None:
        """The slug the node will have after the command, without changing the node.

        A blank or unusable type is left for the domain to refuse when it is applied.
        """
        if clearing:
            return None
        if new_type is None:
            return node.type
        return slugify(new_type) or None

    async def _validate(
        self,
        repos: GraphRepos,
        node: Node,
        type_slug: str | None,
        command: UpdateNodeCommand,
    ) -> None:
        """Check the item's fields against the type it will have.

        Merging the type's schema with the item's own fields refuses a name both
        define, which a type change could otherwise introduce. Values are only
        validated when the command sends them: changing the type keeps the
        existing ones, whether or not the new type has a field for them.
        """
        type_schema: dict[str, Any] | None = None
        if type_slug is not None:
            node_type = await repos.node_types.get_by_slug(type_slug)
            type_schema = node_type.attributes_schema if node_type else None
        extra_schema = (
            command.extra_schema
            if command.extra_schema is not None
            else node.extra_schema
        )
        merged = merge_attribute_schemas(type_schema, extra_schema)
        if command.attributes is None:
            return
        schema = await resolve_choice_lists(merged, self._choice_lists)
        if schema is not None:
            validate_attributes(schema, command.attributes, previous=node.attributes)
