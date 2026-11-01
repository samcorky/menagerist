"""Deployment settings for the web server process."""

import pytest
from pydantic import ValidationError

from app.platform.config import INSTANCE_SETTINGS, get_server_settings
from app.platform.config.server import ServerSettings


def test_defaults_are_auto_workers_and_container_detection() -> None:
    """Nothing set: pick the worker count automatically and detect a container."""
    settings = ServerSettings()

    assert settings.workers == "auto"
    assert settings.in_container is None


def test_the_variables_use_the_server_group() -> None:
    """Named like every other grouped setting, not a loose top-level name."""
    assert ServerSettings.model_config["env_prefix"] == "MENAGERIST_SERVER_"


@pytest.mark.parametrize(("raw", "expected"), [("auto", "auto"), ("1", 1), ("16", 16)])
def test_workers_reads_auto_or_a_number(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: object
) -> None:
    """The environment value becomes the word `auto` or an integer."""
    monkeypatch.setenv("MENAGERIST_SERVER_WORKERS", raw)

    assert ServerSettings().workers == expected


@pytest.mark.parametrize("raw", ["0", "17", "-2", "four", "2.5"])
def test_a_bad_worker_count_stops_start_up(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    """A wrong value is a settings error that names the variable."""
    monkeypatch.setenv("MENAGERIST_SERVER_WORKERS", raw)

    with pytest.raises(ValidationError, match="workers"):
        ServerSettings()


@pytest.mark.parametrize(
    ("raw", "expected"), [("1", True), ("true", True), ("0", False), ("false", False)]
)
def test_in_container_can_be_forced_either_way(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: bool
) -> None:
    """The image sets it to 1; a host with stray markers can set it to 0."""
    monkeypatch.setenv("MENAGERIST_SERVER_IN_CONTAINER", raw)

    assert ServerSettings().in_container is expected


def test_the_cached_getter_is_registered_with_the_instance_settings() -> None:
    """Listed at start-up and in the settings catalogue like its neighbours."""
    assert get_server_settings in INSTANCE_SETTINGS
    get_server_settings.cache_clear()
    assert get_server_settings() is get_server_settings()
