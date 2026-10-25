import asyncio
import sys
from datetime import UTC, datetime, timedelta

import structlog
from cyclopts import App

logger = structlog.get_logger(__name__)

data_app = App(name="data", help="Manage stored content.")


@data_app.command
def purge_deleted(*, older_than_days: int | None = None, dry_run: bool = False) -> None:
    """Permanently delete content that has been in Recently deleted long enough.

    Covers every person's items, connections and collections, with the
    memberships, attachments and stored files that only they used. Live
    content is never touched. Safe to run repeatedly, for example from cron.

    Args:
        older_than_days: Purge what was deleted more than this many days ago, at
            least 1. Defaults to `MENAGERIST_DELETED_RETENTION_DAYS` (30).
        dry_run: Report what would be deleted and change nothing.
    """
    from app.entrypoints.cli.purge_deleted import (
        PurgeDeletedContentCommand,
        build_purge_deleted_content,
    )
    from app.platform.config.retention import get_retention_settings
    from app.shared_kernel.actor import SYSTEM_ACTOR

    if older_than_days is None:
        older_than_days = get_retention_settings().deleted_retention_days
    elif older_than_days < 1:
        print("--older-than-days must be at least 1.", file=sys.stderr)
        raise SystemExit(1)

    cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
    logger.debug("starting deleted-content purge", cutoff=cutoff, dry_run=dry_run)

    result = asyncio.run(
        build_purge_deleted_content().handle(
            PurgeDeletedContentCommand(older_than=cutoff, dry_run=dry_run),
            SYSTEM_ACTOR,
        )
    )
    print(f"Cutoff (UTC): {cutoff:%Y-%m-%d %H:%M}")
    print(f"{'Would delete' if dry_run else 'Deleted'}:")
    print(f"  Items:       {result.items}")
    print(f"  Connections: {result.connections}")
    print(f"  Collections: {result.collections}")
    if dry_run:
        print("Dry run: nothing was deleted")
    logger.info(
        "deleted-content purge complete",
        dry_run=dry_run,
        items=result.items,
        connections=result.connections,
        collections=result.collections,
    )
