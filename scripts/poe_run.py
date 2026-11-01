"""Run quality tools in one of three output modes: agent, human or verbose.

Invoked by the quality ``poe`` tasks. The mode is resolved from, in order: the
``--mode`` flag, ``MENAGERIST_OUTPUT``, the user file ``<config dir>/menagerist/output``
and finally the project default (``human``).

- agent: capture all output to the log and print only a short summary.
- human: inherit the terminal exactly as if the tool were run directly; no log.
- verbose: stream the tool's output with its verbose flags and also write the log.

Logs (agent and verbose modes only) live in
``.agent-logs/<UTC timestamp>-<task>-<pid>/<tool>.log`` at the repo root.
"""

import codecs
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR_NAME = ".agent-logs"
MODES = ("agent", "human", "verbose")
DEFAULT_MODE = "human"
ENV_VAR = "MENAGERIST_OUTPUT"
KEEP_RUNS = 20
MAX_AGE = timedelta(days=7)
MAX_ITEMS = 10
TAIL_LINES = 40
MAX_WIDTH = 200

ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


@dataclass(frozen=True)
class Summary:
    """A parsed tool result: a one-line headline and optional detail lines."""

    headline: str
    details: list[str] = field(default_factory=list)


Parser = Callable[[str], Summary | None]


def strip_ansi(text: str) -> str:
    """Remove terminal colour and cursor escape sequences."""
    return ANSI.sub("", text)


def _clip(line: str) -> str:
    line = line.rstrip()
    return line if len(line) <= MAX_WIDTH else line[: MAX_WIDTH - 3] + "..."


def _cap(items: list[str]) -> list[str]:
    if len(items) <= MAX_ITEMS:
        return items
    return [*items[:MAX_ITEMS], f"... and {len(items) - MAX_ITEMS} more"]


# --- mode resolution ---------------------------------------------------------


def user_config_file(
    environ: Mapping[str, str] | None = None, platform: str | None = None
) -> Path:
    """Location of the per-user output preference file."""
    env = os.environ if environ is None else environ
    if (platform or sys.platform) == "win32":
        base = env.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    else:
        base = env.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "menagerist" / "output"


def _validate(value: str, source: str) -> str:
    mode = value.strip().lower()
    if mode not in MODES:
        allowed = ", ".join(MODES)
        sys.stderr.write(f"Invalid output mode {value.strip()!r} from {source}; ")
        sys.stderr.write(f"expected one of: {allowed}\n")
        raise SystemExit(2)
    return mode


def resolve_mode(
    flag: str | None = None,
    environ: Mapping[str, str] | None = None,
    config_file: Path | None = None,
) -> str:
    """Pick the output mode: flag, then environment, then user file, then default."""
    env = os.environ if environ is None else environ
    if flag and flag.strip():
        return _validate(flag, "--mode")
    if env.get(ENV_VAR, "").strip():
        return _validate(env[ENV_VAR], ENV_VAR)
    path = config_file or user_config_file(env)
    try:
        content = path.read_text(encoding="utf-8").strip()
    except OSError:
        content = ""
    if content:
        return _validate(content.split()[0], str(path))
    return DEFAULT_MODE


# --- parsers -----------------------------------------------------------------

_PYTEST_SUMMARY = re.compile(
    r"^(?:=+ )?(?P<body>\d+ \S+(?:, \d+ \S+)*|no tests ran) in \d+(?:\.\d+)?s"
)
_PYTEST_ID = re.compile(r"^(?:FAILED|ERROR) (?P<rest>\S.*)$")
_PYTEST_HEADER = re.compile(r"^_{2,} (?P<name>.+?) _{2,}$")


