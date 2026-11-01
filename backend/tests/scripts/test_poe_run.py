"""Tests for scripts/poe_run.py: modes, parsers, exit codes and log retention."""

import importlib.util
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "poe_run.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("poe_run", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["poe_run"] = module
    spec.loader.exec_module(module)
    return module


poe_run = _load()


def _text(*lines: str) -> str:
    return "\n".join(lines) + "\n"


# --- mode resolution ---------------------------------------------------------


def _file(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "output"
    path.write_text(content, encoding="utf-8")
    return path


def test_flag_beats_env_beats_file_beats_default(tmp_path: Path) -> None:
    """Flag beats env beats file beats default."""
    config = _file(tmp_path, "verbose\n")
    env = {"MENAGERIST_OUTPUT": "human"}
    assert poe_run.resolve_mode("agent", env, config) == "agent"
    assert poe_run.resolve_mode("", env, config) == "human"
    assert poe_run.resolve_mode("", {}, config) == "verbose"
    assert poe_run.resolve_mode("", {}, tmp_path / "missing") == "human"


def test_empty_env_and_file_are_skipped(tmp_path: Path) -> None:
    """Empty env and file are skipped."""
    assert (
        poe_run.resolve_mode(None, {"MENAGERIST_OUTPUT": "  "}, _file(tmp_path, "\n"))
        == "human"
    )


def test_mode_is_case_insensitive() -> None:
    """Mode is case insensitive."""
    assert poe_run.resolve_mode("AGENT", {}, Path("/nonexistent/x")) == "agent"


@pytest.mark.parametrize("source", ["flag", "env", "file"])
def test_invalid_mode_exits_2(
    source: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Invalid mode exits 2."""
    flag = "loud" if source == "flag" else ""
    env = {"MENAGERIST_OUTPUT": "loud"} if source == "env" else {}
    config = _file(tmp_path, "loud") if source == "file" else tmp_path / "missing"
    with pytest.raises(SystemExit) as exc:
        poe_run.resolve_mode(flag, env, config)
    assert exc.value.code == 2
    assert "Invalid output mode 'loud'" in capsys.readouterr().err


def test_user_config_file_locations() -> None:
    """User config file locations."""
    xdg = poe_run.user_config_file({"XDG_CONFIG_HOME": "/x"}, "linux")
    assert xdg == Path("/x/menagerist/output")
    win = poe_run.user_config_file({"APPDATA": "C:/Users/a/AppData/Roaming"}, "win32")
    assert win == Path("C:/Users/a/AppData/Roaming/menagerist/output")
    assert poe_run.user_config_file({}, "linux").parts[-3:] == (
        ".config",
        "menagerist",
        "output",
    )


# --- parsers -----------------------------------------------------------------

PYTEST_OK = """\
..........
5265 passed, 3 skipped in 146.60s (0:02:26)
"""

PYTEST_FAIL = """\
.F.F
=================================== FAILURES ===================================
____________________________ TestThing.test_add ____________________________
tests/test_a.py:10: in test_add
    assert add(1, 2) == 4
E   assert 3 == 4
E    +  where 3 = add(1, 2)
_______________________________ test_other[x-1] ________________________________
tests/test_b.py:5: in test_other
    raise ValueError("boom")
E   ValueError: boom
=========================== short test summary info ============================
FAILED tests/test_a.py::TestThing::test_add - assert 3 == 4
FAILED tests/test_b.py::test_other[x-1] - ValueError: boom
ERROR tests/test_c.py - ImportError: nope
2 failed, 2 passed, 1 error in 1.23s
"""


def test_pytest_pass() -> None:
    """Pytest pass."""
    summary = poe_run.parse_pytest(PYTEST_OK)
    assert summary.headline == "5265 passed, 3 skipped"
    assert summary.details == []


def test_pytest_failures_with_assertion_tails() -> None:
    """Pytest failures with assertion tails."""
    summary = poe_run.parse_pytest(PYTEST_FAIL)
    assert summary.headline == "2 failed, 2 passed, 1 error"
    assert summary.details == [
        "tests/test_a.py::TestThing::test_add",
        "    E   assert 3 == 4",
        "    E    +  where 3 = add(1, 2)",
        "tests/test_b.py::test_other[x-1]",
        "    E   ValueError: boom",
        "tests/test_c.py",
        "    ImportError: nope",
    ]


def test_pytest_caps_failures() -> None:
    """Pytest caps failures."""
    body = "".join(f"FAILED tests/t.py::test_{i} - bad\n" for i in range(15))
    summary = poe_run.parse_pytest(f"{body}15 failed in 1.00s\n")
    assert len([d for d in summary.details if d.startswith("tests/")]) == 10
    assert summary.details[-1] == "... and 5 more"


def test_pytest_unparseable() -> None:
    """Pytest unparseable."""
    assert poe_run.parse_pytest("Traceback\nboom\n") is None
    assert poe_run.parse_pytest("no tests ran in 0.01s\n").headline == "no tests ran"


def test_ruff() -> None:
    """Ruff."""
    assert poe_run.parse_ruff("All checks passed!\n").headline == "All checks passed"
    out = _text(
        "src/a.py:1:1: F401 `os` imported but unused",
        "src/b.py:2:3: E501 Line too long",
        "Found 2 errors.",
        "[*] 1 fixable",
    )
    summary = poe_run.parse_ruff(out)
    assert summary.headline == "2 errors"
    assert summary.details == [
        "src/a.py:1:1: F401 `os` imported but unused",
        "src/b.py:2:3: E501 Line too long",
    ]
    assert poe_run.parse_ruff("error: bad config\n") is None


def test_mypy() -> None:
    """Mypy."""
    ok = poe_run.parse_mypy("Success: no issues found in 1075 source files\n")
    assert ok.headline == "no issues found in 1075 source files"
    out = _text(
        "src/a.py:3: error: Incompatible types  [assignment]",
        "src/a.py:3: note: see docs",
        "src/b.py:9:4: error: Missing return  [return]",
        "Found 2 errors in 2 files (checked 5 source files)",
    )
    summary = poe_run.parse_mypy(out)
    assert summary.headline == "2 errors in 2 files"
    assert summary.details == [
        "src/a.py:3: error: Incompatible types  [assignment]",
        "src/b.py:9:4: error: Missing return  [return]",
    ]
    assert poe_run.parse_mypy("mypy: can't read file\n") is None


def test_vitest() -> None:
    """Vitest."""
    out = _text(
        "\x1b[31m FAIL \x1b[39m src/a.test.ts > suite > works",
        "AssertionError: expected 1 to be 2",
        " Test Files  1 failed | 4 passed (5)",
        "      Tests  1 failed | 20 passed (21)",
    )
    summary = poe_run.parse_vitest(out)
    assert summary.headline == (
        "files 1 failed | 4 passed (5); tests 1 failed | 20 passed (21)"
    )
    assert summary.details == [
        "src/a.test.ts > suite > works",
        "    AssertionError: expected 1 to be 2",
    ]
    assert poe_run.parse_vitest("nothing\n") is None


def test_vitest_real_output_with_unloadable_files() -> None:
    """Real vitest output: files that fail to load must show in the headline."""
    out = _text(
        " FAIL  |shared| tests/money.test.ts [ tests/money.test.ts ]",
        " FAIL  |shared| tests/list.test.ts [ tests/list.test.ts ]",
        "Error: Cannot find module './generated/client.gen' imported from /w/c.ts",
        " > src/lib/api/client.ts:1:1",
        "",
        " FAIL  |isolated| tests/a.test.ts > same-origin > uses a relative base URL",
        "Error: Cannot find module './generated/client.gen' imported from /w/c.ts",
        "",
        " Test Files  36 failed | 43 passed (79)",
        "      Tests  1 failed | 1162 passed (1163)",
        "   Start at  21:58:00",
        "   Duration  7.14s (transform 59%, import 26%, tests 8%, setup 5%, worker 2%)",
    )
    summary = poe_run.parse_vitest(out)
    assert summary.headline == (
        "files 36 failed | 43 passed (79); tests 1 failed | 1162 passed (1163)"
    )
    assert summary.details[0] == "|shared| tests/money.test.ts [ tests/money.test.ts ]"


def test_svelte_check_real_machine_output() -> None:
    """Real svelte-check output when stdout is not a TTY (machine format)."""
    out = _text(
        "> frontend@0.0.1 check",
        "> svelte-kit sync && svelte-check --tsconfig ./tsconfig.json --incremental",
        "",
        '1793138278893 START "/w/frontend"',
        '1793138278894 ERROR "src/routes/+page.svelte" 8:3 "No member \'listNodes\'."',
        '1793138278894 ERROR "src/lib/status.ts" 1:15 "No member \'x\'."',
        '1793138278896 WARNING "src/lib/a.svelte" 2:1 "Unused CSS"',
        "1793138278896 COMPLETED 253 FILES 2 ERRORS 1 WARNINGS 3 FILES_WITH_PROBLEMS",
    )
    summary = poe_run.parse_svelte_check(out)
    assert summary.headline == "2 errors and 1 warnings in 3 files (253 checked)"
    assert summary.details[1] == "src/lib/status.ts:1:15 No member 'x'."
    assert len(summary.details) == 3
    clean = _text(
        '1793138327600 START "/w/frontend"',
        "1793138327603 COMPLETED 230 FILES 0 ERRORS 0 WARNINGS 0 FILES_WITH_PROBLEMS",
    )
    assert poe_run.parse_svelte_check(clean).headline.startswith("0 errors")


def test_svelte_check() -> None:
    """Svelte check."""
    out = _text(
        "/p/src/A.svelte:12:5",
        "Error: Type 'x' is not assignable",
        "svelte-check found 1 error and 0 warnings in 1 file",
    )
    summary = poe_run.parse_svelte_check(out)
    assert summary.headline == "1 error and 0 warnings in 1 file"
    assert summary.details == ["/p/src/A.svelte:12:5 Error: Type 'x' is not assignable"]
    assert poe_run.parse_svelte_check("oops\n") is None


def test_lint_frontend() -> None:
    """Lint frontend."""
    prettier = _text(
        "Checking formatting...",
        "[warn] src/a.ts",
        "[warn] Code style issues found in 1 file. Run Prettier with --write to fix.",
    )
    summary = poe_run.parse_lint_frontend(prettier)
    assert summary.headline == "prettier: style issues in 1 file"
    assert summary.details == ["src/a.ts"]
    eslint = _text(
        "/p/src/a.ts",
        "  3:7  error  'x' is unused  no-unused-vars",
        "✖ 1 problem (1 error, 0 warnings)",
    )
    summary = poe_run.parse_lint_frontend(eslint)
    assert summary.headline == "eslint: 1 problem (1 error, 0 warnings)"
    assert summary.details == ["/p/src/a.ts:3:7 error 'x' is unused no-unused-vars"]
    assert (
        poe_run.parse_lint_frontend(
            "All matched files use Prettier code style!\n"
        ).headline
        == "prettier and eslint clean"
    )
    assert poe_run.parse_lint_frontend("") is None


def test_prek() -> None:
    """Prek."""
    out = _text(
        "ruff check............................................................Passed",
        "trailing whitespace...................................................Failed",
        "- hook id: trailing-whitespace",
        "- exit code: 1",
        "no files...........................................(no files to check)Skipped",
    )
    summary = poe_run.parse_prek(out)
    assert summary.headline == "1 failed, 1 passed, 1 skipped"
    assert summary.details == [
        "trailing whitespace",
        "    - hook id: trailing-whitespace",
        "    - exit code: 1",
    ]
    assert poe_run.parse_prek("nothing\n") is None


# --- rendering and exit codes -----------------------------------------------


def test_render_never_passes_on_non_zero_exit() -> None:
    """Render never passes on non zero exit."""
    out = poe_run.render(
        "pytest",
        1,
        1.0,
        "5 passed in 1.00s\n",
        poe_run.parse_pytest,
        ".agent-logs/r/pytest.log",
    )
    assert out.startswith("FAIL pytest | 5 passed | exit=1\n")
    assert out.endswith("Full log: .agent-logs/r/pytest.log\n")


def test_render_pass_and_unparseable_tail() -> None:
    """Render pass and unparseable tail."""
    assert (
        poe_run.render(
            "pytest", 0, 146.64, "5 passed in 1s\n", poe_run.parse_pytest, "l"
        )
        == "PASS pytest | 5 passed | 146.6s | exit=0\n"
    )
    noisy = "".join(f"line {i}\n" for i in range(100))
    out = poe_run.render("x", 3, 1.0, noisy, poe_run.parse_pytest, "l").splitlines()
    assert out[0] == "FAIL x | unrecognised output | exit=3"
    assert out[1:-1] == [f"line {i}" for i in range(60, 100)]
    assert out[-1] == "Full log: l"


def _tool(code: int, text: str = "hello") -> tuple[ModuleType, list[str]]:
    tool = poe_run.Tool("fake", ".", lambda _m, _w: [], poe_run.parse_pytest)
    steps = [
        "import sys",
        f"print({text!r}, flush=True)",
        "sys.stderr.write('err\\n')",
        f"sys.exit({code})",
    ]
    return tool, [sys.executable, "-c", "; ".join(steps)]


@pytest.mark.parametrize("mode", ["agent", "verbose"])
@pytest.mark.parametrize("code", [0, 1, 3])
def test_execute_preserves_exit_code_and_logs_everything(
    mode: str, code: int, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Execute preserves exit code and logs everything."""
    tool, cmd = _tool(code)
    assert poe_run.execute("t", tool, mode, root=tmp_path, cmd=cmd) == code
    out = capsys.readouterr().out
    (log,) = (tmp_path / ".agent-logs").glob("*/fake.log")
    assert log.read_text(encoding="utf-8").split() == ["hello", "err"]
    if mode == "agent":
        verdict = "PASS" if code == 0 else "FAIL"
        assert out.startswith(f"{verdict} fake | unrecognised output | exit={code}")
        assert "Full log: .agent-logs/" in out
    else:
        assert "hello" in out


@pytest.mark.parametrize("code", [0, 1, 3])
def test_human_mode_passes_through_without_logs(
    code: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Human mode inherits the terminal: no pipe, no log, exit code preserved."""
    tool, _ = _tool(code)
    probe = tmp_path / "probe.txt"
    script = "; ".join(
        [
            "import os, sys",
            "st = os.fstat(1)",
            f"open({str(probe)!r}, 'w').write(f'{{st.st_dev}} {{st.st_ino}}')",
            f"sys.exit({code})",
        ]
    )
    captured: list[object] = []
    monkeypatch.setattr(poe_run, "_stream", lambda *a, **k: captured.append(a))
    cmd = [sys.executable, "-c", script]
    assert poe_run.execute("t", tool, "human", root=tmp_path, cmd=cmd) == code
    assert not captured
    assert not (tmp_path / ".agent-logs").exists()
    here = os.fstat(1)
    assert probe.read_text() == f"{here.st_dev} {here.st_ino}"


def test_human_mode_reports_missing_executable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Human mode still reports a tool that cannot start."""
    tool, _ = _tool(0)
    cmd = ["definitely-not-a-command-xyz"]
    assert poe_run.execute("t", tool, "human", root=tmp_path, cmd=cmd) == 127
    assert "could not start" in capsys.readouterr().out
    assert not (tmp_path / ".agent-logs").exists()


def test_execute_reports_missing_executable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Execute reports missing executable."""
    tool, _ = _tool(0)
    assert (
        poe_run.execute(
            "t", tool, "agent", root=tmp_path, cmd=["definitely-not-a-command-xyz"]
        )
        == 127
    )
    assert "FAIL fake | could not start" in capsys.readouterr().out


# --- retention ---------------------------------------------------------------


def _run_dirs(root: Path, names: list[str], age: timedelta = timedelta()) -> None:
    for name in names:
        path = root / name
        path.mkdir(parents=True)
        stamp = (datetime.now(UTC) - age).timestamp()
        os.utime(path, (stamp, stamp))


def test_prune_keeps_newest_twenty_and_current(tmp_path: Path) -> None:
    """Prune keeps newest twenty and current."""
    names = [f"20260101T0000{i:02d}Z-t-1" for i in range(25)]
    _run_dirs(tmp_path, names)
    current = tmp_path / names[0]  # oldest by name, but must survive
    poe_run.prune_logs(tmp_path, current)
    remaining = sorted(p.name for p in tmp_path.iterdir())
    assert names[0] in remaining
    assert len(remaining) == 20
    assert names[-1] in remaining
    assert names[1] not in remaining


def test_prune_removes_runs_older_than_seven_days(tmp_path: Path) -> None:
    """Prune removes runs older than seven days."""
    _run_dirs(tmp_path, ["20250101T000000Z-old-1"], age=timedelta(days=8))
    _run_dirs(tmp_path, ["20260101T000000Z-new-1"], age=timedelta(days=1))
    poe_run.prune_logs(tmp_path)
    assert [p.name for p in tmp_path.iterdir()] == ["20260101T000000Z-new-1"]


def test_prune_ignores_missing_root_and_files(tmp_path: Path) -> None:
    """Prune ignores missing root and files."""
    poe_run.prune_logs(tmp_path / "missing")
    (tmp_path / "stray.txt").write_text("x", encoding="utf-8")
    poe_run.prune_logs(tmp_path)
    assert (tmp_path / "stray.txt").exists()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX directory modes")
def test_run_dir_is_private(tmp_path: Path) -> None:
    """Run dir is private."""
    run = poe_run.make_run_dir(tmp_path / ".agent-logs", "test-backend")
    assert run.stat().st_mode & 0o777 == 0o700
    assert run.name.endswith(f"-test-backend-{os.getpid()}")
