"""Ask the worker to run one of a module's jobs for work someone started.

A module keeps its own record of the work waiting (an import, say) and requests its
job by key; the job's run drains whatever is waiting. The scheduling module answers
the request through a bridge in `entrypoints/`, so no module imports it.
"""

from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID


class JobQueue(Protocol):
    """Queue a run of a job, reusing one still waiting to start.

    A run already under way may have looked for work before this request's was
    recorded, so a request made while one runs queues one more behind it.
    """

    async def request(self, job_key: str, *, requested_by: UUID) -> None:
        """Queue `job_key` for work `requested_by` started.

        Raises:
            NotFoundError: no job has the key.
            ConflictError: the job does not coalesce its runs.
        """
        ...


@dataclass
class InMemoryJobQueue:
    """Records each request, for tests; nothing runs."""

    requests: list[tuple[str, UUID]] = field(default_factory=list)

    async def request(self, job_key: str, *, requested_by: UUID) -> None:
        """Record the request."""
        self.requests.append((job_key, requested_by))
