"""Tests for scripts/api_lint.py: the OpenAPI style lint and its warning ratchet."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "api_lint.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("api_lint", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["api_lint"] = module
    spec.loader.exec_module(module)
    return module


lint = _load()


def _item(rule: str, *path: str, message: str = "") -> dict[str, object]:
    return {"rule": rule, "path": list(path), "message": message}


def _report(
    warnings: list[dict[str, object]], errors: list[dict[str, object]] | None = None
) -> dict[str, dict[str, list[dict[str, object]]]]:
    return {
        "warning": {"results": warnings},
        "error": {"results": errors or []},
    }


DESCRIBE = "ibm-property-description"
EXAMPLE = "ibm-success-response-example"


def test_a_finding_is_keyed_by_rule_and_dotted_path() -> None:
    """The same finding in two schemas is two findings."""
    found = lint.findings(
        _report(
            [
                _item(
                    DESCRIBE,
                    "components",
                    "schemas",
                    "A",
                    "properties",
                    "x",
                    message="m",
                ),
                _item(DESCRIBE, "components", "schemas", "B", "properties", "x"),
            ]
        ),
        "warning",
    )
    assert found == {
        (DESCRIBE, "components.schemas.A.properties.x"): "m",
        (DESCRIBE, "components.schemas.B.properties.x"): "",
    }


def test_a_report_without_the_severity_has_no_findings() -> None:
    """A clean run has nothing under either severity."""
    assert lint.findings({}, "warning") == {}


def test_a_finding_without_a_usable_path_still_counts() -> None:
    """A rule that cannot name a place is listed under an empty path."""
    report = _report([{"rule": DESCRIBE, "path": None}])
    assert lint.findings(report, "warning") == {(DESCRIBE, ""): ""}


def test_only_the_new_findings_of_the_failing_rules_are_listed() -> None:
    """Findings already on the base branch, and other rules, are left out."""
    old = _item(DESCRIBE, "components", "schemas", "Old", "properties", "a")
    new = _item(DESCRIBE, "components", "schemas", "New", "properties", "b")
    other = _item(EXAMPLE, "paths", "/x", "get")
    lines = lint.describe_findings(
        _report([old, new, other]), {DESCRIBE}, _report([old])
    )
    assert lines == [
        "New warnings compared with the base branch:",
        f"  {DESCRIBE}  components.schemas.New.properties.b",
    ]


def test_without_a_base_every_finding_of_the_failing_rules_is_listed() -> None:
    """With nothing to compare with, the person is told so and sees them all."""
    a = _item(DESCRIBE, "components", "schemas", "A", "properties", "a")
    b = _item(EXAMPLE, "paths", "/x", "get")
    lines = lint.describe_findings(_report([a, b]), {DESCRIBE}, None)
    assert lines[0].startswith("Warnings of the rules above (no base schema")
    assert lines[1:] == [f"  {DESCRIBE}  components.schemas.A.properties.a"]


def test_errors_are_always_listed_first_with_their_message() -> None:
    """Errors need no comparison; they fail on their own."""
    error = _item("oas3-schema", "paths", "/x", message="is not valid")
    lines = lint.describe_findings(_report([], [error]), set(), _report([]))
    assert lines == ["Errors:", "  oas3-schema  paths./x  (is not valid)"]


def test_nothing_is_listed_when_there_is_nothing_to_say() -> None:
    """No new findings means no section at all."""
    same = _item(DESCRIBE, "components", "schemas", "A", "properties", "a")
    assert lint.describe_findings(_report([same]), {DESCRIBE}, _report([same])) == []


def test_a_long_list_is_capped_and_says_how_many_more() -> None:
    """The validator lists them all; the failure message stays readable."""
    many = [
        _item(DESCRIBE, "properties", f"p{n:03}") for n in range(lint.MAX_LISTED + 7)
    ]
    lines = lint.describe_findings(_report(many), {DESCRIBE}, _report([]))
    assert len(lines) == 1 + lint.MAX_LISTED + 1
    assert lines[-1] == "  ... and 7 more"


def test_the_validator_is_run_through_the_npx_found_on_the_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """On Windows npx is npx.cmd, so its full path is what gets run."""
    seen: list[list[str]] = []

    def fake_run(
        command: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        seen.append(command)
        return subprocess.CompletedProcess(
            command, 0, stdout=json.dumps(_report([])), stderr=""
        )

    monkeypatch.setattr(lint.shutil, "which", lambda name: rf"C:\node\{name}.CMD")
    monkeypatch.setattr(lint.subprocess, "run", fake_run)
    assert lint.run_validator(tmp_path / "openapi.json") == _report([])
    assert seen[0][0] == r"C:\node\npx.CMD"
    assert "ibm-openapi-validator" in seen[0]


def test_a_missing_npx_is_explained(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Without Node the run stops with a plain message, not a traceback."""
    monkeypatch.setattr(lint.shutil, "which", lambda name: None)
    with pytest.raises(SystemExit, match="npx was not found"):
        lint.run_validator(tmp_path / "openapi.json")


