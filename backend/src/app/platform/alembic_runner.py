from pathlib import Path

from alembic.config import Config

from alembic import command
from app.platform.config import get_database_settings

_MIGRATIONS_PATH = Path(__file__).resolve().parents[3] / "alembic"
"""Where `alembic/` lives relative to this installed module.

Mirrors the `BACKEND_SRC_PATH` convention in `entrypoints/cli/__init__.py`.
Assumes `alembic/` sits alongside the package's source tree, true for
`uv run`/editable installs (dev + CI) - revisit once a packaged production
container needs to run migrations too.
"""


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
