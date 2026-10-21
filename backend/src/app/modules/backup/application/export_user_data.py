from contextlib import aclosing
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID, uuid7

import structlog

from app.modules.backup.application.verify_backup import verify_archive
from app.modules.backup.domain.backup import (
    BackupManifest,
    BackupScope,
    BackupSummary,
    TableDigest,
)
from app.modules.backup.domain.errors import CorruptBackupError, MediaFileMissingError
from app.modules.backup.ports.user_database_snapshot import UserDatabaseSnapshot
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.cqrs import ScopedCommandHandler

if TYPE_CHECKING:
    from app.modules.backup.domain.backup import MediaFileRef
    from app.modules.backup.ports.backup_store import BackupStore
    from app.modules.backup.ports.backup_writer import BackupWriter
    from app.modules.backup.ports.media_files import MediaFiles
    from app.shared_kernel.access_policy import AccessPolicy
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


async def prune_user_exports(store: BackupStore, *, older_than: datetime) -> list[UUID]:
    """Delete expired exports from the supplied private owner namespace."""
    expired = [
        summary.id for summary in await store.list() if summary.created_at < older_than
    ]
    for backup_id in expired:
        await store.delete(backup_id)
    return expired


@dataclass(frozen=True, kw_only=True)
class ExportUserDataCommand:
    """Create a verified portable archive of the caller's content."""


class ExportUserData(
    ScopedCommandHandler[UserDatabaseSnapshot, ExportUserDataCommand, BackupSummary]
):
    """Export personal content through a private per-owner archive store."""

    def __init__(
        self,
        store: BackupStore,
        snapshot: UserDatabaseSnapshot,
        media: MediaFiles,
        policy: AccessPolicy,
        *,
        app_version: str,
        ttl_hours: int = 24,
    ) -> None:
        super().__init__(snapshot, policy)
        self._store, self._snapshot, self._media = store, snapshot, media
        self._app_version = app_version
        self._ttl = timedelta(hours=ttl_hours)

    async def _add_media(
        self, writer: BackupWriter, refs: list[MediaFileRef]
    ) -> list[UUID]:
        missing = []
        for ref in refs:
            try:
                digest = await writer.add(
                    f"media/{ref.asset_id}", self._media.open(ref)
                )
            except MediaFileMissingError:
                missing.append(ref.asset_id)
            else:
                if digest.sha256 != ref.sha256 or digest.size != ref.size:
                    raise CorruptBackupError(
                        "A media original has an incorrect hash or size."
                    )
        return missing

    async def handle(
        self, request: ExportUserDataCommand, actor: Actor
    ) -> BackupSummary:
        """Scope every snapshot to the signed-in actor, including administrators."""
        self._policy.assert_can_view(actor, actor.id)
        scope = self._policy.scope_for(actor)
        if scope.is_everyone:
            scope = ContentFilter.of(actor.id)
        await prune_user_exports(self._store, older_than=datetime.now(UTC) - self._ttl)
        writer = await self._store.begin(uuid7())
        try:
            tables = []
            async with aclosing(self._snapshot.export(scope=scope)) as members:
                async for member in members:
                    digest = await writer.add(member.name, member.chunks)
                    tables.append(
                        TableDigest(
                            name=member.name.removeprefix("data/").removesuffix(
                                ".ndjson"
                            ),
                            rows=digest.lines,
                            sha256=digest.sha256,
                        )
                    )
            refs = await self._media.list_files()
            missing = await self._add_media(writer, refs)
            stored = await writer.finish(
                BackupManifest(
                    app_version=self._app_version,
                    alembic_revision=await self._snapshot.schema_revision(),
                    label="user-export",
                    scope=BackupScope.USER,
                    owner_id=actor.id,
                    created_by=actor.id,
                    created_at=datetime.now(UTC),
                    tables=tables,
                    media=refs,
                    media_missing=missing,
                )
            )
            if (await verify_archive(self._store, stored.summary.id)).findings:
                await self._store.delete(stored.summary.id)
                raise CorruptBackupError(
                    "The new export failed integrity verification."
                )
        except BaseException:
            await writer.abort()
            raise
        logger.info(
            "user data exported", actor_id=actor.id, backup_id=stored.summary.id
        )
        return stored.summary
