"""The scheduler contributes its own maintenance job through a use case."""

from unittest.mock import AsyncMock, MagicMock

from app.modules.scheduling.adapters.cli.jobs import prune_runs_job
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.jobs import Lane, Overlap


async def test_prune_binding_calls_a_fresh_command_with_configured_retention() -> None:
    """The driver delegates retention to a fresh guarded application command."""
    command = MagicMock(handle=AsyncMock(return_value=3))
    factory = MagicMock(return_value=command)
    binding = prune_runs_job(factory, keep_per_job=12)
    assert binding.definition.job_key == "scheduling.prune_runs"
    assert binding.definition.lane is Lane.DEFAULT
    assert binding.definition.overlap is Overlap.COALESCE
    assert not binding.definition.needs_setup_complete
    await binding.handler(SYSTEM_ACTOR)
    await binding.handler(SYSTEM_ACTOR)
    assert factory.call_count == 2
    request, actor = command.handle.call_args.args
    assert request.keep_per_job == 12
    assert actor is SYSTEM_ACTOR
