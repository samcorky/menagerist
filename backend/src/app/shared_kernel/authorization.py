from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


class AuthorizationPort(Protocol):
    """Cross-cutting permission check shared by every module's use cases.

    `action` is a plain `"module.entity.verb"` string (e.g.
    `"graph.node.create"`) - data describing what's being attempted, not a
    callable or a registry. Resolving that string to a policy decision is the
    adapter's job, kept off the port itself.
    """

    async def check(self, actor: Actor, action: str) -> None:
        """Raise `ForbiddenError` if `actor` may not perform `action`."""
        ...
