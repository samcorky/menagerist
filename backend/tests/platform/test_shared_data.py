"""`shared_data_path` honours `MENAGERIST_SHARED_DIR` and needs no database."""

from typing import TYPE_CHECKING

from app.platform.shared_data import shared_data_path

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_the_environment_override_wins(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The Docker image points the shared data at its own copy."""
    monkeypatch.setenv("MENAGERIST_SHARED_DIR", str(tmp_path))
    assert shared_data_path("contracts/x.json") == tmp_path / "contracts/x.json"


def test_without_the_override_the_repository_shared_directory_is_used(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Running from a checkout resolves `shared/` at the repository root."""
    monkeypatch.delenv("MENAGERIST_SHARED_DIR", raising=False)
    path = shared_data_path("contracts/field-kinds.json")
    assert path.parent.parent.name == "shared"
    assert path.is_file()
