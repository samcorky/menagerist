"""Every setting can be supplied by a `/run/secrets/<VARIABLE>` file."""

import warnings
from typing import TYPE_CHECKING

import pytest

from app.platform.config import MenageristBaseSettings

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.fast


class Widget(MenageristBaseSettings, group="widget"):
    """A small group, standing for any settings class."""

    password: str | None = None
    size: int = 1


@pytest.fixture
def secrets_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point the default secrets directory at an empty temporary one."""
    monkeypatch.delenv("MENAGERIST_WIDGET_PASSWORD", raising=False)
    monkeypatch.delenv("MENAGERIST_WIDGET_SIZE", raising=False)
    monkeypatch.setattr("app.platform.config._base.SECRETS_DIR", tmp_path)
    return tmp_path


def test_a_setting_supplied_only_as_a_secret_file_is_read(secrets_dir: Path) -> None:
    """The file is named after the environment variable, in either case."""
    (secrets_dir / "MENAGERIST_WIDGET_PASSWORD").write_text("hunter2\n")
    (secrets_dir / "menagerist_widget_size").write_text("7")

    settings = Widget()

    assert settings.password == "hunter2"
    assert settings.size == 7
    assert settings.source_of("password") == "secret_file"
    assert settings.is_pinned("size")


def test_the_environment_variable_wins_over_the_secret_file(
    secrets_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With both set, the variable is used."""
    (secrets_dir / "MENAGERIST_WIDGET_PASSWORD").write_text("from-file")
    monkeypatch.setenv("MENAGERIST_WIDGET_PASSWORD", "from-env")

    settings = Widget()

    assert settings.password == "from-env"
    assert settings.source_of("password") == "env"


def test_a_missing_secrets_directory_is_not_an_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A host without Docker secrets loads quietly from the defaults."""
    monkeypatch.delenv("MENAGERIST_WIDGET_PASSWORD", raising=False)
    monkeypatch.setattr("app.platform.config._base.SECRETS_DIR", tmp_path / "absent")

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        settings = Widget()

    assert settings.password is None
    assert settings.source_of("password") == "default"
