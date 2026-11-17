"""Tests for scripts/preview_tag.py: the throwaway tag of a preview image."""

import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "preview_tag.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("preview_tag_script", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["preview_tag_script"] = module
    spec.loader.exec_module(module)
    return module


preview_tag = _load()


def test_a_pull_request_is_tagged_by_its_number() -> None:
    """The number names the tag, so closing the pull request can delete it."""
    assert preview_tag.tag_for(pr_number="566", branch="ci/566-preview") == "pr-566"


@pytest.mark.parametrize(
    ("branch", "tag"),
    [
        ("main", "preview-main"),
        ("ci/566-Preview_Image", "preview-ci-566-preview_image"),
        ("feat//two..dots", "preview-feat-two.dots"),
        ("-leading.", "preview-leading"),
    ],
)
def test_a_manual_run_is_tagged_by_its_branch_made_safe(branch: str, tag: str) -> None:
    """Only tag characters survive; the prefix keeps it off edge and releases."""
    assert preview_tag.tag_for(pr_number="", branch=branch) == tag


def test_a_long_branch_is_cut_to_the_tag_length_limit() -> None:
    """A Docker tag is at most 128 characters."""
    tag = preview_tag.tag_for(pr_number="", branch="x" * 300)

    assert len(tag) == 128
    assert tag.startswith("preview-x")


def test_a_branch_with_nothing_usable_is_refused() -> None:
    """A bare prefix would be shared by every such branch."""
    with pytest.raises(ValueError, match="branch"):
        preview_tag.tag_for(pr_number="", branch="///")


def test_main_writes_the_tag_to_the_step_outputs(tmp_path: Path) -> None:
    """The workflow reads ``tag`` from GITHUB_OUTPUT."""
    output = tmp_path / "output"

    status = preview_tag.main(
        {"PR_NUMBER": "12", "BRANCH": "anything", "GITHUB_OUTPUT": str(output)}
    )

    assert status == 0
    assert output.read_text(encoding="utf-8") == "tag=pr-12\n"
