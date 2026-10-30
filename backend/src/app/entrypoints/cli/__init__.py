import asyncio
import json
import logging
import sys
from contextlib import nullcontext
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal

import structlog
from cyclopts import App, Parameter

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.entrypoints.api.shared.backup_operations import create_backup
from app.entrypoints.api.shared.settings_reader import get_settings_reader
from app.entrypoints.cli.backups import (
    export_user_data,
    import_user_data,
    restore_backup,
)
from app.entrypoints.cli.data import data_app
from app.entrypoints.cli.scheduling import (
    check_worker_health_cli,
    list_jobs_cli,
    run_job_cli,
    run_worker_cli,
)
from app.modules.backup.adapters.cli.backup_app import (
    backup_app,
    use_access_guard as use_backup_access_guard,
    use_operations,
    use_settings_reader as use_backup_settings_reader,
    use_user_operations,
)
from app.modules.identity.adapters.cli.identity_app import (
    identity_app,
    use_access_guard,
    use_existing_data_claim,
)
from app.modules.media.adapters.cli.media_app import media_app
from app.modules.scheduling.adapters.cli.job_app import (
    job_app,
    use_operations as use_job_operations,
)
from app.platform.app_info import load_app_info
from app.platform.cli_output import RESULT_ACTION, OutputFormat, Report, set_format
from app.platform.cli_progress import activity, confirm
from app.platform.logging_config import configure_logging

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.modules.identity.ports.existing_data_claim import ExistingDataClaim

configure_logging()
app_info = load_app_info()
logger = structlog.get_logger(__name__)

BACKEND_SRC_PATH = Path(__file__).resolve().parents[3]

app = App(
    name=app_info.name,
    version=app_info.version,
    result_action=RESULT_ACTION,
)


app.meta.result_action = RESULT_ACTION


def _runs_until_stopped(tokens: tuple[str, ...]) -> bool:
    remaining = iter(tokens)
    for token in remaining:
        if token == "--format":
            next(remaining, None)  # its value is not the command
        elif not token.startswith("-"):
            return token in {"serve", "worker"}
    return False


@app.meta.default
def main(
    *tokens: Annotated[str, Parameter(show=False, allow_leading_hyphen=True)],
    verbose: Annotated[bool, Parameter(name=["--verbose", "-v"])] = False,
    quiet: Annotated[bool, Parameter(name=["--quiet", "-q"])] = False,
    output_format: Annotated[
        OutputFormat, Parameter(name="--format")
    ] = OutputFormat.AUTO,
    json_output: Annotated[bool, Parameter(name="--json", negative="")] = False,
) -> object:
    """Menagerist CLI.

    Args:
        tokens: Remaining command-line tokens, forwarded to the command apps.
        verbose: Log at DEBUG level, overriding `LOG_LEVEL`.
        quiet: Log only errors.
        output_format: How results are shown: `rich` (tables, the default on a
            terminal), `text` (plain lines, the default when piped) or `json`.
        json_output: Show results as JSON; the same as `--format json`.
    """
    if verbose and quiet:
        raise SystemExit("--verbose and --quiet cannot be used together.")
    if json_output and output_format not in (OutputFormat.AUTO, OutputFormat.JSON):
        raise SystemExit("--json cannot be combined with --format other than json.")
    set_format(OutputFormat.JSON if json_output else output_format)
    # Results own stdout. Only the commands a container runs keep logging there.
    stream = sys.stdout if _runs_until_stopped(tokens) else sys.stderr
    level = logging.DEBUG if verbose else logging.ERROR if quiet else None
    configure_logging(level=level, stream=stream)
    return app(tokens)


migrate_app = App(name="migrate", help="Manage database migrations.")
app.command(migrate_app)

app.command(media_app)
app.command(data_app)
use_job_operations(list_jobs_cli, run_job_cli)
app.command(job_app)
use_backup_access_guard(get_access_guard())
use_backup_settings_reader(get_settings_reader)

use_operations(
    lambda label: create_backup(label=label),
    lambda backup_id, replace, guard: restore_backup(
        backup_id, replace=replace, guard=guard
    ),
)
use_user_operations(export_user_data, import_user_data)
app.command(backup_app)


@app.command
def worker(*, identity_file: Path | None = None) -> None:
    """Run recurring and queued jobs until the process receives a stop signal.

    Args:
        identity_file: Process identity shared with worker-health; defaults to /tmp
            in the container. Use a separate path for each local worker.
    """
    if identity_file is None:
        asyncio.run(run_worker_cli())
    else:
        asyncio.run(run_worker_cli(identity_file=identity_file))


@app.command(name="worker-health")
def worker_health(*, identity_file: Path | None = None) -> Report:
    """Check this worker process's heartbeat; exit with one when unhealthy.

    Args:
        identity_file: The identity file used by the worker being checked.
    """
    # Docker stores probe output; asyncio.run logs its event loop at DEBUG.
    logging.getLogger("asyncio").setLevel(logging.INFO)
    if asyncio.run(check_worker_health_cli(identity_file=identity_file)):
        return Report(
            value={"message": "Worker is healthy.", "healthy": True},
            title="Worker health",
        )
    return Report(
        value={
            "message": "Worker is unhealthy: no recent heartbeat for this process.",
            "healthy": False,
        },
        title="Worker health",
        exit_code=1,
    )


def _claim_existing_data(session: AsyncSession) -> ExistingDataClaim:
    """Build the claim identity cannot build itself: it spans the other modules."""
    from app.entrypoints.api.shared.bridges.claim_existing_data import (
        build_sql_claim_existing_data,
    )

    return build_sql_claim_existing_data(session)


use_existing_data_claim(_claim_existing_data)
use_access_guard(get_access_guard())
app.command(identity_app)

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


