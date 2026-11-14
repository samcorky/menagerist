from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import uuid

    from app.modules.transfer.domain.run import Run
    from app.shared_kernel.content_filter import ContentFilter


class RunRepository(Protocol):
    """Access to bundle runs, independent of storage backend."""

    async def add(self, run: Run) -> None:
        """Add a new run."""
        ...

    async def save(self, run: Run) -> None:
        """Persist changes to an existing run."""
        ...

    async def get(self, run_id: uuid.UUID, *, scope: ContentFilter) -> Run | None:
        """Return the run with `run_id`, or `None`."""
        ...

    async def get_active_for_bundle(
        self, bundle_id: str, *, scope: ContentFilter
    ) -> Run | None:
        """Return the installing or installed run of `bundle_id`, if any."""
        ...

    async def list_active(self, *, scope: ContentFilter) -> list[Run]:
        """Return every installing or installed run."""
        ...

    async def list_for_bundle(
        self, bundle_id: str, *, scope: ContentFilter
    ) -> list[Run]:
        """Return every run of `bundle_id`, whatever its status, newest first."""
        ...

    async def claim_orphaned(
        self, owner_id: uuid.UUID, *, legacy_owner_ids: frozenset[uuid.UUID]
    ) -> int:
        """Give `owner_id` every run with no owner or a legacy owner.

        System-level and unscoped, deleted rows included. Returns the count.
        """
        ...
