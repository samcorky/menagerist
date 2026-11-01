"""The job metadata registry rejects ambiguous and unknown keys."""

import pytest

from app.modules.scheduling.domain.errors import DuplicateJobError, UnknownJobError
from app.modules.scheduling.domain.registry import JobRegistry
from app.shared_kernel.jobs import JobDefinition


def test_registry_lists_and_resolves_job_definitions() -> None:
    """Scheduled jobs and run-now-only jobs remain distinct."""
    recurring = JobDefinition(job_key="backup.create", schedule_key="backup.schedule")
    manual = JobDefinition(job_key="manual", run_now_allowed=False)
    registry = JobRegistry([recurring, manual])
    assert registry.get("backup.create") is recurring
    assert registry.all() == (recurring, manual)
    assert registry.scheduled() == (recurring,)
    with pytest.raises(UnknownJobError, match="missing"):
        registry.get("missing")


def test_registry_rejects_duplicate_keys() -> None:
    """Different metadata cannot silently replace an existing job."""
    with pytest.raises(DuplicateJobError, match=r"backup\.create"):
        JobRegistry(
            [
                JobDefinition(job_key="backup.create"),
                JobDefinition(job_key="backup.create"),
            ]
        )
