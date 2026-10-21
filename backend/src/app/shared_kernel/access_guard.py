from typing import TYPE_CHECKING, Protocol

from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.errors import ForbiddenError, NotFoundError

if TYPE_CHECKING:
    import uuid

    from app.shared_kernel.access import Access
    from app.shared_kernel.actor import Actor


class AccessGuard(Protocol):
    """The one place that decides who may call a use case and see what."""

    async def check(self, actor: Actor, access: Access) -> None:
        """Raise `ForbiddenError` unless `actor` satisfies `access`."""
        ...

    def scope_for(self, actor: Actor) -> ContentFilter:
        """Return the content `actor` may see."""
        ...

    def assert_can_view(self, actor: Actor, owner_id: uuid.UUID | None) -> None:
        """Raise `NotFoundError` unless `actor` may see content owned by `owner_id`."""
        ...

    def assert_can_modify(self, actor: Actor, owner_id: uuid.UUID | None) -> None:
        """Raise `NotFoundError` unless `actor` may change that content."""
        ...

    def assert_can_delete(self, actor: Actor, owner_id: uuid.UUID | None) -> None:
        """Raise `NotFoundError` unless `actor` may delete that content."""
        ...


class InMemoryAccessGuard:
    """Test guard that records checks and can be told to deny them.

    Ownership follows the Stage 1 rule: people see only what they own; the
    system actor sees everything.
    """

    def __init__(self, *, deny: bool = False) -> None:
        self.deny = deny
        self.checked: list[tuple[Actor, Access]] = []

    async def check(self, actor: Actor, access: Access) -> None:
        """Record the check; raise `ForbiddenError` when told to deny."""
        self.checked.append((actor, access))
        if self.deny:
            raise ForbiddenError("You do not have permission to do that.")

    def scope_for(self, actor: Actor) -> ContentFilter:
        """Return everything for the system actor, else the actor's own content."""
        if actor.is_system:
            return ContentFilter.everyone()
        return ContentFilter.of(actor.id)

    def assert_can_view(self, actor: Actor, owner_id: uuid.UUID | None) -> None:
        """Raise `NotFoundError` unless the content is the actor's own."""
        if actor.is_system or owner_id == actor.id:
            return
        raise NotFoundError("Not found.")

    def assert_can_modify(self, actor: Actor, owner_id: uuid.UUID | None) -> None:
        """Raise `NotFoundError` unless the content is the actor's own."""
        self.assert_can_view(actor, owner_id)

    def assert_can_delete(self, actor: Actor, owner_id: uuid.UUID | None) -> None:
        """Raise `NotFoundError` unless the content is the actor's own."""
        self.assert_can_view(actor, owner_id)