def test_no_report_from_the_validator_stops_the_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Output that is not JSON is shown rather than guessed at."""

    def fake_run(
        command: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 2, stdout="", stderr="boom")

    monkeypatch.setattr(lint.shutil, "which", lambda name: "npx")
    monkeypatch.setattr(lint.subprocess, "run", fake_run)
    with pytest.raises(SystemExit, match="boom"):
        lint.run_validator(tmp_path / "openapi.json")


def test_the_base_schema_is_linted_from_git(monkeypatch: pytest.MonkeyPatch) -> None:
    """The committed schema at the ref is written out and handed to the validator."""
    linted: list[bytes] = []

    def fake_git(
        command: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        assert command == ["git", "show", "origin/main:openapi.json"]
        return subprocess.CompletedProcess(command, 0, stdout=b'{"openapi": "3.1"}')

    def fake_validator(schema: Path) -> dict[str, dict[str, list[dict[str, object]]]]:
        linted.append(schema.read_bytes())
        return _report([])

    monkeypatch.setattr(lint.subprocess, "run", fake_git)
    monkeypatch.setattr(lint, "run_validator", fake_validator)
    assert lint.base_report("origin/main") == _report([])
    assert linted == [b'{"openapi": "3.1"}']


def test_a_ref_git_does_not_know_gives_no_base(monkeypatch: pytest.MonkeyPatch) -> None:
    """A shallow clone without the ref falls back to the plain listing."""

    def fake_git(
        command: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(command, 128, stdout=b"")

    monkeypatch.setattr(lint.subprocess, "run", fake_git)
    assert lint.base_report("origin/main") is None


def _run_main(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    head: dict[str, dict[str, list[dict[str, object]]]],
    base: dict[str, dict[str, list[dict[str, object]]]] | None,
    baseline: dict[str, int],
    *args: str,
) -> int:
    baseline_file = tmp_path / "baseline.json"
    baseline_file.write_text(json.dumps(baseline))
    monkeypatch.setattr(lint, "BASELINE", baseline_file)
    monkeypatch.setattr(lint, "run_validator", lambda schema: head)
    monkeypatch.setattr(lint, "base_report", lambda ref: base)
    monkeypatch.setattr(sys, "argv", ["api_lint.py", *args])
    return int(lint.main())


def test_a_failure_names_the_new_findings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A rule over its baseline fails the run and shows what to fix."""
    old = _item(DESCRIBE, "components", "schemas", "Old", "properties", "a")
    new = _item(DESCRIBE, "components", "schemas", "New", "properties", "b")
    status = _run_main(
        monkeypatch, tmp_path, _report([old, new]), _report([old]), {DESCRIBE: 1}
    )
    out = capsys.readouterr().out
    assert status == 1
    assert f"{DESCRIBE}: 2 warning(s), baseline 1" in out
    assert "components.schemas.New.properties.b" in out
    assert "components.schemas.Old.properties.a" not in out


def test_a_failure_without_a_base_still_lists_something(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When no base schema is reachable the failing rule's findings are shown."""
    only = _item(DESCRIBE, "components", "schemas", "A", "properties", "a")
    status = _run_main(monkeypatch, tmp_path, _report([only]), None, {})
    out = capsys.readouterr().out
    assert status == 1
    assert "no base schema to compare with" in out
    assert "components.schemas.A.properties.a" in out


def test_a_run_within_the_baseline_passes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Nothing above the baseline passes, and no comparison is attempted."""
    item = _item(DESCRIBE, "components", "schemas", "A", "properties", "a")
    status = _run_main(monkeypatch, tmp_path, _report([item]), None, {DESCRIBE: 1})
    assert status == 0
    assert "none above the baseline" in capsys.readouterr().out


def test_fewer_findings_point_at_the_baseline_update(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An improvement passes, with a reminder to lock it in."""
    status = _run_main(monkeypatch, tmp_path, _report([]), None, {DESCRIBE: 3})
    assert status == 0
    assert "Fewer findings" in capsys.readouterr().out


def test_update_rewrites_the_baseline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--update` records the current count of each rule."""
    item = _item(DESCRIBE, "components", "schemas", "A", "properties", "a")
    status = _run_main(monkeypatch, tmp_path, _report([item]), None, {}, "--update")
    assert status == 0
    assert json.loads((tmp_path / "baseline.json").read_text()) == {DESCRIBE: 1}
    assert "Baseline written: 1 warnings" in capsys.readouterr().out
