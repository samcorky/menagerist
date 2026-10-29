"""The media module's contribution to the scheduler."""

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock

from app.modules.media.adapters.scheduling import jobs as media_jobs
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.jobs import Lane

if TYPE_CHECKING:
    import pytest


def test_it_contributes_titled_cleanup_and_stray_file_jobs() -> None:
    """Both housekeeping jobs describe themselves to administrators."""
    bindings = {
        b.definition.job_key: b for b in media_jobs.media_job_contribution().bindings()
    }
    assert set(bindings) == {
        "media.cleanup",
        "media.remove_stray_files",
        "media.regenerate_thumbnails",
    }
    for key, schedule_key in (
        ("media.cleanup", "media.cleanup_schedule"),
        ("media.remove_stray_files", "media.stray_files_schedule"),
    ):
        job = bindings[key].definition
        assert job.schedule_key == schedule_key
        assert job.title.strip()
        assert job.description.strip()
    assert bindings["media.cleanup"].handler is media_jobs.cleanup_expired_media
    assert (
        bindings["media.remove_stray_files"].handler
        is media_jobs.remove_stray_media_files
    )


async def test_the_stray_file_job_leaves_recent_files_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Files newer than the staged-upload window may belong to an upload in flight."""
    handle = AsyncMock()
    monkeypatch.setattr(media_jobs, "create_media_uow", Mock())
    monkeypatch.setattr(media_jobs, "get_session_factory", Mock())
    monkeypatch.setattr(media_jobs, "LocalFilesystemMediaStorage", Mock())
    monkeypatch.setattr(
        media_jobs, "RemoveStrayMediaFiles", Mock(return_value=Mock(handle=handle))
    )
    monkeypatch.setattr(
        media_jobs, "get_media_settings", Mock(return_value=Mock(staged_ttl_hours=6))
    )
    before = datetime.now(UTC)
    await media_jobs.remove_stray_media_files(SYSTEM_ACTOR)
    after = datetime.now(UTC)
    assert handle.await_args is not None
    [command, actor] = handle.await_args.args
    assert actor is SYSTEM_ACTOR
    assert before - timedelta(hours=6) <= command.older_than
    assert command.older_than <= after - timedelta(hours=6)


async def test_the_job_applies_the_configured_expiry_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Staged and orphaned media expire after their own configured hours."""
    handle = AsyncMock()
    monkeypatch.setattr(media_jobs, "create_media_uow", Mock())
    monkeypatch.setattr(media_jobs, "get_session_factory", Mock())
    monkeypatch.setattr(media_jobs, "LocalFilesystemMediaStorage", Mock())
    monkeypatch.setattr(
        media_jobs, "CleanupExpiredMedia", Mock(return_value=Mock(handle=handle))
    )
    monkeypatch.setattr(
        media_jobs,
        "get_media_settings",
        Mock(return_value=Mock(staged_ttl_hours=2, orphaned_ttl_hours=5)),
    )
    await media_jobs.cleanup_expired_media(SYSTEM_ACTOR)
    assert handle.await_args is not None
    [command, actor] = handle.await_args.args
    assert actor is SYSTEM_ACTOR
    assert command.staged_before - command.orphaned_before == timedelta(hours=3)


def test_the_schedule_comes_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """The deployment value feeds the schedule source; empty keeps the job off."""
    monkeypatch.setattr(
        media_jobs,
        "get_media_settings",
        Mock(return_value=Mock(cleanup_schedule="", stray_files_schedule="5 3 * * 1")),
    )
    assert media_jobs.media_job_contribution().schedules() == {
        "media.cleanup_schedule": "",
        "media.stray_files_schedule": "5 3 * * 1",
    }


def test_thumbnail_rebuilding_is_a_heavy_manual_job_that_asks_first() -> None:
    """It never runs on its own, uses the heavy lane and wants a confirmation."""
    bindings = {
        b.definition.job_key: b for b in media_jobs.media_job_contribution().bindings()
    }
    job = bindings["media.regenerate_thumbnails"].definition
    assert job.schedule_key is None
    assert job.lane is Lane.HEAVY
    assert job.run_now_allowed
    assert job.confirm_required
    assert job.title.strip()
    assert job.description.strip()
    assert bindings["media.regenerate_thumbnails"].handler is (
        media_jobs.regenerate_thumbnails
    )


async def test_the_thumbnail_job_runs_the_regeneration_use_case(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The job drives the same use case as the command line, as the system."""
    handle = AsyncMock()
    use_case = Mock(return_value=Mock(handle=handle))
    monkeypatch.setattr(media_jobs, "create_media_uow", Mock())
    monkeypatch.setattr(media_jobs, "get_session_factory", Mock())
    monkeypatch.setattr(media_jobs, "LocalFilesystemMediaStorage", Mock())
    monkeypatch.setattr(media_jobs, "PillowImageProcessor", Mock())
    monkeypatch.setattr(media_jobs, "RegenerateThumbnails", use_case)
    monkeypatch.setattr(
        media_jobs, "get_media_settings", Mock(return_value=Mock(storage_path="/m"))
    )
    await media_jobs.regenerate_thumbnails(SYSTEM_ACTOR)
    assert handle.await_args is not None
    [command, actor] = handle.await_args.args
    assert actor is SYSTEM_ACTOR
    assert command.max_dimension == 320
