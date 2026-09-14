import json
import logging
from enum import StrEnum
from pathlib import Path
from typing import Annotated

from cyclopts import App, Parameter

from app.modules.media.adapters.cli.media_app import media_app
from app.platform.app_info import load_app_info
from app.platform.logging_config import configure_logging

configure_logging()
app_info = load_app_info()

BACKEND_SRC_PATH = Path(__file__).resolve().parents[3]

app = App(
    name=app_info.name,
    version=app_info.version,
)


@app.meta.default
def main(
    *tokens: Annotated[str, Parameter(show=False, allow_leading_hyphen=True)],
    verbose: Annotated[bool, Parameter(name=["--verbose", "-v"])] = False,
) -> None:
    """Menagerist CLI.

    Args:
        tokens: Remaining command-line tokens, forwarded to the command apps.
        verbose: Log at DEBUG level, overriding `LOG_LEVEL`.
    """
    if verbose:
        configure_logging(level=logging.DEBUG)
    app(tokens)


migrate_app = App(name="migrate", help="Manage database migrations.")
app.command(migrate_app)

app.command(media_app)

schema_app = App(name="schema", help="Inspect the API schema.")
app.command(schema_app)


@app.default
def shell() -> None:
    """Start the interactive shell."""
    app.interactive_shell(prompt=f"{app_info.name}> ")


@app.command
def help() -> None:
    """Display the help screen."""
    app.help_print()


class ServeLogLevel(StrEnum):
    """Mirrors `granian.log.LogLevels` without requiring granian to be imported.

    Granian is a heavy import (pulls in its Rust extension and server modules),
    so it is only imported inside `serve()`, when actually needed. This enum lets
    cyclopts validate and display `--log-level` choices without paying that cost
    for every other CLI command.
    """

    critical = "critical"
    error = "error"
    warning = "warning"
    warn = "warn"
    info = "info"
    debug = "debug"
    notset = "notset"


@app.command
def serve(
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    workers: int = 1,
    reload: bool = False,
    access_log: bool = True,
    log_level: ServeLogLevel = ServeLogLevel.info,
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
    from granian import Granian
    from granian.constants import Interfaces, Loops
    from granian.log import LogLevels

    from app.platform.logging_config import (
        GRANIAN_ACCESS_LOG_FORMAT,
        GRANIAN_LOG_DICTCONFIG,
    )

    server = Granian(
        target="app.entrypoints.api:app",
        address=host,
        port=port,
        interface=Interfaces.ASGI,
        workers=workers,
        reload=reload,
        reload_paths=[BACKEND_SRC_PATH],
        loop=Loops.auto,
        log_level=LogLevels(log_level.value),
        log_dictconfig=GRANIAN_LOG_DICTCONFIG,
        log_access=access_log,
        log_access_format=GRANIAN_ACCESS_LOG_FORMAT,
    )
    server.serve()


def _enable_migration_logs() -> None:
    logging.getLogger("alembic.runtime.migration").setLevel(logging.INFO)


@migrate_app.command
def upgrade(revision: str = "head") -> None:
    """Upgrade the database to `revision`.

    Args:
        revision: Target revision, or "head" for the latest.
    """
    from app.platform import alembic_runner

    _enable_migration_logs()
    alembic_runner.upgrade(revision)


@migrate_app.command
def downgrade(revision: str) -> None:
    """Downgrade the database to `revision`.

    Args:
        revision: Target revision.
    """
    from app.platform import alembic_runner

    _enable_migration_logs()
    alembic_runner.downgrade(revision)


@migrate_app.command
def revision(message: str, *, autogenerate: bool = True) -> None:
    """Create a new migration script.

    Args:
        message: Short description of the migration.
        autogenerate: Diff current models against the database schema.
    """
    from app.platform import alembic_runner

    alembic_runner.make_revision(message, autogenerate=autogenerate)


@schema_app.command
def dump(*, output: Path = Path("openapi.json")) -> None:
    """Write the API's OpenAPI schema to a file.

    Args:
        output: Path to write the schema JSON to.
    """
    from app.entrypoints.api import create_app

    output.write_text(json.dumps(create_app().openapi(), indent=2))


if __name__ == "__main__":
    app.meta()
