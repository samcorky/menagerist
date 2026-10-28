"""The scheduler contributes its own maintenance job through a use case."""

from unittest.mock import AsyncMock, MagicMock

from app.modules.scheduling.adapters.cli.jobs import prune_runs_job
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.jobs import Lane, Overlap


async def test_prune_binding_calls_a_fresh_command_with_the_current_retention() -> None:
    """Each run builds a new guarded command and reads the quota again."""
    command = MagicMock(handle=AsyncMock(return_value=3))
    factory = MagicMock(return_value=command)
    quotas = iter([12, 30])

    async def keep_per_job() -> int:
        return next(quotas)

    binding = prune_runs_job(factory, keep_per_job=keep_per_job)
    assert binding.definition.job_key == "scheduling.prune_runs"
    assert binding.definition.lane is Lane.DEFAULT
    assert binding.definition.overlap is Overlap.COALESCE
    assert not binding.definition.needs_setup_complete
    await binding.handler(SYSTEM_ACTOR)
    first, _ = command.handle.call_args.args
    await binding.handler(SYSTEM_ACTOR)
    second, actor = command.handle.call_args.args
    assert factory.call_count == 2
    assert (first.keep_per_job, second.keep_per_job) == (12, 30)
    assert actor is SYSTEM_ACTOR
