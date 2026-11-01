"""Execution eligibility is independent of the worker and its locks."""

import pytest

from app.modules.scheduling.domain.execution_policy import execution_skip_reason
from app.shared_kernel.jobs import JobDefinition


@pytest.mark.parametrize(
    ("needs_setup", "setup", "restore", "reason"),
    [
        (True, True, True, None),
        (True, False, True, "setup_incomplete"),
        (False, False, True, None),
        (True, True, False, "restore_in_progress"),
        (False, True, False, "restore_in_progress"),
    ],
)
def test_execution_policy(
    needs_setup: bool, setup: bool, restore: bool, reason: str | None
) -> None:
    """Restore always blocks execution; only declared jobs require setup."""
    assert (
        execution_skip_reason(
            JobDefinition(job_key="x", needs_setup_complete=needs_setup),
            setup_complete=setup,
            restore_available=restore,
        )
        == reason
    )
