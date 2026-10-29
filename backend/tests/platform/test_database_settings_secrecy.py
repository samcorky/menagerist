"""The database password never reaches reprs, dumps, logs or error messages."""

import inspect
import pkgutil
from typing import TYPE_CHECKING

import pytest
from pydantic import SecretStr, ValidationError
from structlog.testing import capture_logs

import app.platform.config as config
from app.entrypoints.api import startup
from app.platform.config import INSTANCE_SETTINGS, DatabaseSettings
from app.platform.config.dsn import mask_dsn

if TYPE_CHECKING:
    from collections.abc import Callable

    from pydantic_settings import BaseSettings

PASSWORD = "s3cr3t-p4ss"
DSN = f"postgresql+asyncpg://menagerist:{PASSWORD}@db:5432/menagerist"
CLI_ONLY = {"get_identity_cli_settings"}


@pytest.fixture
def settings() -> DatabaseSettings:
    """Settings built from a DSN with a known password."""
    return DatabaseSettings(url=DSN)


def test_password_is_absent_from_every_rendering(settings: DatabaseSettings) -> None:
    """repr, str and both JSON dumps mask the password."""
    renderings = [
        repr(settings),
        str(settings),
        settings.model_dump_json(),
        str(settings.model_dump(mode="json")),
    ]
    assert all(PASSWORD not in text for text in renderings)
    assert all("menagerist:***@db" in text for text in renderings)


def test_attribute_access_still_returns_the_real_dsn(
    settings: DatabaseSettings,
) -> None:
    """Connecting needs the real value."""
    assert PASSWORD in str(settings.url)


def test_invalid_dsn_error_does_not_echo_the_password() -> None:
    """A validation error hides the offending input."""
    bad = f"mysql://menagerist:{PASSWORD}@db/menagerist"
    with pytest.raises(ValidationError) as caught:
        DatabaseSettings(url=bad)
    assert PASSWORD not in str(caught.value)


def test_startup_log_does_not_contain_the_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The one-event-per-group log carries the masked DSN only."""
    monkeypatch.setenv("MENAGERIST_DATABASE_URL", DSN)
    config.get_database_settings.cache_clear()
    try:
        with capture_logs() as logs:
            startup.log_instance_settings()
    finally:
        config.get_database_settings.cache_clear()

    assert PASSWORD not in str(logs)
    assert [entry["group"] for entry in logs] == [
        "ApiSettings",
        "BackupSettings",
        "DatabaseSettings",
        "IdentitySettings",
        "LoggingSettings",
        "MediaSettings",
        "ReleaseSettings",
        "RetentionSettings",
        "SchedulerSettings",
    ]
    assert all(entry["log_level"] == "info" for entry in logs)


def test_log_instance_settings_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failing getter is skipped; the others still log."""

    def broken() -> BaseSettings:
        raise RuntimeError("boom")

    monkeypatch.setattr(startup, "INSTANCE_SETTINGS", (broken, *INSTANCE_SETTINGS))
    with capture_logs() as logs:
        startup.log_instance_settings()

    assert len([e for e in logs if e["log_level"] == "info"]) == len(INSTANCE_SETTINGS)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (DSN, "postgresql+asyncpg://menagerist:***@db:5432/menagerist"),
        ("postgresql://u@h/d", "postgresql://u@h/d"),
        ("postgresql://u:pw@h/d?password=pw&sslmode=require", None),
        ("not a url", "<unparseable database url>"),
    ],
)
def test_mask_dsn(url: str, expected: str | None) -> None:
    """The password goes; the rest stays readable."""
    masked = mask_dsn(url)
    assert "pw" not in masked.replace("password", "")
    if expected is not None:
        assert masked == expected
    else:
        assert "sslmode=require" in masked


def _all_settings_classes() -> list[type[BaseSettings]]:
    from pydantic_settings import BaseSettings

    classes: list[type[BaseSettings]] = []
    for info in pkgutil.iter_modules(config.__path__):
        module = __import__(f"app.platform.config.{info.name}", fromlist=["x"])
        classes.extend(
            cls
            for _, cls in inspect.getmembers(module, inspect.isclass)
            if issubclass(cls, BaseSettings)
            and cls is not BaseSettings
            and cls.__module__ == module.__name__
            and cls.__name__ != "MenageristBaseSettings"
        )
    return classes


def test_no_secret_named_field_has_a_plain_type() -> None:
    """Fields named like secrets (`..._password`, `..._token`) must be SecretStr."""
    markers = ("password", "secret", "token", "key")
    offenders = [
        f"{cls.__name__}.{name}"
        for cls in _all_settings_classes()
        for name, field in cls.model_fields.items()
        if name.rsplit("_", 1)[-1] in markers
        and SecretStr not in _flatten(field.annotation)
    ]
    assert offenders == []


def _flatten(annotation: object) -> set[object]:
    args = getattr(annotation, "__args__", ())
    found: set[object] = {annotation}
    for arg in args:
        found |= _flatten(arg)
    return found


def test_every_settings_getter_is_in_instance_settings() -> None:
    """A new settings group must be logged (or explicitly CLI-only)."""
    getters: list[Callable[[], BaseSettings]] = [
        getattr(config, name)
        for name in dir(config)
        if name.startswith("get_") and name.endswith("_settings")
    ]
    missing = [g.__name__ for g in getters if g not in INSTANCE_SETTINGS]
    assert sorted(missing) == sorted(CLI_ONLY)