def _check_workers(_type: type, value: int | str) -> None:
    """Cyclopts validator: `auto`, or a worker count inside the supported range."""
    from app.platform.connection_budget import validate_workers

    if value is not None and value != "auto":
        validate_workers(int(value))


def _warn_if_connections_exceed_limit(workers: int) -> None:
    """Log a warning when the pools could outgrow Postgres' `max_connections`."""
    from app.platform import connection_budget

    limit = asyncio.run(connection_budget.fetch_max_connections())
    if limit is None:
        return
    if message := connection_budget.connection_warning(
        workers=workers, max_connections=limit
    ):
        logger.warning(message)


@app.command
def serve(
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    workers: Annotated[
        int | Literal["auto"] | None, Parameter(validator=_check_workers)
    ] = None,
    reload: bool = False,
    access_log: bool = False,
    log_level: ServeLogLevel = ServeLogLevel.info,
    migrate: bool = False,
    backup: bool = True,
) -> None:
    """Run the API server.

    Args:
        host: Address to bind the server to.
        port: Port to bind the server to.
        workers: Number of worker processes, 1 to 16, or `auto` for one per CPU
            core on a host and one in a container or when reloading. Defaults to
            the `server.workers` setting (`MENAGERIST_SERVER_WORKERS`, `auto`).
        reload: Restart workers when application code changes.
        access_log: Also write Granian's own access line. Off by default because
            the API logs one access line per request itself (with the user and
            session ids); `MENAGERIST_LOG_ACCESS=false` turns that one off.
        log_level: Minimum level for Granian's own server logs.
        backup: Honour the configured pre-migration backup policy.
        migrate: Apply pending database migrations before starting. Meant for
            single-instance deployments; run `migrate upgrade` separately when
            several instances share one database.
    """
    from granian import Granian
    from granian.constants import Interfaces, Loops
    from granian.log import LogLevels

    from app.platform.logging_config import (
        GRANIAN_ACCESS_LOG_FORMAT,
        granian_log_dictconfig,
    )

    if migrate:
        upgrade(backup=backup)
    from app.platform import worker_count
    from app.platform.config import get_server_settings

    server_settings = get_server_settings()
    workers = worker_count.resolve_workers(
        server_settings.workers if workers is None else workers,
        container=reload or worker_count.in_container(server_settings.in_container),
        cpus=worker_count.available_cpus(),
    )
    _warn_if_connections_exceed_limit(workers)

    server = Granian(
        target="app.entrypoints.api.application:app",
        address=host,
        port=port,
        interface=Interfaces.ASGI,
        workers=workers,
        reload=reload,
        reload_paths=[BACKEND_SRC_PATH],
        loop=Loops.auto,
        log_level=LogLevels(log_level.value),
        log_dictconfig=granian_log_dictconfig(),
        log_access=access_log,
        log_access_format=GRANIAN_ACCESS_LOG_FORMAT,
    )
    server.serve()


def _enable_migration_logs() -> bool:
    """Show alembic's step lines unless `-q` asked for quiet; say whether they show."""
    if logging.getLogger().getEffectiveLevel() > logging.INFO:
        return False
    logging.getLogger("alembic.runtime.migration").setLevel(logging.INFO)
    return True


@migrate_app.command
def upgrade(revision: str = "head", *, backup: bool = True) -> dict[str, object]:
    """Upgrade the database to `revision`.

    Args:
        revision: Target revision, or "head" for the latest.
        backup: Honour the configured pre-migration backup policy.
    """
    steps_shown = _enable_migration_logs()
    logger.debug("starting database upgrade", revision=revision)
    from app.entrypoints.cli.backups import upgrade_with_backup

    # With the step lines hidden, a spinner shows that something is happening.
    with nullcontext() if steps_shown else activity("Upgrading the database"):
        upgrade_with_backup(revision, backup=backup)
    logger.info("database upgrade complete", revision=revision)
    return {"message": "Database upgraded", "revision": revision, "backup": backup}


@migrate_app.command
def downgrade(
    revision: str, *, yes: Annotated[bool, Parameter(name=["--yes", "-y"])] = False
) -> dict[str, object]:
    """Downgrade the database to `revision`.

    Args:
        revision: Target revision.
        yes: Do not ask for confirmation.
    """
    from app.platform import alembic_runner

    confirm(f"Downgrade the database to {revision}? Data may be lost.", assume_yes=yes)
    _enable_migration_logs()
    logger.debug("starting database downgrade", revision=revision)
    alembic_runner.downgrade(revision)
    logger.info("database downgrade complete", revision=revision)
    return {"message": "Database downgraded", "revision": revision}


@migrate_app.command
def revision(message: str, *, autogenerate: bool = True) -> dict[str, object]:
    """Create a new migration script.

    Args:
        message: Short description of the migration.
        autogenerate: Diff current models against the database schema.
    """
    from app.platform import alembic_runner

    logger.debug(
        "starting migration revision", message=message, autogenerate=autogenerate
    )
    alembic_runner.make_revision(message, autogenerate=autogenerate)
    logger.info("migration revision complete", message=message)
    return {
        "message": "Migration created",
        "description": message,
        "autogenerate": autogenerate,
    }


@schema_app.command
def dump(*, output: Path = Path("openapi.json")) -> dict[str, object]:
    """Write the API's OpenAPI schema to a file.

    Args:
        output: Path to write the schema JSON to.
    """
    from app.entrypoints.api import create_app

    logger.debug("dumping API schema", output=str(output))
    output.write_text(json.dumps(create_app().openapi(), indent=2))
    logger.info("schema dump complete", output=str(output))
    return {
        "message": "OpenAPI schema written",
        "output": output,
        "size": output.stat().st_size,
    }


if __name__ == "__main__":
    app.meta()
