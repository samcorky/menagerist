"""Create and migrate one database per e2e worker (menagerist_w0 ... menagerist_w{N-1}).

Idempotent: existing databases are kept and migrated again. Needs the e2e Postgres container
(``poe e2e-db-up``). N comes from ``E2E_WORKERS``, falling back to the CPU count.
"""

import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTAINER = "menagerist-e2e-db"
URL = "postgresql+asyncpg://menagerist:menagerist@localhost:55433/{db}"


def worker_count() -> int:
    if raw := os.environ.get("E2E_WORKERS"):
        return int(raw)
    try:
        return len(os.sched_getaffinity(0))
    except AttributeError:
        return os.cpu_count() or 1


def psql(sql: str) -> str:
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


def prepare(db: str) -> None:
    if not psql(f"SELECT 1 FROM pg_database WHERE datname = '{db}'"):
        psql(f'CREATE DATABASE "{db}"')
    env = {**os.environ, "MENAGERIST_DATABASE_URL": URL.format(db=db)}
    subprocess.run(
        ["menagerist", "migrate", "upgrade"], cwd=ROOT / "backend", env=env, check=True
    )


def main() -> None:
    names = [f"menagerist_w{i}" for i in range(worker_count())]
    with ThreadPoolExecutor() as pool:
        list(pool.map(prepare, names))
    print(f"Migrated {len(names)} e2e database(s): {', '.join(names)}")


if __name__ == "__main__":
    main()
