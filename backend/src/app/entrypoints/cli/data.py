import asyncio
import sys
from datetime import UTC, datetime, timedelta
from typing import Annotated

import structlog
from cyclopts import App, Parameter

from app.platform.cli_output import Report
from app.platform.cli_progress import activity, confirm

logger = structlog.get_logger(__name__)

data_app = App(name="data", help="Manage stored content.")


@data_app.command
def purge_deleted(
    *,
    older_than_days: int | None = None,
    dry_run: bool = False,
    yes: Annotated[bool, Parameter(name=["--yes", "-y"])] = False,
) -> Report:
    """Permanently delete content that has been in Recently deleted long enough.

    Covers every person's items, connections and collections, with the
    memberships, attachments and stored files that only they used. Live
    content is never touched. Safe to run repeatedly, for example from cron.

    Args:
        older_than_days: Purge what was deleted more than this many days ago, at
            least 1. Defaults to `MENAGERIST_RETENTION_DELETED_DAYS` (30).
        dry_run: Report what would be deleted and change nothing.
        yes: Do not ask for confirmation.
    """
    from app.entrypoints.cli.purge_deleted import (
        PurgeDeletedContentCommand,
        build_purge_deleted_content,
    )
    from app.platform.config.retention import get_retention_settings
    from app.shared_kernel.actor import SYSTEM_ACTOR

    if older_than_days is None:
        older_than_days = get_retention_settings().deleted_days
    elif older_than_days < 1:
        print("--older-than-days must be at least 1.", file=sys.stderr)
        raise SystemExit(1)

    cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
    logger.debug("starting deleted-content purge", cutoff=cutoff, dry_run=dry_run)

    if not dry_run:
        confirm(
            f"Delete for good what was removed before {cutoff:%Y-%m-%d %H:%M} UTC?",
            assume_yes=yes,
        )
    with activity("Looking through Recently deleted"):
        result = asyncio.run(
            build_purge_deleted_content().handle(
                PurgeDeletedContentCommand(older_than=cutoff, dry_run=dry_run),
                SYSTEM_ACTOR,
            )
        )
    logger.info(
        "deleted-content purge complete",
        dry_run=dry_run,
        items=result.items,
        connections=result.connections,
        collections=result.collections,
    )
    return Report(
        value={
            "message": "Dry run: nothing was deleted"
            if dry_run
            else "Deleted content purged",
            "cutoff": cutoff,
            "dry_run": dry_run,
            "items": result.items,
            "connections": result.connections,
            "collections": result.collections,
        },
        title="Deleted-content purge",
    )
