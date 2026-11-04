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
    date: dict[str, int],
    *,
    prerelease: bool = False,
    stable: bool = False,
    prefix: str = "v",
) -> dict[str, Any]:
    """The part of ``calver-scm --json parse`` output the script reads."""
    return {
        "valid": True,
        "input": prefix + version,
        "version": version,
        "tag_prefix": prefix,
        "is_prerelease": prerelease,
        "stable": stable,
        "date": date,
    }


MONTH = {"YYYY": 2026, "MM": 11}
OCTOBER = {"YYYY": 2026, "MM": 10}


@pytest.mark.parametrize(
    ("version", "date", "expected"),
    [
        ("0.2026.11.0", MONTH, ["0.2026.11", "0.2026", "latest"]),
        ("0.2026.11.3", MONTH, ["0.2026.11", "0.2026", "latest"]),
        # A hotfix is the newest of its month, so it moves the same tags.
        ("0.2026.11.0.post1", MONTH, ["0.2026.11", "0.2026", "latest"]),
        (
            "0.2026.11.20.1",
            {"YYYY": 2026, "MM": 11, "DD": 20},
            ["0.2026.11.20", "0.2026.11", "0.2026", "latest"],
        ),
        ("0.2026.7", {"YYYY": 2026}, ["0.2026", "latest"]),
    ],
)
def test_the_first_release_moves_every_tag(
    version: str, date: dict[str, int], expected: list[str]
) -> None:
    """With nothing else published, a release is the newest in every scope."""
    assert image_tags.plan(_parsed(version, date), []) == (expected, [])


def test_a_stable_scheme_has_no_zero_prefix() -> None:
    """The 0. marks an unstable scheme, so a stable one has none."""
    parsed = _parsed("2026.11.0", MONTH, stable=True)
    assert image_tags.plan(parsed, []) == (["2026.11", "2026", "latest"], [])


def test_a_release_newer_than_the_rest_moves_every_tag() -> None:
    """Older releases, in the month, the year or earlier, hold nothing back."""
    released = ["v0.2026.11.0", "v0.2026.10.2", "v0.2025.12.0"]
    parsed = _parsed("0.2026.11.0.post1", MONTH)
    assert image_tags.plan(parsed, released) == (["0.2026.11", "0.2026", "latest"], [])


def test_a_hotfix_for_an_older_month_moves_only_its_month() -> None:
    """It is the newest of October, but not of the year or overall."""
    released = ["v0.2026.10.0", "v0.2026.11.0"]
    parsed = _parsed("0.2026.10.0.post1", OCTOBER)
    assert image_tags.plan(parsed, released) == (["0.2026.10"], ["0.2026", "latest"])


def test_a_hotfix_for_an_older_patch_moves_nothing() -> None:
    """A later patch in the same month already covers the month, year and latest."""
    released = ["v0.2026.11.0", "v0.2026.11.1"]
    parsed = _parsed("0.2026.11.0.post1", MONTH)
    assert image_tags.plan(parsed, released) == ([], ["0.2026.11", "0.2026", "latest"])


def test_a_release_already_published_does_not_hold_itself_back() -> None:
    """Publish runs after the release exists, so it is in its own list."""
    released = ["v0.2026.11.0", "v0.2026.11.0.post1"]
    parsed = _parsed("0.2026.11.0.post1", MONTH)
    assert image_tags.plan(parsed, released) == (["0.2026.11", "0.2026", "latest"], [])


def test_other_years_do_not_share_a_scope() -> None:
    """A newer 2027 release leaves the 2026 month and year tags to a 2026 hotfix."""
    released = ["v0.2027.1.0"]
    parsed = _parsed("0.2026.11.0.post1", MONTH)
    assert image_tags.plan(parsed, released) == (["0.2026.11", "0.2026"], ["latest"])


def test_a_year_is_not_a_prefix_of_a_longer_year() -> None:
    """Scope matching is by whole component, so 0.20261 is not in 0.2026."""
    released = ["v0.20261.1.0"]
    parsed = _parsed("0.2026.11.0", MONTH)
    assert image_tags.plan(parsed, released) == (["0.2026.11", "0.2026"], ["latest"])


def test_tags_that_are_not_versions_are_ignored() -> None:
    """A stray release name must not stop a release publishing."""
    parsed = _parsed("0.2026.11.0", MONTH)
    assert image_tags.plan(parsed, ["nightly", "v0.2026.11.0"]) == (
        ["0.2026.11", "0.2026", "latest"],
        [],
    )


def test_a_tag_prefix_is_removed_before_comparing() -> None:
    """Releases are tagged with the project's prefix; versions are compared bare."""
    parsed = _parsed("0.2026.11.0", MONTH, prefix="r")
    assert image_tags.plan(parsed, ["r0.2026.12.0"]) == (
        ["0.2026.11"],
        ["0.2026", "latest"],
    )


def test_a_prerelease_moves_nothing() -> None:
    """A release candidate must not move a tag that deployments follow."""
    parsed = _parsed("0.2026.11.0rc1", MONTH, prerelease=True)
    assert image_tags.plan(parsed, []) == ([], [])


def test_an_invalid_tag_moves_nothing() -> None:
    """A tag calver-scm rejects has no parts to build tags from."""
    parsed = {"valid": False, "input": "main", "errors": [{"code": "x"}]}
    assert image_tags.plan(parsed, []) == ([], [])


def test_writes_the_tags_preview_and_held_tags(tmp_path: Path) -> None:
    """Tags go out as type=raw lines; people get the preview and what was held."""
    released = tmp_path / "released.txt"
    released.write_text("v0.2026.10.0\nv0.2026.11.0\n", encoding="utf-8")
    output = tmp_path / "output"
    parsed = json.dumps(_parsed("0.2026.10.0.post1", OCTOBER))
    env = {"GITHUB_OUTPUT": str(output), "RELEASED_FILE": str(released)}
    assert image_tags.main(parsed, env) == 0
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
    parsed = json.dumps(_parsed("0.2026.11.0rc1", MONTH, prerelease=True))
    assert image_tags.main(parsed, {"GITHUB_OUTPUT": str(output)}) == 0
    assert output.read_text(encoding="utf-8") == (
        "tags<<EOF\n\nEOF\npreview=0.2026.11.0rc1\nheld=\n"
    )


def test_runs_without_a_github_output_or_release_list() -> None:
    """Running outside Actions only prints, and an absent list holds nothing back."""
    parsed = json.dumps(_parsed("0.2026.11.0", MONTH))
    assert image_tags.main(parsed, {}) == 0
