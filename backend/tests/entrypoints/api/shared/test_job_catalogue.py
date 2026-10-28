"""Every job a module contributes explains itself to administrators."""

from app.entrypoints.api.shared.job_catalogue import CONTRIBUTIONS, build_catalogue


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
