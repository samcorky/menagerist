"""The database connection can be given as parts or as one URL."""

from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError
from sqlalchemy.engine import make_url
from structlog.testing import capture_logs

from app.platform.config import DatabaseSettings
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
