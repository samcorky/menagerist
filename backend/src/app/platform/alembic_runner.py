from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

from app.platform.config import get_database_settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

_MIGRATIONS_PATH = Path(__file__).resolve().parent.parent / "alembic"


def build_config() -> Config:
    """Build an Alembic Config pointed at backend migrations and database."""
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
    """Return the head revision(s) declared in migration scripts."""
    return tuple(ScriptDirectory.from_config(build_config()).get_heads())


async def db_current_revisions(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[str, ...]:
    """Return the revision(s) currently applied in the database."""
    async with session_factory() as session:
        connection = await session.connection()
        return tuple(
            await connection.run_sync(
                lambda c: MigrationContext.configure(c).get_current_heads()
            )
        )
