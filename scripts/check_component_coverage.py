#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "coverage>=7.10",
#     "pyyaml>=6.0.2",
#     "types-pyyaml>=6.0.2",
# ]
# ///
"""Enforce per-component coverage thresholds defined in codecov.yml.

The CODECOV component configuration is the single source of truth for backend
coverage targets. This script reads those targets from ``codecov.yml`` and
checks the already-generated coverage data from pytest locally, so the checks
never drift.
"""

import argparse
import io
import json
import os
import sys
import tempfile
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

import yaml
from coverage import Coverage
from coverage.exceptions import NoDataError

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"
FRONTEND_LCOV = FRONTEND_DIR / "coverage" / "lcov.info"
CODECOV_YML = ROOT / "codecov.yml"
COMMENT_MARKER = "<!-- component-coverage -->"
TOTALS_PREFIX = "<!-- coverage-total"
Result = tuple[str, float, float | None]
Counts = tuple[int, int]  # (hit, found)


def load_components() -> list[dict[str, Any]]:
    """Return the component_management.individual_components list from codecov.yml."""
    config = yaml.safe_load(CODECOV_YML.read_text(encoding="utf-8")) or {}
    if not isinstance(config, dict):
        raise SystemExit(f"Expected {CODECOV_YML} to contain a YAML mapping.")

    components: list[dict[str, Any]] = config.get("component_management", {}).get(
        "individual_components", []
    )
    if not components:
        raise SystemExit(
            f"No component_management.individual_components found in {CODECOV_YML}"
        )
    return components


def component_target(component: dict[str, Any]) -> float | None:
    """Return the fixed project target percentage for a component, or None when auto."""
    for status in component.get("statuses", []):
        if status.get("type") != "project" or "target" not in status:
            continue

        target = str(status["target"]).strip()
        if target.lower() == "auto":
            return None

        target = target.removesuffix("%")
        return float(target)

    return None


def component_paths(component: dict[str, Any]) -> list[str]:
    """Normalize Codecov path globs for the backend coverage data layout."""
    paths: list[str] = []
    for raw_path in component.get("paths", []):
        if not isinstance(raw_path, str):
            continue

        path = raw_path.strip().replace("\\", "/")
        path = path.lstrip("./")
        if path.startswith("backend/"):
            path = path.removeprefix("backend/")
        elif path.startswith(f"{BACKEND_DIR.name}/"):
            path = path.removeprefix(f"{BACKEND_DIR.name}/")
        elif path.startswith("/"):
            normalized = Path(path)
            try:
                path = str(normalized.relative_to(BACKEND_DIR))
            except ValueError:
                path = path.lstrip("/")
        paths.append(path)

    return paths


def is_frontend(component: dict[str, Any]) -> bool:
    """Whether a component's paths are under frontend/, so lcov measures it."""
    paths = component.get("paths", [])
    return bool(paths) and all(str(p).strip().startswith("frontend/") for p in paths)


def frontend_paths(component: dict[str, Any]) -> list[str]:
    """Return a frontend component's globs relative to frontend/, as lcov lists them."""
    return [str(p).strip().removeprefix("frontend/") for p in component["paths"]]


def lcov_counts(lcov: str, patterns: list[str]) -> Counts:
    """Return the lines hit and found in the lcov files that match any of the globs."""
    found = hit = 0
    included = False
    for line in lcov.splitlines():
        if line.startswith("SF:"):
            included = any(fnmatch(line.removeprefix("SF:"), p) for p in patterns)
        elif included and line.startswith("LF:"):
            found += int(line.removeprefix("LF:"))
        elif included and line.startswith("LH:"):
            hit += int(line.removeprefix("LH:"))
    return hit, found


def lcov_percent(lcov: str, patterns: list[str]) -> float:
    """Return the line coverage of the lcov files that match any of the globs."""
    hit, found = lcov_counts(lcov, patterns)
    return 100.0 * hit / found if found else 0.0


def backend_counts(cov: Coverage) -> Counts:
    """Return the hit and total of every measured backend file, branches included.

    That is the basis ``Coverage.report`` uses for the component percentages.
    """
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "coverage.json"
        try:
            cov.json_report(outfile=str(out), include=["src/**"])
        except NoDataError:
            return 0, 0
        totals = json.loads(out.read_text(encoding="utf-8"))["totals"]
    found = totals["num_statements"] + totals.get("num_branches", 0)
    hit = totals["covered_lines"] + totals.get("covered_branches", 0)
    return hit, found


def totals_marker(label: str, counts: Counts) -> str:
    """Return the hidden line that lets the comment script add the sides together."""
    return f"{TOTALS_PREFIX} {label} {counts[0]} {counts[1]} -->"


def overall_row(label: str, counts: Counts) -> Result:
    """Return the informational row for a whole side, which has no target."""
    hit, found = counts
    return label, 100.0 * hit / found if found else 0.0, None


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for local reporting or CI enforcement."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--frontend",
        action="store_true",
        help="Check the frontend components against frontend/coverage/lcov.info.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail if a component is below target; default is informational output.",
    )
    return parser.parse_args()


def collect_results(
    components: list[dict[str, Any]],
    cov: Coverage,
) -> list[Result]:
    """Collect each configured component's percentage against the loaded data."""
    results: list[Result] = []
    for component in components:
        target = component_target(component)
        if target is None:
            continue

        name = str(component.get("name") or component["component_id"])
        paths = component_paths(component)
        if not paths:
            continue

        try:
            percent = cov.report(include=paths, show_missing=False, file=io.StringIO())
        except NoDataError:
            percent = 0.0

        results.append((name, percent, target))

    return results