def parse_pytest(text: str) -> Summary | None:
    """Summarise ``pytest -q --tb=short`` output."""
    lines = strip_ansi(text).splitlines()
    headline = next(
        (m["body"] for line in reversed(lines) if (m := _PYTEST_SUMMARY.match(line))),
        None,
    )
    if headline is None:
        return None

    sections: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in lines:
        if header := _PYTEST_HEADER.match(line):
            current = sections.setdefault(header["name"], [])
        elif line.startswith("="):
            current = None
        elif current is not None and line.startswith("E "):
            current.append(line.strip())

    details: list[str] = []
    for line in lines:
        found = _PYTEST_ID.match(line)
        if not found:
            continue
        ident, _, message = found["rest"].partition(" - ")
        key = ident.split("::")[-1]
        tail = next(
            (
                e[-3:]
                for name, e in sections.items()
                if e and (name == key or name.endswith((f".{key}", f" {key}")))
            ),
            [],
        )
        details.append(ident)
        details.extend(
            f"    {_clip(e)}" for e in tail or ([message] if message else [])
        )
    return Summary(headline, _cap_groups(details))


def _cap_groups(lines: list[str]) -> list[str]:
    """Cap failures (unindented lines), keeping their indented tails."""
    out: list[str] = []
    count = 0
    skipped = 0
    for line in lines:
        if not line.startswith(" "):
            count += 1
        if count <= MAX_ITEMS:
            out.append(line)
        elif not line.startswith(" "):
            skipped += 1
    if skipped:
        out.append(f"... and {skipped} more")
    return out


_RUFF_LINE = re.compile(r"^\S.*?:\d+:\d+: \S+ ")
_RUFF_FOUND = re.compile(r"^Found (?P<n>.+?)\.?$")


def parse_ruff(text: str) -> Summary | None:
    """Summarise ``ruff check --output-format concise`` output."""
    lines = [_clip(line) for line in strip_ansi(text).splitlines()]
    problems = [line for line in lines if _RUFF_LINE.match(line)]
    found = next((m["n"] for line in lines if (m := _RUFF_FOUND.match(line))), None)
    if found:
        return Summary(found, _cap(problems))
    if any(line.startswith("All checks passed") for line in lines):
        return Summary("All checks passed")
    return None


_MYPY_ERROR = re.compile(r"^.+?:\d+:(?:\d+:)? error: ")
_MYPY_FOUND = re.compile(r"^Found (?P<n>.+?)(?: \(checked .*\))?$")
_MYPY_OK = re.compile(r"^Success: (?P<n>.+)$")


def parse_mypy(text: str) -> Summary | None:
    """Summarise ``mypy --no-pretty`` output."""
    lines = strip_ansi(text).splitlines()
    errors = [_clip(line) for line in lines if _MYPY_ERROR.match(line)]
    for line in reversed(lines):
        if found := _MYPY_FOUND.match(line):
            return Summary(found["n"], _cap(errors))
        if ok := _MYPY_OK.match(line):
            return Summary(ok["n"])
    return None


_VITEST_TESTS = re.compile(r"^\s*Tests\s+(?P<n>\d.*)$")
_VITEST_FILES = re.compile(r"^\s*Test Files\s+(?P<n>\d.*)$")
_VITEST_FAIL = re.compile(r"^\s*FAIL\s+(?P<name>\S.*)$")
_VITEST_ERROR = re.compile(r"^\s*(?:\w*Error): .+")


def parse_vitest(text: str) -> Summary | None:
    """Summarise vitest's default reporter output."""
    lines = strip_ansi(text).splitlines()
    headline = next(
        (
            m["n"].strip()
            for line in reversed(lines)
            if (m := _VITEST_TESTS.match(line))
        ),
        None,
    )
    if headline is None:
        return None
    files = next(
        (m["n"].strip() for line in lines if (m := _VITEST_FILES.match(line))), None
    )
    if files and "failed" in files:
        headline = f"files {files}; tests {headline}"
    seen: set[str] = set()
    details: list[str] = []
    for i, line in enumerate(lines):
        found = _VITEST_FAIL.match(line)
        if not found or found["name"] in seen:
            continue
        seen.add(found["name"])
        details.append(_clip(found["name"]))
        message = next(
            (m for m in lines[i + 1 : i + 8] if _VITEST_ERROR.match(m)), None
        )
        if message:
            details.append(f"    {_clip(message.strip())}")
    return Summary(headline, _cap_groups(details))


