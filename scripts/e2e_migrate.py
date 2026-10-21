"""Create and migrate one database per e2e worker.

Databases are named menagerist_w0 ... menagerist_w{N-1}. Idempotent: existing
databases are kept and migrated again. The users table starts empty; each worker
sets up its administrator through the real first-run endpoint.

The ``auth`` project's database, menagerist_auth, is dropped and recreated on every
run so it is always empty (auth.spec.ts drives first-run setup). No backend may be
connected to it while this runs. The ``cookies`` projects' database,
menagerist_cookies, is recreated the same way, and when ``E2E_COOKIES=1`` it is the only
one prepared. Needs the e2e Postgres container (``poe e2e-db-up``). N comes from
``E2E_WORKERS``, falling back to the CPU count.
"""

import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTAINER = "menagerist-e2e-db"
AUTH_DB = "menagerist_auth"
COOKIES_DB = "menagerist_cookies"
URL = "postgresql+asyncpg://menagerist:menagerist@localhost:55433/{db}"


def worker_count() -> int:
    """Return the e2e worker count."""
    if raw := os.environ.get("E2E_WORKERS"):
        return int(raw)
    affinity = getattr(os, "sched_getaffinity", None)  # Linux only
    return len(affinity(0)) if affinity else os.cpu_count() or 1


def psql(sql: str) -> str:
    """Run SQL in the e2e container and return trimmed output."""
    result = subprocess.run(
        [
            "docker",
            "exec",
            CONTAINER,
            "psql",
            "-U",
            "menagerist",
            "-d",
            "postgres",
            "-tAc",
            sql,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def prepare(db: str, *, fresh: bool = False) -> None:
    """Create the database if missing (or recreate it if ``fresh``), then migrate it."""
    if fresh:
        psql(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)')
    if not psql(f"SELECT 1 FROM pg_database WHERE datname = '{db}'"):
        psql(f'CREATE DATABASE "{db}"')
    env = {**os.environ, "MENAGERIST_DATABASE_URL": URL.format(db=db)}
    subprocess.run(
        ["menagerist", "migrate", "upgrade"], cwd=ROOT / "backend", env=env, check=True
    )


def main() -> None:
    """Create and migrate every worker database."""
    if os.environ.get("E2E_COOKIES") == "1":
        prepare(COOKIES_DB, fresh=True)
        print(f"Migrated e2e database {COOKIES_DB} (empty)")
        return
    names = [f"menagerist_w{i}" for i in range(worker_count())]
    with ThreadPoolExecutor() as pool:
        list(pool.map(prepare, names))
        pool.submit(prepare, AUTH_DB, fresh=True).result()
    print(
        f"Migrated {len(names)} e2e database(s): {', '.join(names)}, {AUTH_DB} (empty)"
    )


if __name__ == "__main__":
    main()
