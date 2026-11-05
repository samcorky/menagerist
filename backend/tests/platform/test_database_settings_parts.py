"""The database connection can be given as parts or as one URL."""

from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError
from sqlalchemy.engine import make_url
from structlog.testing import capture_logs

from app.platform.alembic_runner import build_config
from app.platform.config import DatabaseSettings, get_database_settings
from app.platform.config.dsn import mask_dsn

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

DEFAULT_URL = "postgresql+asyncpg://menagerist:menagerist@localhost:5432/menagerist"
TRICKY = "p@ss/w:rd#?%"
URL = "postgresql+asyncpg://other:pw@elsewhere:6543/otherdb?ssl=require"


def test_defaults_match_the_previous_default_url() -> None:
    """With nothing set, the composed URL is the one the setting always had."""
    assert str(DatabaseSettings().url) == DEFAULT_URL


def test_url_is_composed_from_the_parts() -> None:
    """Each part lands in its place in the URL."""
    settings = DatabaseSettings(
        host="postgres", port=6000, user="app", password=TRICKY, name="menagerie"
    )
    parsed = make_url(str(settings.url))
    assert parsed.drivername == "postgresql+asyncpg"
    assert (parsed.host, parsed.port, parsed.username, parsed.database) == (
        "postgres",
        6000,
        "app",
        "menagerie",
    )


def test_password_is_percent_encoded_and_round_trips() -> None:
    """Characters that mean something in a URL survive being in the password."""
    settings = DatabaseSettings(password=TRICKY)
    assert TRICKY not in str(settings.url)
    assert make_url(str(settings.url)).password == TRICKY


def test_url_wins_over_the_parts() -> None:
    """A full URL replaces every part, so existing deployments are unchanged."""
    settings = DatabaseSettings(url=URL, host="ignored", password="ignored")
    assert str(settings.url) == URL


def test_parts_come_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """The parts use the `MENAGERIST_DATABASE_` prefix."""
    monkeypatch.setenv("MENAGERIST_DATABASE_HOST", "postgres")
    monkeypatch.setenv("MENAGERIST_DATABASE_PASSWORD", TRICKY)
    parsed = make_url(str(DatabaseSettings().url))
    assert (parsed.host, parsed.password) == ("postgres", TRICKY)


def test_environment_url_wins_over_environment_parts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both forms set in the environment: the URL is used."""
    monkeypatch.setenv("MENAGERIST_DATABASE_URL", URL)
    monkeypatch.setenv("MENAGERIST_DATABASE_HOST", "postgres")
    assert str(DatabaseSettings().url) == URL


def test_password_alone_can_come_from_a_secrets_file(tmp_path: Path) -> None:
    """The other parts stay ordinary settings; only the password is in the file."""
    (tmp_path / "menagerist_database_password").write_text(f"{TRICKY}\n")
    settings = DatabaseSettings(_secrets_dir=tmp_path, host="postgres")
    parsed = make_url(str(settings.url))
    assert (parsed.host, parsed.password) == ("postgres", TRICKY)


def test_composed_url_is_masked_like_a_given_one() -> None:
    """The password stays out of every rendering when it came from the parts."""
    settings = DatabaseSettings(password=TRICKY)
    renderings = [
        repr(settings),
        settings.model_dump_json(),
        str(settings.model_dump()),
    ]
    assert all(TRICKY not in text for text in renderings)
    assert mask_dsn(settings.url) == DEFAULT_URL.replace(":menagerist@", ":***@")


@pytest.mark.parametrize("port", [0, 65536])
def test_port_must_be_a_valid_port(port: int) -> None:
    """An impossible port is refused rather than composed into the URL."""
    with pytest.raises(ValidationError):
        DatabaseSettings(port=port)


def test_url_set_with_parts_warns_naming_the_ignored_parts() -> None:
    """The warning names the parts that lost, and never their values."""
    with capture_logs() as logs:
        DatabaseSettings(url=URL, host="ignored", password=TRICKY)

    assert [(e["event"], e["log_level"], e["ignored"]) for e in logs] == [
        ("database_url_overrides_parts", "warning", ["host", "password"])
    ]
    assert TRICKY not in str(logs)


@pytest.mark.parametrize(
    "settings",
    [lambda: DatabaseSettings(url=URL), lambda: DatabaseSettings(host="postgres")],
)
def test_no_warning_without_both_forms(settings: Callable[[], object]) -> None:
    """The URL alone, or the parts alone, is not a conflict."""
    with capture_logs() as logs:
        settings()
    assert logs == []


def test_alembic_config_keeps_an_encoded_password_literal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ConfigParser reads `%` as interpolation, so the URL is escaped for it."""
    monkeypatch.setenv("MENAGERIST_DATABASE_PASSWORD", TRICKY)
    get_database_settings.cache_clear()
    try:
        url = build_config().get_main_option("sqlalchemy.url")
        assert url == str(get_database_settings().url)
        assert make_url(str(url)).password == TRICKY
    finally:
        get_database_settings.cache_clear()


def test_invalid_part_error_does_not_echo_the_password() -> None:
    """A part the URL refuses is reported without the URL it was composed into."""
    with pytest.raises(ValidationError) as caught:
        DatabaseSettings(host="bad host", password=TRICKY)
    assert TRICKY not in str(caught.value)


def test_pool_defaults_match_the_previous_fixed_sizes() -> None:
    """Nothing set keeps today's pool of 5 with 10 overflow connections."""
    settings = DatabaseSettings()
    assert (settings.pool_size, settings.max_overflow) == (5, 10)


@pytest.mark.parametrize(("pool_size", "max_overflow"), [(0, 10), (-1, 10), (5, -1)])
def test_pool_bounds_are_enforced(pool_size: int, max_overflow: int) -> None:
    """A pool needs a connection; overflow may be none but not negative."""
    with pytest.raises(ValidationError):
        DatabaseSettings(pool_size=pool_size, max_overflow=max_overflow)


def test_pool_may_have_no_overflow() -> None:
    """Zero overflow caps a process at its pool size."""
    assert DatabaseSettings(max_overflow=0).max_overflow == 0


def test_engine_is_built_with_the_configured_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`get_engine` hands the settings to SQLAlchemy's queue pool."""
    from typing import cast

    from sqlalchemy.pool import QueuePool

    from app.platform.database import get_engine

    monkeypatch.setenv("MENAGERIST_DATABASE_POOL_SIZE", "3")
    monkeypatch.setenv("MENAGERIST_DATABASE_MAX_OVERFLOW", "7")
    get_database_settings.cache_clear()
    get_engine.cache_clear()
    try:
        pool = cast(QueuePool, get_engine().pool)
        assert (pool.size(), pool._max_overflow) == (3, 7)
    finally:
        get_engine.cache_clear()
        get_database_settings.cache_clear()