_SVELTE_FOUND = re.compile(r"svelte-check found (?P<n>.+)$")
_SVELTE_DONE = re.compile(
    r"COMPLETED (?P<f>\d+) FILES (?P<e>\d+) ERRORS? (?P<w>\d+) WARNINGS? (?P<p>\d+) FILES_WITH_PROBLEMS"  # noqa: E501
)
_SVELTE_MACHINE = re.compile(
    r'^\d+ (?:ERROR|WARNING) "(?P<file>[^"]+)" (?P<pos>\d+:\d+) "(?P<msg>.*)"$'
)


def parse_svelte_check(text: str) -> Summary | None:
    """Summarise svelte-check's human or machine (non-TTY default) output."""
    lines = strip_ansi(text).splitlines()
    done = next(
        (m for line in reversed(lines) if (m := _SVELTE_DONE.search(line))), None
    )
    if done:
        problems = [
            _clip(f"{m['file']}:{m['pos']} {m['msg']}")
            for line in lines
            if (m := _SVELTE_MACHINE.match(line))
        ]
        counts = f"{done['e']} errors and {done['w']} warnings"
        summary_line = f"{counts} in {done['p']} files ({done['f']} checked)"
        return Summary(summary_line, _cap(problems))
    headline = next(
        (
            m["n"].strip()
            for line in reversed(lines)
            if (m := _SVELTE_FOUND.search(line))
        ),
        None,
    )
    if headline is None:
        return None
    details = [
        _clip(f"{lines[i - 1].strip()} {line.strip()}")
        for i, line in enumerate(lines)
        if i and line.startswith("Error:")
    ]
    return Summary(headline, _cap(details))


_PRETTIER_ISSUES = re.compile(r"^\[warn\] Code style issues found in (?P<n>.+?)\.")
_ESLINT_FOUND = re.compile(r"^\W*(?P<n>\d+ problems? \(.*\))")
_ESLINT_PROBLEM = re.compile(r"^\s+(?P<pos>\d+:\d+)\s+(?P<rest>(?:error|warning)\s.*)$")


def _eslint_details(lines: list[str]) -> list[str]:
    details: list[str] = []
    path = ""
    for entry in lines:
        if problem := _ESLINT_PROBLEM.match(entry):
            rest = " ".join(problem["rest"].split())
            details.append(_clip(f"{path}:{problem['pos']} {rest}"))
        elif entry and not entry[0].isspace() and not _ESLINT_FOUND.match(entry):
            path = entry.strip()
    return details


def parse_lint_frontend(text: str) -> Summary | None:
    """Summarise ``prettier --check`` followed by ``eslint`` output."""
    lines = strip_ansi(text).splitlines()
    if issues := next(filter(None, map(_PRETTIER_ISSUES.match, lines)), None):
        files = [
            line.removeprefix("[warn] ").strip()
            for line in lines
            if line.startswith("[warn] ") and not _PRETTIER_ISSUES.match(line)
        ]
        return Summary(f"prettier: style issues in {issues['n']}", _cap(files))
    if found := next(filter(None, map(_ESLINT_FOUND.match, lines)), None):
        return Summary(f"eslint: {found['n']}", _cap(_eslint_details(lines)))
    if any("All matched files use Prettier code style" in line for line in lines):
        return Summary("prettier and eslint clean")
    return None


_PREK_HOOK = re.compile(
    r"^(?P<name>\S.*?)\.{2,}.*?(?P<status>Passed|Failed|Skipped)\s*$"
)


def parse_prek(text: str) -> Summary | None:
    """Summarise ``prek run`` output."""
    lines = strip_ansi(text).splitlines()
    counts = {"Failed": 0, "Passed": 0, "Skipped": 0}
    details: list[str] = []
    capturing = 0
    for line in lines:
        hook = _PREK_HOOK.match(line)
        if hook:
            counts[hook["status"]] += 1
            capturing = 5 if hook["status"] == "Failed" else 0
            if capturing:
                details.append(hook["name"].strip())
        elif capturing and line.strip():
            details.append(f"    {_clip(line.strip())}")
            capturing -= 1
    if not any(counts.values()):
        return None
    headline = ", ".join(f"{n} {status.lower()}" for status, n in counts.items() if n)
    return Summary(headline, _cap_groups(details))


