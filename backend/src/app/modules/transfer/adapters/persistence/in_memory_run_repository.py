from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid

    from app.modules.transfer.domain.run import Run
    from app.shared_kernel.content_filter import ContentFilter


class InMemoryRunRepository:
    """Dict-backed `RunRepository` for tests."""

    def __init__(self) -> None:
        self._runs: dict[uuid.UUID, Run] = {}

    async def add(self, run: Run) -> None:
        """Add a new run."""
        self._runs[run.id] = run

    async def save(self, run: Run) -> None:
        """Persist changes to an existing run."""
        self._runs[run.id] = run

    async def get(self, run_id: uuid.UUID, *, scope: ContentFilter) -> Run | None:
        """Return the run with `run_id` in `scope`, or `None`."""
        found = self._runs.get(run_id)
        return found if found is not None and scope.covers(found.owner_id) else None

    async def get_active_for_bundle(
        self, bundle_id: str, *, scope: ContentFilter
    ) -> Run | None:
        """Return the installing or installed run of `bundle_id`, if any."""
        return next(
            (
                r
                for r in self._runs.values()
                if r.bundle_id == bundle_id and r.is_active and scope.covers(r.owner_id)
            ),
            None,
        )

    async def list_active(self, *, scope: ContentFilter) -> list[Run]:
        """Return every installing or installed run, oldest first."""
        return sorted(
            (
                r
                for r in self._runs.values()
                if r.is_active and scope.covers(r.owner_id)
            ),
            key=lambda r: r.id,
        )

    async def list_for_bundle(
        self, bundle_id: str, *, scope: ContentFilter
    ) -> list[Run]:
        """Return every run of `bundle_id`, whatever its status, newest first."""
        return sorted(
            (
                r
                for r in self._runs.values()
                if r.bundle_id == bundle_id and scope.covers(r.owner_id)
            ),
            key=lambda r: r.id,
            reverse=True,
        )

    async def claim_orphaned(
        self, owner_id: uuid.UUID, *, legacy_owner_ids: frozenset[uuid.UUID]
    ) -> int:
        """Give `owner_id` every run with no owner or a legacy owner."""
        claimed = [
            row
            for row in self._runs.values()
            if row.owner_id is None or row.owner_id in legacy_owner_ids
        ]
        for row in claimed:
            row.owner_id = owner_id
        return len(claimed)
