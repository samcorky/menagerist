from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock

import pytest

from app.entrypoints.cli import backups
from app.platform import alembic_runner

if TYPE_CHECKING:
    from _pytest.monkeypatch import MonkeyPatch


def test_upgrade_skips_backup_when_disabled(monkeypatch: MonkeyPatch) -> None:
    """Check the upgrade and backup ordering."""
    upgrade = Mock()
    monkeypatch.setattr(alembic_runner, "upgrade", upgrade)
    monkeypatch.setattr(
        backups, "get_backup_settings", lambda: Mock(before_migrate=False)
    )
    backups.upgrade_with_backup("head")
    upgrade.assert_called_once_with("head")


@pytest.mark.parametrize(("current", "pending"), [((), True), (("old",), False)])
def test_upgrade_skips_backup_without_existing_pending_schema(
    monkeypatch: MonkeyPatch, current: tuple[str, ...], pending: bool
) -> None:
    """Check the upgrade and backup ordering."""
    upgrade = Mock()
    monkeypatch.setattr(alembic_runner, "upgrade", upgrade)
    monkeypatch.setattr(alembic_runner, "pending", AsyncMock(return_value=pending))
    monkeypatch.setattr(
        alembic_runner, "db_current_revisions", AsyncMock(return_value=current)
    )
    monkeypatch.setattr(
        backups, "get_backup_settings", lambda: Mock(before_migrate=True)
    )
    monkeypatch.setattr(backups, "get_session_factory", Mock())
    backups.upgrade_with_backup("head")
    upgrade.assert_called_once_with("head")


def test_failed_backup_prevents_upgrade(monkeypatch: MonkeyPatch) -> None:
    """Check the upgrade and backup ordering."""
    upgrade = Mock()
    monkeypatch.setattr(alembic_runner, "upgrade", upgrade)
    monkeypatch.setattr(
        backups, "get_backup_settings", lambda: Mock(before_migrate=True)
    )
    monkeypatch.setattr(
        backups,
        "backup_before_upgrade",
        AsyncMock(side_effect=RuntimeError("disk full")),
    )
    with pytest.raises(RuntimeError, match="disk full"):
        backups.upgrade_with_backup("head")
    upgrade.assert_not_called()


def test_no_backup_option_skips_enabled_policy(monkeypatch: MonkeyPatch) -> None:
    """The explicit CLI opt-out skips backup even when configured."""
    upgrade = Mock()
    backup = AsyncMock()
    monkeypatch.setattr(alembic_runner, "upgrade", upgrade)
    monkeypatch.setattr(
        backups, "get_backup_settings", lambda: Mock(before_migrate=True)
    )
    monkeypatch.setattr(backups, "backup_before_upgrade", backup)
    backups.upgrade_with_backup("head", backup=False)
    backup.assert_not_awaited()
    upgrade.assert_called_once_with("head")


async def test_pending_upgrade_creates_labelled_backup(
    monkeypatch: MonkeyPatch,
) -> None:
    """Existing pending schemas produce a verified, revision-labelled backup."""
    create = AsyncMock()
    monkeypatch.setattr(backups, "get_session_factory", Mock())
    monkeypatch.setattr(
        alembic_runner, "db_current_revisions", AsyncMock(return_value=("old",))
    )
    monkeypatch.setattr(alembic_runner, "pending", AsyncMock(return_value=True))
    monkeypatch.setattr(alembic_runner, "target_revisions", Mock(return_value=("new",)))
    monkeypatch.setattr(backups, "create_backup", create)
    await backups.backup_before_upgrade("head")
    create.assert_awaited_once_with(
        label="pre-migration", from_revision="old", to_revision="new"
    )


@pytest.mark.parametrize("at_head", [False, True])
async def test_pending_uses_live_and_script_revisions(
    monkeypatch: MonkeyPatch, at_head: bool
) -> None:
    """Pending checks the actual script chain against the live revision."""
    from app.platform import database

    heads = alembic_runner.target_revisions()
    assert heads
    monkeypatch.setattr(database, "get_session_factory", Mock())
    monkeypatch.setattr(
        alembic_runner,
        "db_current_revisions",
        AsyncMock(return_value=heads if at_head else ()),
    )
    assert await alembic_runner.pending() is not at_head
