"""Tests for scripts/ci_changes.py: which CI jobs a set of changed files needs."""

import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "ci_changes.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("ci_changes_script", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["ci_changes_script"] = module
    spec.loader.exec_module(module)
    return module


ci_changes = _load()

NOTHING = {"backend": False, "frontend": False, "e2e": False, "image": False}
EVERYTHING = {"backend": True, "frontend": True, "e2e": True, "image": True}


@pytest.mark.parametrize(
    "files",
    [
        ["README.md"],
        ["docs/DECISIONS.md", "docs/DEPLOYING.md"],
        [".github/renovate.json"],
        [".github/ISSUE_TEMPLATE/bug_report.yml", "SECURITY.md"],
        [
            ".github/labeller.yml",
            ".github/release.yml",
            ".github/workflows/autofix.yml",
        ],
        ["frontend/README.md", "backend/README.md"],
        [".pre-commit-config.yaml", "backend/.pre-commit-config.yaml"],
    ],
)
def test_documentation_and_housekeeping_run_nothing(files: list[str]) -> None:
    """Files no test or build reads need no job."""
    assert ci_changes.classify(files) == NOTHING


def test_a_frontend_only_change_skips_the_backend_jobs() -> None:
    """Frontend code runs the frontend, e2e and image jobs, not mypy or coverage."""
    assert ci_changes.classify(["frontend/src/lib/api/client.ts"]) == {
        "backend": False,
        "frontend": True,
        "e2e": True,
        "image": True,
    }


@pytest.mark.parametrize(
    "path",
    ["backend/src/app/main.py", "uv.lock", "pyproject.toml", "scripts/e2e.py"],
)
def test_a_backend_change_also_runs_the_frontend(path: str) -> None:
    """The frontend checks itself against the backend's schema and example packs."""
    assert ci_changes.classify([path]) == EVERYTHING


def test_shared_contracts_run_both_sides() -> None:
    """Both stacks read shared/contracts."""
    assert ci_changes.classify(["shared/contracts/cron-conformance.json"]) == EVERYTHING


def test_an_image_only_change_runs_only_the_image() -> None:
    """The Dockerfile changes the image and nothing the tests run against."""
    assert ci_changes.classify(["Dockerfile"]) == {
        "backend": False,
        "frontend": False,
        "e2e": False,
        "image": True,
    }


def test_compose_changes_run_the_image_and_end_to_end() -> None:
    """The end-to-end suite and the smoke test both use the Compose files."""
    assert ci_changes.classify(["compose.e2e.yaml"]) == {
        "backend": False,
        "frontend": False,
        "e2e": True,
        "image": True,
    }


@pytest.mark.parametrize(
    "path",
    [
        ".github/workflows/ci.yml",
        ".github/workflows/build.yml",
        ".github/actions/postgres-image/action.yml",
    ],
)
def test_changing_the_pipeline_runs_everything(path: str) -> None:
    """A change to CI itself is tested by CI."""
    assert ci_changes.classify([path]) == EVERYTHING


def test_an_unrecognised_file_runs_everything() -> None:
    """The safe default for anything the rules do not know."""
    assert ci_changes.classify(["something/new.txt"]) == EVERYTHING


def test_markdown_inside_a_source_tree_is_code() -> None:
    """Code could read a Markdown file under src/, so it is not documentation."""
    assert ci_changes.classify(["backend/src/app/help/guide.md"]) == EVERYTHING


def test_documentation_does_not_hide_a_code_change() -> None:
    """One code file is enough to run its jobs, whatever else changed."""
    flags = ci_changes.classify(["README.md", "frontend/src/routes/+page.svelte"])
    assert flags["frontend"] is True
    assert flags["backend"] is False


def test_an_empty_list_runs_everything() -> None:
    """No files is a failure to look, not a reason to skip."""
    assert ci_changes.classify([]) == EVERYTHING


def test_other_events_run_everything() -> None:
    """Pushes to main and manual runs are never skipped."""
    flags, reason = ci_changes.decide({"EVENT_NAME": "push"})
    assert flags == EVERYTHING
    assert "push" in reason


def test_a_listing_failure_runs_everything(monkeypatch: pytest.MonkeyPatch) -> None:
    """If GitHub cannot list the files, nothing is skipped."""
    monkeypatch.setattr(ci_changes, "changed_files", lambda *_: None)
    flags, _ = ci_changes.decide(
        {"EVENT_NAME": "pull_request", "REPOSITORY": "o/r", "PR_NUMBER": "1"}
    )
    assert flags == EVERYTHING


def test_a_full_file_list_runs_everything(monkeypatch: pytest.MonkeyPatch) -> None:
    """GitHub stops listing at 3,000 files, so that many cannot be trusted."""
    monkeypatch.setattr(
        ci_changes,
        "changed_files",
        lambda *_: ["README.md"] * ci_changes.FILE_LIST_LIMIT,
    )
    flags, _ = ci_changes.decide(
        {"EVENT_NAME": "pull_request", "REPOSITORY": "o/r", "PR_NUMBER": "1"}
    )
    assert flags == EVERYTHING


def test_main_writes_the_outputs_and_a_summary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The flags go to GITHUB_OUTPUT and a table to the job summary."""
    monkeypatch.setattr(ci_changes, "changed_files", lambda *_: ["README.md"])
    output = tmp_path / "output"
    summary = tmp_path / "summary"
    env = {
        "EVENT_NAME": "pull_request",
        "REPOSITORY": "o/r",
        "PR_NUMBER": "1",
        "GITHUB_OUTPUT": str(output),
        "GITHUB_STEP_SUMMARY": str(summary),
    }
    assert ci_changes.main(env) == 0
    assert output.read_text(encoding="utf-8").splitlines() == [
        "backend=false",
        "frontend=false",
        "e2e=false",
        "image=false",
    ]
    assert "| backend | skipped |" in summary.read_text(encoding="utf-8")


def test_changed_files_reads_the_api_listing(monkeypatch: pytest.MonkeyPatch) -> None:
    """The files come from `gh api`, one name per line."""

    class Result:
        returncode = 0
        stdout = "README.md\nfrontend/package.json\n\n"
        stderr = ""

    monkeypatch.setattr(ci_changes.subprocess, "run", lambda *_a, **_k: Result())
    assert ci_changes.changed_files("o/r", "7") == [
        "README.md",
        "frontend/package.json",
    ]


def test_changed_files_reports_a_failed_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-zero exit from `gh` is a failure, not an empty list."""

    class Result:
        returncode = 1
        stdout = ""
        stderr = "boom"

    monkeypatch.setattr(ci_changes.subprocess, "run", lambda *_a, **_k: Result())
    assert ci_changes.changed_files("o/r", "7") is None
