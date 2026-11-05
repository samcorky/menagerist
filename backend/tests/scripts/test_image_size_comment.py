"""Tests for scripts/image_size_comment.py: the image size pull request comment."""

import importlib.util
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types import ModuleType

    import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "image_size_comment.py"
MB = 1_000_000
BASE = {"compressed": 100 * MB, "uncompressed": 300 * MB, "commit": "abcdef1234567"}


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("image_size_comment", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["image_size_comment"] = module
    spec.loader.exec_module(module)
    return module


comment = _load()


def _sizes(compressed: int, uncompressed: int) -> dict[str, int]:
    return {"compressed": compressed * MB, "uncompressed": uncompressed * MB}


def test_a_growth_shows_before_after_and_difference() -> None:
    """The table gives main's size, the new size and the signed change."""
    body = comment.build_comment(_sizes(110, 320), BASE)

    assert body.startswith(comment.MARKER + "\n### Docker image size")
    assert "`main` (`abcdef1`)" in body
    assert "| Compressed | 100.00 MB | 110.00 MB | +10.00 MB (+10.0%) |" in body
    assert "| Uncompressed | 300.00 MB | 320.00 MB | +20.00 MB (+6.7%) |" in body


def test_a_shrink_is_signed_negative() -> None:
    """A smaller image reads as a negative change."""
    body = comment.build_comment(_sizes(90, 300), BASE)

    assert "-10.00 MB (-10.0%)" in body


def test_a_missing_base_commit_still_names_main() -> None:
    """The commit is only a nicety, so a base without one still renders."""
    base = {"compressed": 100 * MB, "uncompressed": 300 * MB}

    assert "| | `main` | This pull request |" in comment.build_comment(
        _sizes(100, 300), base
    )


def test_a_zero_base_omits_the_percentage() -> None:
    """An empty base cannot be divided by, so only the absolute change shows."""
    base = {"compressed": 0, "uncompressed": 0}

    body = comment.build_comment(_sizes(1, 1), base)

    assert "+1.00 MB |" in body
    assert "%" not in body


def test_no_base_shows_the_new_size_alone() -> None:
    """Without a size for main the comment says so rather than inventing one."""
    body = comment.build_comment(_sizes(110, 320), None)

    assert "| Compressed | 110.00 MB |" in body
    assert "The `edge` image could not be pulled" in body
    assert "Change" not in body


def test_main_writes_the_comment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The workflow posts the output file."""
    current = tmp_path / "current.json"
    current.write_text(json.dumps(_sizes(110, 320)), encoding="utf-8")
    base = tmp_path / "base.json"
    base.write_text(json.dumps(BASE), encoding="utf-8")
    out = tmp_path / "out.md"
    argv = ["image_size_comment.py", str(current), "--base", str(base)]
    monkeypatch.setattr(sys, "argv", [*argv, "--output", str(out)])

    assert comment.main() == 0
    assert "+10.00 MB" in out.read_text(encoding="utf-8")


def test_main_copes_with_a_missing_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A base that was never cached is the no-baseline case, not an error."""
    current = tmp_path / "current.json"
    current.write_text(json.dumps(_sizes(110, 320)), encoding="utf-8")
    out = tmp_path / "out.md"
    gone = tmp_path / "gone.json"
    argv = ["image_size_comment.py", str(current), "--base", str(gone)]
    monkeypatch.setattr(sys, "argv", [*argv, "--output", str(out)])

    assert comment.main() == 0
    assert "The `edge` image could not be pulled" in out.read_text(encoding="utf-8")


def test_a_change_that_rounds_to_nothing_is_a_dash() -> None:
    """A change of under 0.005 MB shows as a dash, not +0.00 or -0.00."""
    current = {"compressed": 100 * MB - 1000, "uncompressed": 300 * MB + 1000}

    body = comment.build_comment(current, BASE)

    assert "| Compressed | 100.00 MB | 100.00 MB | - |" in body
    assert "| Uncompressed | 300.00 MB | 300.00 MB | - |" in body
    assert "0.00" not in body.replace("100.00", "").replace("300.00", "")
