#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "coverage>=7.10",
#     "pyyaml>=6.0.2",
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
import os
import sys
from pathlib import Path
from typing import Any

import yaml
from coverage import Coverage
from coverage.exceptions import NoDataError

ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT / "backend"
CODECOV_YML = ROOT / "codecov.yml"


def load_components() -> list[dict[str, Any]]:
    """Return the component_management.individual_components list from codecov.yml."""
    config = yaml.safe_load(CODECOV_YML.read_text(encoding="utf-8")) or {}
    if not isinstance(config, dict):
        raise SystemExit(f"Expected {CODECOV_YML} to contain a YAML mapping.")

    components = config.get("component_management", {}).get("individual_components", [])
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


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for local reporting or CI enforcement."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail if a component is below target; default is informational output.",
    )
    return parser.parse_args()


def collect_results(
    components: list[dict[str, Any]],
    cov: Coverage,
) -> list[tuple[str, float, float]]:
    """Collect each configured component's percentage against the loaded data."""
    results: list[tuple[str, float, float]] = []
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


def main() -> int:
    """Display component percentages and optionally fail on their targets."""
    args = parse_args()
    components = load_components()
    os.chdir(BACKEND_DIR)

    cov = Coverage(data_file=str(BACKEND_DIR / ".coverage"))
    try:
        cov.load()
    except NoDataError:
        print("No coverage data found - run tests with coverage enabled first.")
        return 1

    results = collect_results(components, cov)
    if not results:
        print("No components with a fixed (non-auto) target to check.")
        return 0

    width = max(len(name) for name, _, _ in results)
    failures = [name for name, percent, target in results if percent < target]

    for name, percent, target in results:
        status = "OK  " if percent >= target else "FAIL"
        target_text = f"target {target:.0f}%"
        message = f"[{status}] {name.ljust(width)}  {percent:6.2f}%  ({target_text})"
        print(message)

    if not failures:
        print("\nAll components meet their coverage targets.")
        return 0

    print(f"\n{len(failures)} component(s) below target: {', '.join(failures)}\n")
    if args.strict:
        print_missing_details(components, failures, cov)
        return 1

    print("(informational only; rerun with --strict to fail CI)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
