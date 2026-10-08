"""Orchestrate the Playwright e2e run: one throwaway Postgres, one database and backend per worker.

Invoked by the ``test-e2e*`` poe tasks. The worker count is resolved once here and exported as
``E2E_WORKERS`` so the migrate script and ``playwright.config.ts`` agree on it.
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def default_workers() -> int:
    """CPU cores available to this process."""
    try:
        return len(os.sched_getaffinity(0))
    except AttributeError:
        return os.cpu_count() or 1


def poe(task: str) -> int:
    return subprocess.call([sys.executable, "-m", "poethepoet", task], cwd=ROOT)


def main(
    workers: int | None = None, skip_build: bool = False, mode: str = "run"
) -> None:
    n = workers or default_workers()
    if n < 1:
        sys.exit("--workers must be at least 1")
    os.environ["E2E_WORKERS"] = str(n)
    args = ["npx", "playwright", "test"]
    if mode in ("headed", "slow"):
        args.append("--headed")
    if mode == "slow":
        os.environ["PW_SLOWMO"] = "1000"

    code = 1
    try:
        steps = ["e2e-db-up"] + ([] if skip_build else ["e2e-build"]) + ["e2e-migrate"]
        for step in steps:
            if (code := poe(step)) != 0:
                break
        else:
            print(f"Running Playwright with {n} worker(s)", flush=True)
            code = subprocess.call(args, cwd=ROOT / "frontend")
    finally:
        poe("e2e-db-down")
    sys.exit(code)
