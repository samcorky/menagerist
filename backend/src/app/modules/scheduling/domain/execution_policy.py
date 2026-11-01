"""Eligibility rules applied before invoking a registered job."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.shared_kernel.jobs import JobDefinition


def execution_skip_reason(
    job: JobDefinition, *, setup_complete: bool, restore_available: bool
) -> str | None:
    """Restore always blocks execution; setup requirements are declared per job."""
    if not restore_available:
        return "restore_in_progress"
    if job.needs_setup_complete and not setup_complete:
        return "setup_incomplete"
    return None
