"""First-class in-memory implementation of the queue contract."""

from typing import TYPE_CHECKING

from app.modules.scheduling.domain.queue_policy import next_claim, select_submission

if TYPE_CHECKING:
    from collections.abc import Collection
    from datetime import datetime
    from uuid import UUID

    from app.modules.scheduling.adapters.persistence.in_memory_store import (
        InMemorySchedulingStore,
    )
    from app.modules.scheduling.domain.job_run import JobRun
    from app.shared_kernel.jobs import Lane


class InMemoryJobRunQueue:
    """Apply queue policies atomically within one event-loop turn."""

    def __init__(self, store: InMemorySchedulingStore) -> None:
        self._store = store

    async def enqueue(self, run: JobRun, *, deduplicate_active: bool = False) -> JobRun:
        """Reuse accepted runs and enforce the submission's overlap policy."""
        previous = self._store.runs.get(run.id)
        if previous is None and run.deduplication_key is not None:
            previous = next(
                (
                    item
                    for item in self._store.runs.values()
                    if item.deduplication_key == run.deduplication_key
                ),
                None,
            )
        selected = select_submission(
            run,
            previous,
            self._store.active(run.job_key),
            deduplicate_active=deduplicate_active,
        )
        self._store.save(selected)
        return self._store.get(selected.id)

    async def claim(
        self,
        lanes: Collection[Lane],
        worker_id: str,
        now: datetime,
        *,
        run_id: UUID | None = None,
    ) -> JobRun | None:
        """Select and start a due run without yielding between read and write."""
        selected = next_claim(self._store.runs.values(), lanes, now, run_id=run_id)
        if selected is None:
            return None
        claimed = self._store.get(selected.id)
        claimed.start(worker_id, now)
        self._store.save(claimed)
        return claimed
