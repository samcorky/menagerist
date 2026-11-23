import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.graph.application.batch_ids import check_batch_ids, unknown_items_error
from app.modules.graph.application.permissions import GraphPermission
from app.modules.graph.ports.unit_of_work import GraphUnitOfWork
from app.shared_kernel.access import Access, Content
from app.shared_kernel.cqrs import CommandHandler
from app.shared_kernel.errors import ValidationError

if TYPE_CHECKING:
    from app.modules.graph.domain.node import Node
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class TagNodesCommand:
    """Request to add and remove tags on several nodes in one transaction."""

    node_ids: list[uuid.UUID]
    add: list[str] = field(default_factory=list)
    remove: list[str] = field(default_factory=list)


class TagNodes(CommandHandler[GraphUnitOfWork, TagNodesCommand, int]):
    """Add and remove tags on several nodes, all or none."""

    access: ClassVar[Access] = Content(GraphPermission.ITEM_WRITE)

    async def _handle(self, command: TagNodesCommand, actor: Actor) -> int:
        """Apply the tag changes and return how many nodes actually changed."""
        ids = check_batch_ids(command.node_ids)
        add = _clean(command.add)
        remove = _clean(command.remove)
        if not add and not remove:
            raise ValidationError("Choose a tag to add or remove")
        async with self._uow as repos:
            found: list[Node] = []
            missing: list[uuid.UUID] = []
            for node_id in ids:
                node = await repos.nodes.get(node_id, scope=self.scope(actor))
                if node is None:
                    missing.append(node_id)
                else:
                    found.append(node)
            if missing:
                raise unknown_items_error(missing)
            for node in found:
                self._guard.assert_can_modify(actor, node.owner_id)
            updated = 0
            for node in found:
                tags = [tag for tag in node.tags if tag not in remove]
                tags.extend(tag for tag in add if tag not in tags)
                if tags == node.tags:
                    continue
                node.update(tags=tags)
                await repos.nodes.save(node)
                updated += 1
            await self._uow.commit()
        logger.info("nodes tagged", count=updated)
        return updated


def _clean(tags: list[str]) -> list[str]:
    """Trim and lowercase tags the way a node does, dropping blanks and repeats."""
    return list(dict.fromkeys(t for tag in tags if (t := tag.strip().lower())))
