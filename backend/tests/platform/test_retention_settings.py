import pytest
from pydantic import ValidationError

from app.platform.config import RetentionSettings, get_retention_settings


def test_default_is_thirty_days() -> None:
    """Deleted content stays recoverable for 30 days unless configured."""
    assert RetentionSettings().deleted_retention_days == 30


def test_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """The retention comes from `MENAGERIST_DELETED_RETENTION_DAYS`."""
    monkeypatch.setenv("MENAGERIST_DELETED_RETENTION_DAYS", "7")
    get_retention_settings.cache_clear()
    try:
        assert get_retention_settings().deleted_retention_days == 7
    finally:
        get_retention_settings.cache_clear()


@pytest.mark.parametrize("value", ["0", "-5"])
def test_below_one_day_is_refused(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    """The minimum retention is one day."""
    monkeypatch.setenv("MENAGERIST_DELETED_RETENTION_DAYS", value)
    with pytest.raises(ValidationError):
        RetentionSettings()


def test_one_day_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    """One day is the smallest allowed retention."""
    monkeypatch.setenv("MENAGERIST_DELETED_RETENTION_DAYS", "1")
    assert RetentionSettings().deleted_retention_days == 1
