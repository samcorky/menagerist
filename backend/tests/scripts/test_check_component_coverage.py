"""Tests for scripts/check_component_coverage.py: the job summary it writes."""

import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types import ModuleType

    import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_component_coverage.py"
RESULTS = [("Domain", 100.0, 100.0), ("Adapters", 71.456, 80.0)]


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_component_coverage", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_component_coverage"] = module
    spec.loader.exec_module(module)
    return module


check = _load()


def test_the_summary_lists_each_component_against_its_target() -> None:
    """Every component gets a row, and one below its target is marked."""
    table = check.summary_markdown(RESULTS)

    assert "| Domain | 100.00% | 100% | Pass |" in table
    assert "| Adapters | 71.46% | 80% | **Below target** |" in table


def test_the_summary_is_appended_when_github_provides_a_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Existing summary content is kept and the table follows it."""
    summary = tmp_path / "summary.md"
    summary.write_text("earlier step\n", encoding="utf-8")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

    check.write_step_summary(RESULTS)

    text = summary.read_text(encoding="utf-8")
    assert text.startswith("earlier step\n")
    assert "### Backend coverage" in text


def test_nothing_is_written_outside_github_actions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without GITHUB_STEP_SUMMARY the script writes no file."""
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.chdir(tmp_path)

    check.write_step_summary(RESULTS)

    assert list(tmp_path.iterdir()) == []


def test_the_comment_file_starts_with_the_marker_and_holds_the_table(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The workflow finds its earlier comment by the marker on the first line."""
    comment = tmp_path / "comment.md"
    monkeypatch.setenv("COMPONENT_COVERAGE_COMMENT", str(comment))

    check.write_comment_file(RESULTS)

    text = comment.read_text(encoding="utf-8")
    assert text.startswith(check.COMMENT_MARKER + "\n")
    assert "| Domain | 100.00% | 100% | Pass |" in text


def test_no_comment_file_is_written_unless_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Locally, where no file is named, nothing is written."""
    monkeypatch.delenv("COMPONENT_COVERAGE_COMMENT", raising=False)
    monkeypatch.chdir(tmp_path)

    check.write_comment_file(RESULTS)

    assert list(tmp_path.iterdir()) == []


LCOV = """TN:
SF:src/lib/a.ts
LF:10
LH:9
end_of_record
SF:src/lib/b.ts
LF:10
LH:5
end_of_record
SF:other/c.ts
LF:100
LH:0
end_of_record
"""


def test_lcov_percent_sums_only_the_files_matching_the_globs() -> None:
    """Lines found and hit are added across matching files, ignoring the rest."""
    assert check.lcov_percent(LCOV, ["src/**"]) == 70.0
    assert check.lcov_percent(LCOV, ["nothing/**"]) == 0.0


def test_frontend_components_are_told_apart_by_their_paths() -> None:
    """Components under frontend/ are measured from lcov, the rest from coverage.py."""
    components = {c["component_id"]: c for c in check.load_components()}

    assert check.is_frontend(components["frontend"])
    assert not check.is_frontend(components["domain"])
    assert check.frontend_paths(components["frontend"]) == ["src/**"]


def test_the_frontend_component_has_a_target_that_the_lcov_report_is_held_to() -> None:
    """The target comes from codecov.yml, and a shortfall is reported by name."""
    components = [c for c in check.load_components() if check.is_frontend(c)]

    results = check.collect_frontend_results(components, LCOV)

    assert [(name, round(pct)) for name, pct, _ in results] == [("Frontend", 70)]
    assert results[0][2] == check.component_target(components[0])
    assert check.component_target(components[0]) is not None


def test_ports_alone_are_tracked_without_a_floor() -> None:
    """Auto targets are skipped, so ports never fails the check."""
    components = {c["component_id"]: c for c in check.load_components()}

    assert check.component_target(components["ports"]) is None
    assert check.component_target(components["domain"]) == 100.0
