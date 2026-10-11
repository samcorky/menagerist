from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import uuid

    from app.shared_kernel.access_scope import AccessScope
    from app.shared_kernel.actor import Actor


class AccessPolicy(Protocol):
    """The only place that knows who may see or change what."""

    def scope_for(self, actor: Actor) -> AccessScope:
        """Return the scope of content `actor` may see."""
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

    def require_admin(self, actor: Actor) -> None:
        """Raise `ForbiddenError` unless `actor` is an administrator."""
        ...
