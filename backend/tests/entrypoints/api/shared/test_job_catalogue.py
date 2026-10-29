"""Every job a module contributes explains itself to administrators."""

from app.entrypoints.api.shared.job_catalogue import (
    CONTRIBUTIONS,
    build_catalogue,
    tunable_schedule_keys,
)


def test_every_contributed_job_has_a_title_and_description() -> None:
    """The scheduled tasks page shows this copy, so a job cannot ship without it."""
    missing = [
        job.job_key
        for job in build_catalogue().registry.all()
        if not job.title.strip() or not job.description.strip()
    ]
    assert not missing, f"Jobs without a title and description: {missing}"


def test_each_contribution_adds_jobs_with_distinct_keys() -> None:
    """Contributions compose without clashing."""
    keys = [
        binding.definition.job_key
        for contribution in CONTRIBUTIONS
        for binding in contribution.bindings()
    ]
    assert len(keys) == len(set(keys)) > 0


def test_every_job_schedule_key_resolves_to_a_setting_or_a_supplied_value() -> None:
    """A key nobody supplies would only fail on the worker's first tick."""
    supplied = {
        key for contribution in CONTRIBUTIONS for key in contribution.schedules()
    }
    unresolved = [
        job.schedule_key
        for job in build_catalogue().registry.scheduled()
        if job.schedule_key not in supplied | tunable_schedule_keys()
    ]
    assert not unresolved, f"Schedule keys with no value: {unresolved}"


def test_only_tunable_settings_are_live() -> None:
    """Every task's own schedule is editable at runtime; the scheduler's own is not."""
    live = tunable_schedule_keys()
    for key in (
        "backup.schedule",
        "identity.purge_expired_schedule",
        "media.cleanup_schedule",
        "retention.purge_schedule",
    ):
        assert key in live
    assert "scheduling.prune_schedule" not in live