def print_missing_details(
    components: list[dict[str, Any]],
    failures: list[str],
    cov: Coverage,
) -> None:
    """Print detailed missing-coverage tables for failed components."""
    for component in components:
        name = str(component.get("name") or component["component_id"])
        if name not in failures:
            continue
        print(f"--- {name}: missing coverage ---")
        try:
            cov.report(
                include=component_paths(component),
                show_missing=True,
                file=sys.stdout,
            )
        except NoDataError:
            print("  (no files in this component were collected by coverage)")
        print()


def summary_markdown(
    results: list[Result],
    heading: str = "Backend coverage",
    totals: tuple[str, Counts] | None = None,
) -> str:
    """Return a Markdown table of each component's coverage against its target.

    Rows without a target (the whole-side row) are informational and carry no result.
    """
    checked = [(n, p, t) for n, p, t in results if t is not None]
    below = [name for name, percent, target in checked if percent < target]
    if below:
        verdict = f"❌ {len(below)} of {len(checked)} below target: {', '.join(below)}"
    else:
        verdict = f"✅ All {len(checked)} meet their targets"
    lines = [
        f"### {heading}",
        "",
        verdict,
        "",
        "| Component | Coverage | Target | Result |",
        "| --- | ---: | ---: | --- |",
    ]
    for name, percent, target in results:
        shown = "100" if percent >= 100 else f"{percent:.2f}"
        if target is None:
            lines.append(f"| {name} | {shown}% | - | - |")
            continue
        result = "✅ Pass" if percent >= target else "❌ **Below target**"
        lines.append(f"| {name} | {shown}% | {target:.0f}% | {result} |")
    if totals is not None:
        lines.extend(["", totals_marker(*totals)])
    return "\n".join(lines) + "\n"


def write_step_summary(
    results: list[Result],
    heading: str = "Backend coverage",
    totals: tuple[str, Counts] | None = None,
) -> None:
    """Append the results to the GitHub Actions job summary, when there is one."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as summary:
            summary.write(summary_markdown(results, heading, totals))


def write_comment_file(
    results: list[Result],
    heading: str = "Backend coverage",
    totals: tuple[str, Counts] | None = None,
) -> None:
    """Write the table for the pull request comment, when CI names a file for it.

    The marker lets the workflow find and update its earlier comment.
    """
    path = os.environ.get("COMPONENT_COVERAGE_COMMENT")
    if path:
        body = COMMENT_MARKER + "\n" + summary_markdown(results, heading, totals)
        Path(path).write_text(body, encoding="utf-8")


def collect_frontend_results(
    components: list[dict[str, Any]], lcov: str
) -> list[Result]:
    """Collect each frontend component's line coverage from the lcov report."""
    results: list[Result] = []
    for component in components:
        target = component_target(component)
        if target is None:
            continue
        name = str(component.get("name") or component["component_id"])
        results.append((name, lcov_percent(lcov, frontend_paths(component)), target))
    return results


def report(
    results: list[Result],
    heading: str,
    totals: tuple[str, Counts] | None = None,
) -> list[str]:
    """Print each component against its target and return those below it."""
    write_step_summary(results, heading, totals)
    write_comment_file(results, heading, totals)
    width = max(len(name) for name, _, _ in results)

    for name, percent, target in results:
        if target is None:
            print(f"[INFO] {name.ljust(width)}  {percent:6.2f}%  (no target)")
            continue
        status = "OK  " if percent >= target else "FAIL"
        target_text = f"target {target:.0f}%"
        print(f"[{status}] {name.ljust(width)}  {percent:6.2f}%  ({target_text})")

    return [
        name
        for name, percent, target in results
        if target is not None and percent < target
    ]


def main() -> int:
    """Display component percentages and optionally fail on their targets."""
    args = parse_args()
    components = load_components()
    frontend = [c for c in components if is_frontend(c)]
    backend = [c for c in components if not is_frontend(c)]
    os.chdir(BACKEND_DIR)

    cov: Coverage | None = None
    if args.frontend:
        if not FRONTEND_LCOV.is_file():
            print("No frontend coverage found - run `poe coverage-frontend` first.")
            return 1
        lcov = FRONTEND_LCOV.read_text(encoding="utf-8")
        results = collect_frontend_results(frontend, lcov)
        counts = lcov_counts(lcov, ["*"])
        results.append(overall_row("All frontend", counts))
        totals = ("frontend", counts)
        heading = "Frontend coverage"
    else:
        cov = Coverage(data_file=str(BACKEND_DIR / ".coverage"))
        try:
            cov.load()
        except NoDataError:
            print("No coverage data found - run tests with coverage enabled first.")
            return 1
        results = collect_results(backend, cov)
        counts = backend_counts(cov)
        results.append(overall_row("All backend", counts))
        totals = ("backend", counts)
        heading = "Backend coverage"

    if not any(target is not None for _, _, target in results):
        print("No components with a fixed (non-auto) target to check.")
        return 0

    failures = report(results, heading, totals)
    if not failures:
        print("\nAll components meet their coverage targets.")
        return 0

    print(f"\n{len(failures)} component(s) below target: {', '.join(failures)}\n")
    if args.strict:
        if cov is not None:
            print_missing_details(backend, failures, cov)
        return 1

    print("(informational only; rerun with --strict to fail CI)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
