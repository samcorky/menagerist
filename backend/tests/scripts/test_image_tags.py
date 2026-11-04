"""Tests for scripts/image_tags.py: the version tags a release moves."""

import importlib.util
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from types import ModuleType

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "image_tags.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("image_tags_script", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["image_tags_script"] = module
    spec.loader.exec_module(module)
    return module


image_tags = _load()


def _parsed(
    version: str,
    newest: dict[str, bool],
    *,
    prerelease: bool = False,
    stable: bool = False,
) -> dict[str, Any]:
    """The part of ``calver-scm parse --against-repo`` JSON the script reads."""
    return {
        "valid": True,
        "input": "v" + version,
        "version": version,
        "is_prerelease": prerelease,
        "stable": stable,
        "newest": newest,
    }


ALL_NEWEST = {"2026.11": True, "2026": True, "all": True}


@pytest.mark.parametrize(
    ("newest", "expected"),
    [
        (ALL_NEWEST, ["0.2026.11", "0.2026", "latest"]),
        (
            {"2026.11.20": True, "2026.11": True, "2026": True, "all": True},
            ["0.2026.11.20", "0.2026.11", "0.2026", "latest"],
        ),
        ({"2026": True, "all": True}, ["0.2026", "latest"]),
    ],
)
def test_the_newest_release_moves_every_tag(
    newest: dict[str, bool], expected: list[str]
) -> None:
    """When calver-scm finds nothing newer in any scope, every tag moves."""
    assert image_tags.plan(_parsed("0.2026.11.0", newest)) == (expected, [])


def test_a_stable_scheme_has_no_zero_prefix() -> None:
    """The 0. marks an unstable scheme, so a stable one has none."""
    parsed = _parsed("2026.11.0", ALL_NEWEST, stable=True)
    assert image_tags.plan(parsed) == (["2026.11", "2026", "latest"], [])


def test_a_hotfix_for_an_older_month_moves_only_its_month() -> None:
    """It is the newest of October, but not of the year or overall."""
    newest = {"2026.10": True, "2026": False, "all": False}
    parsed = _parsed("0.2026.10.0.post1", newest)
    assert image_tags.plan(parsed) == (["0.2026.10"], ["0.2026", "latest"])


def test_a_hotfix_for_an_older_patch_moves_nothing() -> None:
    """A later patch in the same month already covers the month, year and latest."""
    newest = {"2026.11": False, "2026": False, "all": False}
    parsed = _parsed("0.2026.11.0.post1", newest)
    assert image_tags.plan(parsed) == ([], ["0.2026.11", "0.2026", "latest"])


def test_a_prerelease_moves_nothing() -> None:
    """A release candidate must not move a tag that deployments follow."""
    parsed = _parsed("0.2026.11.0rc1", ALL_NEWEST, prerelease=True)
    assert image_tags.plan(parsed) == ([], [])


def test_an_invalid_tag_moves_nothing() -> None:
    """A tag calver-scm rejects has no parts to build tags from."""
    parsed = {"valid": False, "input": "main", "errors": [{"code": "x"}]}
    assert image_tags.plan(parsed) == ([], [])


def test_writes_the_tags_preview_and_held_tags(tmp_path: Path) -> None:
    """Tags go out as type=raw lines; people get the preview and what was held."""
    output = tmp_path / "output"
    newest = {"2026.10": True, "2026": False, "all": False}
    parsed = json.dumps(_parsed("0.2026.10.0.post1", newest))
    assert image_tags.main(parsed, {"GITHUB_OUTPUT": str(output)}) == 0
    assert output.read_text(encoding="utf-8").splitlines() == [
        "tags<<EOF",
        "type=raw,value=0.2026.10",
        "EOF",
        "preview=0.2026.10.0.post1, 0.2026.10",
        "held=0.2026, latest",
    ]


def test_a_prerelease_previews_only_its_own_tag(tmp_path: Path) -> None:
    """A candidate publishes its version alone."""
    output = tmp_path / "output"
    parsed = json.dumps(_parsed("0.2026.11.0rc1", ALL_NEWEST, prerelease=True))
    assert image_tags.main(parsed, {"GITHUB_OUTPUT": str(output)}) == 0
    assert output.read_text(encoding="utf-8") == (
        "tags<<EOF\n\nEOF\npreview=0.2026.11.0rc1\nheld=\n"
    )


def test_runs_without_a_github_output() -> None:
    """Running outside Actions only prints."""
    parsed = json.dumps(_parsed("0.2026.11.0", ALL_NEWEST))
    assert image_tags.main(parsed, {}) == 0
