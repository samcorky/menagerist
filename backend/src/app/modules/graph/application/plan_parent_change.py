import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.graph.application.parent_change import (
    OnClash,
    OnDetach,
    ParentChange,
    ParentChangeResult,
    plan_parent_change,
)
from app.modules.graph.application.parent_type import (
    blocked_message,
    check_can_be_subtype,
    parent_of,
)
from app.modules.graph.application.permissions import GraphPermission
from app.modules.graph.application.type_scope import owner_scope
from app.modules.graph.domain.errors import NodeTypeNotFoundError
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.access import Access, Content
from app.shared_kernel.cqrs import QueryHandler
from app.shared_kernel.slug import slugify

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class PlanParentChangeQuery:
    """Ask what giving a type another parent, or none, would do, without doing it."""

    node_type_id: uuid.UUID
    parent: str | None = None
    on_clash: OnClash = "refuse"
    on_detach: OnDetach = "keep"


@dataclass(frozen=True, eq=False)
class ParentChangePlan:
    """What a parent change would do: its fields, whether it is allowed, and why not.

    `items` is how many items of the type there are. None of their values change.
    """

    parent: str | None
    previous: str | None
    result: ParentChangeResult
    reason: str | None
    items: int

    @property
    def allowed(self) -> bool:
        """Whether the change could be made as asked."""
        return not self.result.blocked_by


class PlanParentChange(
    QueryHandler[GraphRepos, PlanParentChangeQuery, ParentChangePlan]
):
    """Preview a type's change of parent: which fields merge, are kept or archived.

    It changes nothing and applies the same rules as `UpdateNodeType`, so what it
    reports is what an update with the same choices would do. It needs the same
    permission as that update, since it only previews what the person may do.
    """

    access: ClassVar[Access] = Content(GraphPermission.TYPE_WRITE)

    async def _handle(
        self, query: PlanParentChangeQuery, actor: Actor
    ) -> ParentChangePlan:
        """Work out the change, raising if the parent cannot be used at all."""
        scope = self.scope(actor)
        node_type = await self._repos.node_types.get(query.node_type_id, scope=scope)
        if node_type is None:
            raise NodeTypeNotFoundError(f"NodeType {query.node_type_id} not found")
        slug = str(node_type.slug)
        target = slugify(query.parent) if query.parent is not None else None
        change = ParentChange(on_clash=query.on_clash, on_detach=query.on_detach)
        old = await parent_of(self._repos, node_type, scope)
        new = (
            await check_can_be_subtype(
                self._repos,
                slug=slug,
                schema=node_type.attributes_schema,
                parent=target,
                scope=scope,
                check_keys=False,
            )
            if target is not None
            else None
        )
        result = plan_parent_change(
            old_slug=node_type.parent,
            old_parent=old.attributes_schema if old else None,
            new_slug=target,
            new_parent=new.attributes_schema if new else None,
            own=node_type.attributes_schema,
            change=change,
        )
        reason = (
            blocked_message(slug, target, result.blocked_by, change)
            if result.blocked_by and target is not None
            else None
        )
        items = await self._repos.nodes.count(
            scope=owner_scope(node_type.owner_id), type=slug
        )
        logger.debug("parent change planned", node_type_id=query.node_type_id)
        return ParentChangePlan(
            parent=target,
            previous=node_type.parent,
            result=result,
            reason=reason,
            items=items,
        )
