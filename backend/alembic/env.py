import asyncio
from logging.config import fileConfig
from typing import TYPE_CHECKING

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection
from app.modules.graph.adapters.persistence import models as graph_models  # noqa: F401
from app.platform.config import get_database_settings
from app.platform.database import Base

# this is the Alembic Config object, which provides access to values within
# the .ini file in use.
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", str(get_database_settings().database_url))

# `graph_models` above registers Node/Edge tables on `Base.metadata` before
# autogenerate runs - every future module's persistence models get the same
# import added here, per `backend/README.md`'s single-environment convention.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode, emitting SQL without a live connection."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Configure the migration context against an already-open connection."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and associate a connection with the migration context."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode, against a live async connection."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
