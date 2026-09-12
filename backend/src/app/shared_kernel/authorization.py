from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


class AuthorizationPort(Protocol):
    """Permission checking port shared across modules."""

    async def check(self, actor: Actor, action: str) -> None:
        """Raise `ForbiddenError` if `actor` may not perform `action`."""
        ...
