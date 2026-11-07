# /// script
# requires-python = ">=3.12"
# ///
"""Lint openapi.json with the IBM OpenAPI validator and ratchet its warnings.

Errors always fail. Warnings are compared with ``scripts/api-lint/baseline.json``,
a count per rule: a rule may not gain findings, and fixing some means lowering
its count with ``--update`` so the improvement cannot be lost. Rules and their
reasons live in ``scripts/api-lint/.spectral.yaml``; the conventions are in
``docs/API_STYLE.md``.
"""

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINT_DIR = ROOT / "scripts" / "api-lint"
BASELINE = LINT_DIR / "baseline.json"

type Report = dict[str, dict[str, list[dict[str, object]]]]


def run_validator(schema: Path) -> Report:
    """Run the validator and return its JSON report.

    Exit status 1 only means there were errors, so it is not checked.
    """
    result = subprocess.run(
        [
            "npx",
            "--no-install",
            "ibm-openapi-validator",
            "-r",
            ".spectral.yaml",
            "-j",
            str(schema),
        ],
        cwd=LINT_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        report: Report = json.loads(result.stdout)
    except json.JSONDecodeError:
        output = result.stderr or result.stdout
        sys.exit(f"No report from the validator (exit {result.returncode}):\n{output}")
    return report


def counts(report: Report, severity: str) -> Counter[str]:
    """Count findings of one severity per rule."""
    results = report.get(severity, {}).get("results", [])
    return Counter(str(item["rule"]) for item in results)


def main() -> int:
    """Return the process exit status."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", type=Path, default=ROOT / "openapi.json")
    parser.add_argument(
        "--update",
        action="store_true",
        help="rewrite the baseline from the current warnings",
    )
    args = parser.parse_args()

    report = run_validator(args.schema)
    errors = counts(report, "error")
    warnings = counts(report, "warning")
    total = sum(warnings.values())

    if args.update:
        BASELINE.write_text(json.dumps(dict(sorted(warnings.items())), indent=2) + "\n")
        print(f"Baseline written: {total} warnings across {len(warnings)} rules.")
        return 0

    baseline: dict[str, int] = (
        json.loads(BASELINE.read_text()) if BASELINE.exists() else {}
    )
    failures = [f"{n} error(s) from {rule}" for rule, n in sorted(errors.items())]
    failures += [
        f"{rule}: {n} warning(s), baseline {baseline.get(rule, 0)}"
        for rule, n in sorted(warnings.items())
        if n > baseline.get(rule, 0)
    ]
    improved = sorted(
        rule for rule, was in baseline.items() if warnings.get(rule, 0) < was
    )

    if failures:
        print("API lint failed:\n  " + "\n  ".join(failures))
        print("Fix the new findings, or change the ruleset with a reason.")
        print("The validator in scripts/api-lint lists each one.")
        return 1
    if improved:
        print(f"API lint passed. Fewer findings: {', '.join(improved)}.")
        print("Run `poe lint-schema-baseline` to lock the improvement in.")
    else:
        print(f"API lint passed: {total} warnings, none above the baseline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
