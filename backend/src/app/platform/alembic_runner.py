from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

from alembic import command
from app.platform.config import get_database_settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

_MIGRATIONS_PATH = Path(__file__).resolve().parent.parent / "alembic"
# app/platform/ → app/ → app/alembic/ — works for both editable and installed wheels.


def build_config() -> Config:
    """Build an Alembic `Config` pointed at this backend's migrations and database.

    Also reused by the `pytest-alembic` integration tests, which need the same
    `script_location`/`sqlalchemy.url` wiring against a testcontainers database.
    """
    config = Config()
    config.set_main_option("script_location", str(_MIGRATIONS_PATH))
    config.set_main_option("sqlalchemy.url", str(get_database_settings().database_url))
    return config


def upgrade(revision: str = "head") -> None:
    """Upgrade the database to `revision`."""
    command.upgrade(build_config(), revision)


def downgrade(revision: str) -> None:
    """Downgrade the database to `revision`."""
    command.downgrade(build_config(), revision)


def make_revision(message: str, *, autogenerate: bool = True) -> None:
    """Create a new migration script."""
    command.revision(build_config(), message=message, autogenerate=autogenerate)


@lru_cache(maxsize=1)
def code_head_revisions() -> tuple[str, ...]:
    """Return the head revision(s) declared in the migration scripts.

    Cached per-process since the scripts are static for the lifetime of a build.
    """
    return tuple(ScriptDirectory.from_config(build_config()).get_heads())


async def db_current_revisions(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[str, ...]:
    """Return the revision(s) currently applied in the database.

    Opens an isolated session so this read is independent of any caller's unit
    of work — Alembic's MigrationContext reads alembic_version directly, not
    through the ORM, and must not participate in an outer transaction.
    """
    async with session_factory() as session:
        connection = await session.connection()
        return tuple(
            await connection.run_sync(
                lambda c: MigrationContext.configure(c).get_current_heads()
            )
        )
