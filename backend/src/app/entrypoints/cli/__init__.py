import json
from pathlib import Path

import structlog
from cyclopts import App
from granian import Granian
from granian.constants import Interfaces, Loops
from granian.log import LogLevels

from app.platform import alembic_runner
from app.platform.app_info import load_app_info
from app.platform.logging_config import GRANIAN_LOG_DICTCONFIG, configure_logging

configure_logging()
app_info = load_app_info()

logger = structlog.get_logger(__name__)

BACKEND_SRC_PATH = Path(__file__).resolve().parents[3]

app = App(
    name=app_info.name,
    version=app_info.version,
)

migrate_app = App(name="migrate", help="Manage database migrations.")
app.command(migrate_app)

schema_app = App(name="schema", help="Inspect the API schema.")
app.command(schema_app)


@app.command
def serve(
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    workers: int = 1,
    reload: bool = False,
    access_log: bool = True,
    log_level: LogLevels = LogLevels.info,
) -> None:
    """Run the API server.

    Args:
        host: Address to bind the server to.
        port: Port to bind the server to.
        workers: Number of worker processes.
        reload: Restart workers when application code changes.
        access_log: Whether to log access events.
        log_level: Minimum level for Granian's own server logs.
    """
    server = Granian(
        target="app.entrypoints.api:app",
        address=host,
        port=port,
        interface=Interfaces.ASGI,
        workers=workers,
        reload=reload,
        reload_paths=[BACKEND_SRC_PATH],
        loop=Loops.auto,
        log_level=log_level,
        log_dictconfig=GRANIAN_LOG_DICTCONFIG,
        log_access=access_log,
    )
    logger.info(BACKEND_SRC_PATH)
    server.serve()


@migrate_app.command
def upgrade(revision: str = "head") -> None:
    """Upgrade the database to `revision`.

    Args:
        revision: Target revision, or "head" for the latest.
    """
    alembic_runner.upgrade(revision)


@migrate_app.command
def downgrade(revision: str) -> None:
    """Downgrade the database to `revision`.

    Args:
        revision: Target revision.
    """
    alembic_runner.downgrade(revision)


@migrate_app.command
def revision(message: str, *, autogenerate: bool = True) -> None:
    """Create a new migration script.

    Args:
        message: Short description of the migration.
        autogenerate: Diff current models against the database schema.
    """
    alembic_runner.make_revision(message, autogenerate=autogenerate)


@schema_app.command
def dump(*, output: Path = Path("openapi.json")) -> None:
    """Write the API's OpenAPI schema to a file.

    No live server is needed - this builds the same FastAPI app `serve` does
    and reads its schema directly, so the frontend can generate a typed
    client without a running backend.

    Args:
        output: Path to write the schema JSON to.
    """
    from app.entrypoints.api import create_app

    output.write_text(json.dumps(create_app().openapi(), indent=2))


if __name__ == "__main__":
    app()
