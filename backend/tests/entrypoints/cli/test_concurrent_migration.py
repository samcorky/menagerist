"""Several instances starting against one database migrate it exactly once."""

import asyncio
import json
import os
import subprocess
import sys
import uuid
from typing import TYPE_CHECKING

import pytest
import sqlalchemy
from sqlalchemy.engine import make_url

from app.entrypoints.cli import backups
from app.modules.backup.domain.errors import BackupNotFoundError
from app.platform import alembic_runner
from app.platform.advisory_locks import AdvisoryLock, session_lock
from app.platform.database import get_engine

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

pytestmark = pytest.mark.integration

INSTANCES = 4
INITIAL_REVISION = "cd0c974e3e33"
# Runs the installed `menagerist` entry point without relying on the script path.
ENTRY_POINT = "from app.entrypoints.cli import app; app.meta()"
# The same entry point with the migration lock removed. After the "is anything
# pending?" check it waits until every instance has made that check, so each sees
# the work before any starts it. That makes the race certain: a fixed pause is not,
# because on a busy machine the instances can start further apart than the pause.
UNLOCKED_ENTRY_POINT = """
import asyncio
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from app.entrypoints.cli import app, backups
from app.platform import alembic_runner


@asynccontextmanager
async def no_lock(*_args):
    yield


real_pending = alembic_runner.pending


async def slow_pending(*args):
    result = await real_pending(*args)
    barrier = Path(os.environ["TEST_BARRIER_DIR"])
    (barrier / str(os.getpid())).touch()
    deadline = time.monotonic() + 60
    while len(list(barrier.iterdir())) < int(os.environ["TEST_BARRIER_COUNT"]):
        if time.monotonic() > deadline:
            raise TimeoutError("not every instance reached the pending check")
        await asyncio.sleep(0.05)
    return result


backups.session_lock = no_lock
alembic_runner.pending = slow_pending
app.meta()
"""


def _env(url: str, backups_dir: Path | None, media_dir: Path | None) -> dict[str, str]:
    """Environment for one instance: its own database, backups and media."""
    env = {**os.environ, "MENAGERIST_DATABASE_URL": url, "NO_COLOR": "1"}
    if backups_dir is not None:
        env["MENAGERIST_BACKUP_PATH"] = str(backups_dir)
    if media_dir is not None:
        env["MENAGERIST_MEDIA_STORAGE_PATH"] = str(media_dir)
    return env


@pytest.fixture
def old_database(postgres_url: str, postgres_sync_url: str) -> Iterator[str]:
    """A fresh database at the first revision, so the seed migration is pending."""
    name = f"concurrent_{uuid.uuid4().hex[:12]}"
    admin = sqlalchemy.create_engine(postgres_sync_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(sqlalchemy.text(f'CREATE DATABASE "{name}"'))
    url = make_url(postgres_url).set(database=name).render_as_string(False)
    try:
        subprocess.run(
            (
                *(sys.executable, "-c", ENTRY_POINT, "migrate", "upgrade"),
                *(INITIAL_REVISION, "--no-backup"),
            ),
            check=True,
            capture_output=True,
            env=_env(url, None, None),
        )
        yield url
    finally:
        with admin.connect() as connection:
            connection.execute(
                sqlalchemy.text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
            )
        admin.dispose()


async def _instance(env: dict[str, str], entry: str) -> tuple[int, str]:
    """Start one `menagerist migrate upgrade` and wait for it."""
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        entry,
        "migrate",
        "upgrade",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=env,
    )
    output, _ = await process.communicate()
    return process.returncode or 0, output.decode()


async def _start_together(
    database: str, tmp_path: Path, entry: str
) -> tuple[list[tuple[int, str]], list[Path]]:
    """Start the instances at once; return their results and the archives taken."""
    backups_dir = tmp_path / "backups"
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    barrier_dir = tmp_path / "barrier"
    barrier_dir.mkdir()
    env = {
        **_env(database, backups_dir, media_dir),
        "TEST_BARRIER_DIR": str(barrier_dir),
        "TEST_BARRIER_COUNT": str(INSTANCES),
    }
    results = await asyncio.gather(*(_instance(env, entry) for _ in range(INSTANCES)))
    return list(results), list((backups_dir / "instance").glob("*.tar.gz"))


async def test_instances_starting_together_migrate_and_back_up_once(
    old_database: str, tmp_path: Path, postgres_sync_url: str
) -> None:
    """Every instance succeeds, the database reaches head and one backup exists."""
    results, archives = await _start_together(old_database, tmp_path, ENTRY_POINT)

    failures = [output for code, output in results if code != 0]
    assert not failures, failures
    engine = sqlalchemy.create_engine(
        make_url(postgres_sync_url).set(database=make_url(old_database).database)
    )
    try:
        with engine.connect() as connection:
            revisions = connection.scalars(
                sqlalchemy.text("SELECT version_num FROM alembic_version")
            ).all()
    finally:
        engine.dispose()
    assert tuple(revisions) == alembic_runner.code_head_revisions()
    assert len(archives) == 1, archives
    summary = json.loads(archives[0].with_suffix("").with_suffix(".json").read_text())
    assert summary["label"] == "pre-migration"


async def test_without_the_lock_instances_each_take_a_backup(
    old_database: str, tmp_path: Path
) -> None:
    """Negative control: the check above fails when the lock is removed.

    Without this, a regression that made the lock a no-op could still pass the
    positive test on a lucky start order. Each instance waits for the others at the
    pending check, so all of them see the migration as pending.
    """
    _, archives = await _start_together(old_database, tmp_path, UNLOCKED_ENTRY_POINT)
    assert len(archives) > 1, archives


async def test_restore_waits_for_a_running_migration(postgres_url: str) -> None:
    """A restore started during a migration does not run until it has finished."""
    del postgres_url
    from app.entrypoints.api.shared.access_guard import get_access_guard

    async with session_lock(get_engine(), AdvisoryLock.MIGRATION):
        restore = asyncio.create_task(
            backups.restore_backup(
                uuid.uuid4(), replace=False, guard=get_access_guard()
            )
        )
        done, _ = await asyncio.wait({restore}, timeout=1)
        assert not done
    # With the lock free it proceeds, and fails only because the archive is unknown.
    with pytest.raises(BackupNotFoundError):
        await asyncio.wait_for(restore, timeout=30)
