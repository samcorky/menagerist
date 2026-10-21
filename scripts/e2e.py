"""Orchestrate the Playwright e2e run.

Uses one throwaway Postgres, with one database and backend per worker. Invoked by
the ``test-e2e*`` poe tasks. The worker count is resolved once here and exported
as ``E2E_WORKERS`` so the migrate script and ``playwright.config.ts`` agree on it.

Besides the per-worker backends, the ``auth`` Playwright project uses one extra backend
(port 8190) on an always-empty database, ``menagerist_auth``, which the migrate step
recreates on every run.

The ``cookies`` mode (``test-e2e-cookies``) runs only the cookie specs, in Chromium,
WebKit and Firefox, against their own backend and a TLS proxy (see
``frontend/tests/e2e/tls-proxy.mjs``). It is exported as ``E2E_COOKIES=1`` for the
migrate script and ``playwright.config.ts``.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def default_workers() -> int:
    """CPU cores available to this process."""
    affinity = getattr(os, "sched_getaffinity", None)  # Linux only
    return len(affinity(0)) if affinity else os.cpu_count() or 1


def poe(task: str) -> int:
    """Run a poe task and return its exit code."""
    return subprocess.call([sys.executable, "-m", "poethepoet", task], cwd=ROOT)


def main(
    workers: int | None = None, skip_build: bool = False, mode: str = "run"
) -> None:
    """Run the e2e suite with the requested worker count and mode."""
    n = workers or default_workers()
    if n < 1:
        sys.exit("--workers must be at least 1")
    os.environ["E2E_WORKERS"] = str(n)
    args = [shutil.which("npx") or "npx", "playwright", "test"]  # npx.cmd on Windows
    if mode in ("headed", "slow"):
        args.append("--headed")
    if mode == "slow":
        os.environ["PW_SLOWMO"] = "1000"
    if mode == "cookies":
        os.environ["E2E_COOKIES"] = "1"

    code = 1
    try:
        # Sync first: the servers run with `uv run --no-sync` (playwright.config.ts).
        steps = (
            ["sync-backend", "e2e-db-up"]
            + ([] if skip_build else ["e2e-build"])
            + ["e2e-migrate"]
        )
        for step in steps:
            if (code := poe(step)) != 0:
                break
        else:
            print(f"Running Playwright with {n} worker(s)", flush=True)
            code = subprocess.call(args, cwd=ROOT / "frontend")
    finally:
        poe("e2e-db-down")
    sys.exit(code)
