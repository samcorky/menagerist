"""Tests for scripts/image_tags.py: the partial Docker tags a release moves."""

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
    tag: str,
    date: dict[str, int],
    *,
    prerelease: bool = False,
    stable: bool = False,
) -> dict[str, Any]:
    """The part of ``calver-scm --json parse`` output the script reads."""
    return {
        "valid": True,
        "input": tag,
        "version": tag.removeprefix("v"),
        "is_prerelease": prerelease,
        "stable": stable,
        "date": date,
    }


MONTH = {"YYYY": 2026, "MM": 11}


@pytest.mark.parametrize(
    ("tag", "date", "expected"),
    [
        ("v0.2026.11.0", MONTH, ["0.2026.11", "0.2026"]),
        ("v0.2026.11.3", MONTH, ["0.2026.11", "0.2026"]),
        # A hotfix is the newest of its month, so it moves the partial tags.
        ("v0.2026.11.0.post1", MONTH, ["0.2026.11", "0.2026"]),
        (
            "v0.2026.11.20.1",
            {"YYYY": 2026, "MM": 11, "DD": 20},
            ["0.2026.11.20", "0.2026.11", "0.2026"],
        ),
        ("v0.2026.7", {"YYYY": 2026}, ["0.2026"]),
    ],
)
def test_releases_move_the_period_tags(
    tag: str, date: dict[str, int], expected: list[str]
) -> None:
    """A final or post release moves a tag for each shorter period."""
    assert image_tags.partial_tags(_parsed(tag, date)) == expected


def test_a_stable_scheme_has_no_zero_prefix() -> None:
    """The 0. marks an unstable scheme, so a stable one has none."""
    parsed = _parsed("v2026.11.0", MONTH, stable=True)
    assert image_tags.partial_tags(parsed) == ["2026.11", "2026"]


def test_a_prerelease_moves_nothing() -> None:
    """A release candidate must not move a tag that deployments follow."""
    parsed = _parsed("v0.2026.11.0rc1", MONTH, prerelease=True)
    assert image_tags.partial_tags(parsed) == []


def test_an_invalid_tag_moves_nothing() -> None:
    """A tag calver-scm rejects has no parts to build tags from."""
    parsed = {"valid": False, "input": "main", "errors": [{"code": "x"}]}
    assert image_tags.partial_tags(parsed) == []


def test_a_release_previews_its_version_tags_and_latest() -> None:
    """Show every tag a release publishes, and that it moves latest."""
    parsed = _parsed("v0.2026.11.0.post1", MONTH)
    assert image_tags.preview(parsed) == [
        "0.2026.11.0.post1",
        "0.2026.11",
        "0.2026",
        "latest",
    ]


def test_a_prerelease_previews_only_its_own_tag() -> None:
    """A candidate publishes its version alone, and stays off latest."""
    parsed = _parsed("v0.2026.11.0rc1", MONTH, prerelease=True)
    assert image_tags.preview(parsed) == ["0.2026.11.0rc1"]


def test_an_invalid_tag_previews_nothing() -> None:
    """A tag calver-scm rejects has nothing to show."""
    assert image_tags.preview({"valid": False, "input": "main"}) == []


def test_writes_metadata_action_lines(tmp_path: Path) -> None:
    """The output holds one type=raw line per tag, as a multiline value."""
    output = tmp_path / "output"
    parsed = json.dumps(_parsed("v0.2026.11.0.post1", MONTH))
    assert image_tags.main(parsed, {"GITHUB_OUTPUT": str(output)}) == 0
    assert output.read_text(encoding="utf-8") == (
        "tags<<EOF\ntype=raw,value=0.2026.11\ntype=raw,value=0.2026\nEOF\n"
        + "preview=0.2026.11.0.post1, 0.2026.11, 0.2026, latest\n"
    )


def test_runs_without_a_github_output() -> None:
    """Running outside Actions only prints."""
    parsed = json.dumps(_parsed("v0.2026.11.0", MONTH, prerelease=True))
    assert image_tags.main(parsed, {}) == 0