# --- tools -------------------------------------------------------------------


@dataclass(frozen=True)
class Tool:
    """How to run one tool in each mode."""

    name: str
    cwd: str
    build: Callable[[str, str], list[str]]
    parser: Parser


def _exe(name: str) -> str:
    """Find an executable, preferring the running interpreter's environment."""
    for suffix in ("", ".exe"):
        candidate = Path(sys.executable).parent / f"{name}{suffix}"
        if candidate.is_file():
            return str(candidate)
    return shutil.which(name) or name


def _pytest(selector: list[str], append: bool) -> Callable[[str, str], list[str]]:
    def build(mode: str, workers: str) -> list[str]:
        cmd = [
            _exe("pytest"),
            *selector,
            "-n",
            workers or "auto",
            "--dist",
            "loadscope",
        ]
        cmd += [
            "--cov=app",
            "--cov-branch",
            *(["--cov-append"] if append else []),
            "--cov-report=",
        ]
        if mode == "agent":
            return [*cmd, "-q", "--tb=short", "--no-header"]
        cmd.append("--cov-report=term-missing:skip-covered")
        return [*cmd, "-v"] if mode == "verbose" else cmd

    return build


def _ruff(mode: str, _workers: str) -> list[str]:
    extra = {"agent": ["--output-format=concise"], "verbose": ["--verbose"]}.get(
        mode, []
    )
    return [_exe("ruff"), "check", ".", "../scripts", *extra]


def _mypy(mode: str, _workers: str) -> list[str]:
    return [_exe("mypy"), *(["--no-pretty"] if mode == "agent" else [])]


def _npm(script: str) -> Callable[[str, str], list[str]]:
    return lambda _mode, _workers: [shutil.which("npm") or "npm", "run", script]


def _vitest(mode: str, workers: str) -> list[str]:
    cmd = [shutil.which("node") or "node", "./node_modules/vitest/vitest.mjs", "run"]
    if workers:
        cmd.append(f"--maxWorkers={workers}")
    return [*cmd, "--reporter=verbose"] if mode == "verbose" else cmd


def _prek(mode: str, _workers: str) -> list[str]:
    return [_exe("prek"), "run", *(["--verbose"] if mode == "verbose" else [])]


TOOLS: dict[str, Tool] = {
    "test-backend": Tool(
        "pytest",
        "backend",
        _pytest(["-m", "not integration"], append=False),
        parse_pytest,
    ),
    "test-backend-integration": Tool(
        "pytest", "backend", _pytest(["-m", "integration"], append=True), parse_pytest
    ),
    "test-frontend": Tool("vitest", "frontend", _vitest, parse_vitest),
    "lint-backend": Tool("ruff", "backend", _ruff, parse_ruff),
    "lint-frontend": Tool("lint", "frontend", _npm("lint"), parse_lint_frontend),
    "typecheck-backend": Tool("mypy", "backend", _mypy, parse_mypy),
    "typecheck-frontend": Tool(
        "svelte-check", "frontend", _npm("check"), parse_svelte_check
    ),
    "check-changed": Tool("prek", ".", _prek, parse_prek),
}


# --- logs --------------------------------------------------------------------


def prune_logs(
    logs_root: Path, current: Path | None = None, now: datetime | None = None
) -> None:
    """Keep the newest ``KEEP_RUNS`` runs and drop those older than ``MAX_AGE``."""
    if not logs_root.is_dir():
        return
    now = now or datetime.now(UTC)
    runs = sorted(
        (p for p in logs_root.iterdir() if p.is_dir() and not p.is_symlink()),
        key=lambda p: p.name,
        reverse=True,
    )
    kept = 1 if current in runs else 0
    for run in runs:
        if run == current:
            continue
        try:
            age = now - datetime.fromtimestamp(run.stat().st_mtime, UTC)
        except OSError:
            continue
        if kept >= KEEP_RUNS or age > MAX_AGE:
            shutil.rmtree(run, ignore_errors=True)
        else:
            kept += 1


