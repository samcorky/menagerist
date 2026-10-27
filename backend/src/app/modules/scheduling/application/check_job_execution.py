"""Read-only eligibility policy for claimed jobs."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from app.modules.scheduling.domain.execution_policy import execution_skip_reason
from app.modules.scheduling.ports.setup_state import SetupState
from app.shared_kernel.access import Access, System
from app.shared_kernel.cqrs import QueryHandler
from app.shared_kernel.jobs import JobDefinition

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


@dataclass(frozen=True, kw_only=True)
class CheckJobExecutionQuery:
    """The declared job policy and the adapter's restore reservation result."""

    job: JobDefinition
    restore_available: bool


class CheckJobExecution(QueryHandler[SetupState, CheckJobExecutionQuery, str | None]):
    """Decide whether setup or restoration requires skipping this execution."""

    access: ClassVar[Access] = System()

    async def _handle(
        self, request: CheckJobExecutionQuery, actor: Actor
    ) -> str | None:
        complete = False
        if request.restore_available:
            complete = (
                not request.job.needs_setup_complete or await self._repos.is_complete()
            )
        return execution_skip_reason(
            request.job,
            setup_complete=complete,
            restore_available=request.restore_available,
        )
