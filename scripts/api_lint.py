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
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINT_DIR = ROOT / "scripts" / "api-lint"
BASELINE = LINT_DIR / "baseline.json"

type Report = dict[str, dict[str, list[dict[str, object]]]]
type Findings = dict[tuple[str, str], str]

# Where the schema to compare with may be found, tried in order.
BASE_REFS = ("origin/main", "main")
# Enough to fix by hand; the validator lists the rest.
MAX_LISTED = 40


def run_validator(schema: Path) -> Report:
    """Run the validator and return its JSON report.

    Exit status 1 only means there were errors, so it is not checked.
    """
    # On Windows npx is npx.cmd, which subprocess only finds by its full path.
    npx = shutil.which("npx")
    if npx is None:
        sys.exit("npx was not found. Install Node.js to run the API lint.")
    result = subprocess.run(
        [
            npx,
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


def findings(report: Report, severity: str) -> Findings:
    """Each finding of one severity, keyed by rule and schema path."""
    found: Findings = {}
    for item in report.get(severity, {}).get("results", []):
        parts = item["path"]
        path = ".".join(str(part) for part in parts) if isinstance(parts, list) else ""
        found[(str(item["rule"]), path)] = str(item.get("message", ""))
    return found


def base_report(ref: str) -> Report | None:
    """Lint the schema committed at `ref`; None when git cannot supply it."""
    shown = subprocess.run(
        ["git", "show", f"{ref}:openapi.json"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if shown.returncode != 0:
        return None
    with tempfile.TemporaryDirectory() as directory:
        schema = Path(directory) / "openapi.json"
        schema.write_bytes(shown.stdout)
        return run_validator(schema)


def _listing(heading: str, found: Findings) -> list[str]:
    """A heading and up to `MAX_LISTED` findings, one per line."""
    if not found:
        return []
    lines = [heading]
    for (rule, path), text in sorted(found.items())[:MAX_LISTED]:
        lines.append(f"  {rule}  {path}" + (f"  ({text})" if text else ""))
    if len(found) > MAX_LISTED:
        lines.append(f"  ... and {len(found) - MAX_LISTED} more")
    return lines


def describe_findings(head: Report, rules: set[str], base: Report | None) -> list[str]:
    """Name the findings behind a failure, as lines for a person to act on.

    Errors are always listed. The baseline holds only counts, so the warnings
    that are new are known only by comparing with the schema on the base branch;
    without one, every warning of the rules that went over is listed instead.
    """
    warned = {
        key: text for key, text in findings(head, "warning").items() if key[0] in rules
    }
    if base is None:
        heading = "Warnings of the rules above (no base schema to compare with):"
    else:
        heading = "New warnings compared with the base branch:"
        was = findings(base, "warning")
        warned = {key: text for key, text in warned.items() if key not in was}
    return _listing("Errors:", findings(head, "error")) + _listing(heading, warned)


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
        over = {rule for rule, n in warnings.items() if n > baseline.get(rule, 0)}
        base = next(filter(None, (base_report(ref) for ref in BASE_REFS)), None)
        for line in describe_findings(report, over, base):
            print(line)
        print("Fix the new findings, or change the ruleset with a reason.")
        print("The validator in scripts/api-lint lists every finding.")
        return 1
    if improved:
        print(f"API lint passed. Fewer findings: {', '.join(improved)}.")
        print("Run `poe lint-schema-baseline` to lock the improvement in.")
    else:
        print(f"API lint passed: {total} warnings, none above the baseline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
