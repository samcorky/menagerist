"""Tests for scripts/coverage_comment.py: the combined pull request comment."""

import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types import ModuleType

    import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "coverage_comment.py"
BACKEND = "<!-- component-coverage -->\n### Backend coverage\n\n| Component |\n"
FRONTEND = "<!-- component-coverage -->\n### Frontend coverage\n\n| Component |\n"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("coverage_comment", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["coverage_comment"] = module
    spec.loader.exec_module(module)
    return module


comment = _load()


def test_the_tables_share_one_marker_in_order() -> None:
    """Each script's own marker is dropped, leaving exactly one at the top."""
    body = comment.build_comment([BACKEND, FRONTEND])

    assert body is not None
    assert body.startswith(comment.MARKER + "\n### Backend coverage")
    assert body.count(comment.MARKER) == 1
    assert body.index("### Backend") < body.index("### Frontend")


def test_no_tables_means_no_comment() -> None:
    """With nothing to show there is nothing to post."""
    assert comment.build_comment([]) is None


def test_main_joins_the_files_that_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pull request that skipped one job still gets the other table."""
    frontend = tmp_path / "frontend.md"
    frontend.write_text(FRONTEND, encoding="utf-8")
    out = tmp_path / "out.md"
    argv = ["coverage_comment.py", str(tmp_path / "missing.md"), str(frontend)]
    monkeypatch.setattr(sys, "argv", [*argv, "--output", str(out)])

    assert comment.main() == 0
    text = out.read_text(encoding="utf-8")
    assert "### Frontend coverage" in text
    assert "### Backend coverage" not in text


def test_main_writes_nothing_without_tables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No table files means no output file."""
    out = tmp_path / "out.md"
    argv = ["coverage_comment.py", str(tmp_path / "missing.md"), "--output", str(out)]
    monkeypatch.setattr(sys, "argv", argv)

    assert comment.main() == 0
    assert not out.exists()


def _with_total(table: str, side: str, hit: int, found: int) -> str:
    return table + f"\n<!-- coverage-total {side} {hit} {found} -->\n"


def test_two_sides_get_a_total_weighted_by_lines() -> None:
    """900/1000 and 50/100 combine to 950/1100, not the average of 90% and 50%."""
    body = comment.build_comment(
        [
            _with_total(BACKEND, "backend", 900, 1000),
            _with_total(FRONTEND, "frontend", 50, 100),
        ]
    )

    assert body is not None
    assert "**Total: 86.36%** (backend 90.00%, frontend 50.00%)" in body
    assert body.index("**Total") < body.index("### Backend")
    assert "coverage-total" not in body


def test_a_lone_side_has_no_combined_line() -> None:
    """A pull request that skipped a job shows only the side that ran."""
    body = comment.build_comment([_with_total(BACKEND, "backend", 9, 10)])

    assert body is not None
    assert "Total" not in body
    assert "coverage-total" not in body


def test_tables_without_counts_still_post() -> None:
    """Older artifacts, or a side with nothing measured, do not break the comment."""
    assert "Total" not in (comment.build_comment([BACKEND, FRONTEND]) or "")
    zero = [
        _with_total(BACKEND, "backend", 0, 0),
        _with_total(FRONTEND, "frontend", 0, 0),
    ]
    assert "Total" not in (comment.build_comment(zero) or "")
