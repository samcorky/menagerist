import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from app.entrypoints.cli.data import purge_deleted
from app.entrypoints.cli.purge_deleted import (
    PurgeDeletedContentCommand,
    PurgeDeletedContentResult,
)
from app.platform.config.retention import RetentionSettings
from app.shared_kernel.actor import SYSTEM_ACTOR

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


class _Purge:
    """Records the command it is given and returns fixed counts."""

    def __init__(self) -> None:
        self.commands: list[PurgeDeletedContentCommand] = []
        self.actors: list[Actor] = []

    async def handle(
        self, command: PurgeDeletedContentCommand, actor: Actor
    ) -> PurgeDeletedContentResult:
        await asyncio.sleep(0)
        self.commands.append(command)
        self.actors.append(actor)
        return PurgeDeletedContentResult(items=3, connections=5, collections=1)


@pytest.fixture
def purge(monkeypatch: pytest.MonkeyPatch) -> _Purge:
    """Stub the composition and pin the retention setting at 14 days."""
    recorder = _Purge()
    monkeypatch.setattr(
        "app.entrypoints.cli.purge_deleted.build_purge_deleted_content",
        lambda: recorder,
    )
    monkeypatch.setattr(
        "app.platform.config.retention.get_retention_settings",
        lambda: RetentionSettings(deleted_days=14),
    )
    return recorder


def _age_in_days(command: PurgeDeletedContentCommand) -> float:
    return (datetime.now(UTC) - command.older_than) / timedelta(days=1)


def test_uses_the_configured_retention_and_reports_the_counts(purge: _Purge) -> None:
    """Without a flag the retention setting decides the cutoff."""
    report = purge_deleted()

    (command,) = purge.commands
    assert command.dry_run is False
    assert 13.99 < _age_in_days(command) < 14.01
    assert purge.actors == [SYSTEM_ACTOR]
    assert report.title == "Deleted-content purge"
    assert report.value == {
        "message": "Deleted content purged",
        "cutoff": command.older_than,
        "dry_run": False,
        "items": 3,
        "connections": 5,
        "collections": 1,
    }


def test_older_than_days_overrides_the_setting(purge: _Purge) -> None:
    """An explicit number of days wins over the setting."""
    purge_deleted(older_than_days=2)

    assert 1.99 < _age_in_days(purge.commands[0]) < 2.01


def test_dry_run_says_nothing_was_deleted(purge: _Purge) -> None:
    """A dry run passes the flag on and states that nothing changed."""
    report = purge_deleted(dry_run=True)

    assert purge.commands[0].dry_run is True
    assert report.value["message"] == "Dry run: nothing was deleted"  # type: ignore[index]
    assert report.value["dry_run"] is True  # type: ignore[index]


@pytest.mark.parametrize("days", [0, -3])
def test_fewer_than_one_day_is_refused(
    purge: _Purge, capsys: pytest.CaptureFixture[str], days: int
) -> None:
    """Retention below the one-day minimum is refused before anything runs."""
    with pytest.raises(SystemExit) as exit_info:
        purge_deleted(older_than_days=days)

    assert exit_info.value.code == 1
    assert "at least 1" in capsys.readouterr().err
    assert purge.commands == []
