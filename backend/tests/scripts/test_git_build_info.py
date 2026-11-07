"""Tests for scripts/git_build_info.py: git values the host passes to the build."""

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "git_build_info.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("git_build_info_script", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["git_build_info_script"] = module
    spec.loader.exec_module(module)
    return module


git_build_info = _load()


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A git repository with one commit, set as the working directory."""
    _git(tmp_path, "init", "-b", "feature")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "T")
    (tmp_path / "f").write_text("x")
    _git(tmp_path, "add", "f")
    _git(tmp_path, "commit", "-m", "init")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_reports_commit_branch_and_a_clean_tree(repo: Path) -> None:
    """Reports commit branch and a clean tree."""
    assert len(git_build_info.query("commit")) == 40
    assert git_build_info.query("branch") == "feature"
    assert git_build_info.query("dirty") == "false"
    assert git_build_info.query("repository-url") == ""


def test_reports_the_remote_and_uncommitted_changes(repo: Path) -> None:
    """Reports the remote and uncommitted changes."""
    _git(repo, "remote", "add", "origin", "https://example.com/o/r.git")
    (repo / "f").write_text("changed")

    assert git_build_info.query("repository-url") == "https://example.com/o/r.git"
    assert git_build_info.query("dirty") == "true"


def test_reports_nothing_outside_a_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reports nothing outside a repository."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "missing"))

    assert git_build_info.query("commit") == ""


def test_main_prints_the_field_and_rejects_unknown_ones(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Main prints the field and rejects unknown ones."""
    assert git_build_info.main(["branch"]) == 0
    assert capsys.readouterr().out == "feature\n"
    with pytest.raises(SystemExit) as exit_info:
        git_build_info.main(["nope"])
    assert exit_info.value.code == 2