def make_run_dir(logs_root: Path, task: str) -> Path:
    """Prune old runs, then create this run's private log directory."""
    prune_logs(logs_root)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run = logs_root / f"{stamp}-{task}-{os.getpid()}"
    logs_root.mkdir(mode=0o700, exist_ok=True)
    run.mkdir(mode=0o700, exist_ok=True)
    return run


# --- running -----------------------------------------------------------------


def _stream(proc: subprocess.Popen[bytes], log_path: Path, echo: bool) -> str:
    """Copy process output to the log (and the terminal if ``echo``); return it."""
    assert proc.stdout is not None
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    chunks: list[str] = []
    with log_path.open("w", encoding="utf-8", newline="") as log:
        while True:
            data = proc.stdout.read1(8192)  # type: ignore[attr-defined]
            text = decoder.decode(data, final=not data)
            if text:
                chunks.append(text)
                log.write(strip_ansi(text))
                if echo:
                    sys.stdout.write(text)
                    sys.stdout.flush()
            if not data:
                break
    return "".join(chunks)


def render(
    tool: str, exit_code: int, elapsed: float, output: str, parser: Parser, log: str
) -> str:
    """Build the agent-mode report for a finished run."""
    summary = parser(output)
    if exit_code == 0 and summary is not None:
        return f"PASS {tool} | {summary.headline} | {elapsed:.1f}s | exit=0\n"
    if summary is None:
        tail = [_clip(line) for line in strip_ansi(output).splitlines()[-TAIL_LINES:]]
        verdict = "PASS" if exit_code == 0 else "FAIL"
        head = f"{verdict} {tool} | unrecognised output | exit={exit_code}"
        return "\n".join([head, *tail, f"Full log: {log}"]) + "\n"
    return (
        "\n".join(
            [
                f"FAIL {tool} | {summary.headline} | exit={exit_code}",
                *summary.details,
                f"Full log: {log}",
            ]
        )
        + "\n"
    )


def _start_failure(tool: Tool, argv: list[str], exc: OSError) -> int:
    sys.stdout.write(
        f"FAIL {tool.name} | could not start {argv[0]}: {exc} | exit=127\n"
    )
    return 127


def execute(
    task: str,
    tool: Tool,
    mode: str,
    workers: str = "",
    root: Path = ROOT,
    cmd: list[str] | None = None,
) -> int:
    """Run ``tool`` in ``mode`` and return the tool's own exit code."""
    argv = cmd or tool.build(mode, workers)
    cwd = root / tool.cwd
    if mode == "human":
        try:
            return subprocess.call(argv, cwd=cwd)
        except OSError as exc:
            return _start_failure(tool, argv, exc)
    run_dir = make_run_dir(root / LOG_DIR_NAME, task)
    log_path = run_dir / f"{tool.name}.log"
    env = dict(os.environ)
    if mode == "agent":
        env["NO_COLOR"] = "1"
        env.pop("FORCE_COLOR", None)
    elif sys.stdout.isatty():
        env.setdefault("FORCE_COLOR", "1")
    start = time.monotonic()
    try:
        proc = subprocess.Popen(
            argv,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
    except OSError as exc:
        return _start_failure(tool, argv, exc)
    output = _stream(proc, log_path, echo=mode != "agent")
    code = proc.wait()
    if mode == "agent":
        rel = log_path.relative_to(root).as_posix()
        sys.stdout.write(
            render(tool.name, code, time.monotonic() - start, output, tool.parser, rel)
        )
    return code


def main(task: str, mode: str = "", workers: str = "") -> None:
    """Poe entry point: resolve the mode, run the task's tool, exit with its code."""
    sys.exit(execute(task, TOOLS[task], resolve_mode(mode), workers))
