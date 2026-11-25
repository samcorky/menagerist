from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import uuid

    from app.shared_kernel.actor import Actor


class ImportActors(Protocol):
    """Who a queued import runs as, now that its owner is not making the request."""

    async def actor_for(
        self, owner_id: uuid.UUID, grants: frozenset[str] | None
    ) -> Actor | None:
        """Return `owner_id` as they are now, capped by `grants`.

        `None` when the account is gone or disabled.
        """
        ...
