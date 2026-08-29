from pathlib import Path

from alembic.config import Config

from alembic import command
from app.platform.config import get_database_settings

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
