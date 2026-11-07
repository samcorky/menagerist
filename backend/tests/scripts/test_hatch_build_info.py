"""Tests for backend/scripts/hatch_build_info.py: where each build value comes from."""

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "hatch_build_info.py"
DEFAULT_URL = "https://github.com/samcorky/menagerist"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("hatch_build_info_script", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["hatch_build_info_script"] = module
    spec.loader.exec_module(module)
    return module


hatch_build_info = _load()


def _hook(
    monkeypatch: pytest.MonkeyPatch, root: Path, urls: dict[str, str] | None = None
) -> Any:  # noqa: ANN401
    """Build a hook without hatchling's config plumbing, with the given metadata."""
    monkeypatch.setattr(
        hatch_build_info.BuildInfoHook, "root", property(lambda _self: str(root))
    )
    metadata = SimpleNamespace(core=SimpleNamespace(urls=urls or {}))
    monkeypatch.setattr(
        hatch_build_info.BuildInfoHook, "metadata", property(lambda _self: metadata)
    )
    return hatch_build_info.BuildInfoHook.__new__(hatch_build_info.BuildInfoHook)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "MENAGERIST_BUILD_COMMIT_SHA",
        "MENAGERIST_BUILD_BRANCH",
        "MENAGERIST_BUILD_DIRTY",
        "MENAGERIST_BUILD_REPOSITORY_URL",
    ):
        monkeypatch.delenv(name, raising=False)


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A git repository with one commit on the ``feature`` branch."""
    _git(tmp_path, "init", "-b", "feature")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "T")
    (tmp_path / "f").write_text("x")
    _git(tmp_path, "add", "f")
    _git(tmp_path, "commit", "-m", "init")
    return tmp_path


def test_repository_url_prefers_the_explicit_value(
    monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    """Repository url prefers the explicit value."""
    _git(repo, "remote", "add", "origin", "git@example.com:remote/repo.git")
    monkeypatch.setenv("MENAGERIST_BUILD_REPOSITORY_URL", "git@fork.test:me/fork.git")
    hook = _hook(monkeypatch, repo, {"Repository": DEFAULT_URL})

    assert hook._repository_url() == "https://fork.test/me/fork"


def test_repository_url_uses_the_git_remote_over_the_default(
    monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    """Repository url uses the git remote over the default."""
    _git(repo, "remote", "add", "origin", "git@example.com:remote/repo.git")
    hook = _hook(monkeypatch, repo, {"Repository": DEFAULT_URL})

    assert hook._repository_url() == "https://example.com/remote/repo"


def test_repository_url_falls_back_to_the_declared_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Repository url falls back to the declared default."""
    # No repository at all, as in a build container without the mount.
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "missing"))
    hook = _hook(monkeypatch, tmp_path, {"Repository": f"{DEFAULT_URL}.git"})

    assert hook._repository_url() == DEFAULT_URL


def test_repository_url_is_none_without_any_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Repository url is none without any source."""
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "missing"))
    hook = _hook(monkeypatch, tmp_path)

    assert hook._repository_url() is None


def test_commit_sha_and_branch_prefer_the_explicit_values(
    monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    """Commit sha and branch prefer the explicit values."""
    monkeypatch.setenv("MENAGERIST_BUILD_COMMIT_SHA", "abc1234")
    monkeypatch.setenv("MENAGERIST_BUILD_BRANCH", "release")
    hook = _hook(monkeypatch, repo)

    assert hook._commit_sha() == "abc1234"
    assert hook._branch() == "release"


def test_commit_sha_and_branch_fall_back_to_git(
    monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    """Commit sha and branch fall back to git."""
    hook = _hook(monkeypatch, repo)

    assert len(hook._commit_sha() or "") == 40
    assert hook._branch() == "feature"
    assert hook._is_dirty() is False


def test_values_are_none_without_repository_metadata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Values are none without repository metadata."""
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "missing"))
    hook = _hook(monkeypatch, tmp_path)

    assert hook._commit_sha() is None
    assert hook._branch() is None
    assert hook._is_dirty() is None
