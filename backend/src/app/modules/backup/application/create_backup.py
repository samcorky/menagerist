from contextlib import aclosing
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid7

import structlog

from app.modules.backup.application.permissions import BackupPermission
from app.modules.backup.application.verify_backup import verify_archive
from app.modules.backup.domain.backup import (
    BackupManifest,
    BackupSummary,
    MediaFileRef,
    TableDigest,
)
from app.modules.backup.domain.errors import CorruptBackupError, MediaFileMissingError
from app.shared_kernel.cqrs import AuthorisedUseCase

if TYPE_CHECKING:
    from app.modules.backup.ports.backup_store import BackupStore
    from app.modules.backup.ports.backup_writer import BackupWriter
    from app.modules.backup.ports.database_snapshot import DatabaseSnapshot
    from app.modules.backup.ports.media_files import MediaFiles
    from app.shared_kernel.actor import Actor
    from app.shared_kernel.authorisation import AuthorisationPort

logger = structlog.get_logger()


@dataclass(frozen=True, kw_only=True)
class CreateBackupCommand:
    """Create a verified instance archive by default."""

    label: str = "manual"
    verify: bool = True
    from_revision: str | None = None
    to_revision: str | None = None


class CreateBackup(
    AuthorisedUseCase[CreateBackupCommand, BackupSummary, BackupPermission]
):
    """Archive a consistent database snapshot and original media files."""

    required_permission = BackupPermission.CREATE

    def __init__(
        self,
        store: BackupStore,
        snapshot: DatabaseSnapshot,
        media: MediaFiles,
        authorisation: AuthorisationPort,
        *,
        app_version: str,
    ) -> None:
        super().__init__(authorisation)
        self._store = store
        self._snapshot = snapshot
        self._media = media
        self._app_version = app_version

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
                logger.warning("backup original media missing", asset_id=ref.asset_id)
            else:
                if digest.sha256 != ref.sha256 or digest.size != ref.size:
                    raise CorruptBackupError(
                        f"Media {ref.asset_id} has an incorrect hash or size."
                    )
        return missing

    async def _handle(
        self, request: CreateBackupCommand, actor: Actor
    ) -> BackupSummary:
        revision = await self._snapshot.schema_revision()
        backup_id = uuid7()
        writer = await self._store.begin(backup_id)
        try:
            tables = []
            async with aclosing(self._snapshot.export()) as members:
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
                    alembic_revision=revision,
                    label=request.label,
                    created_at=datetime.now(UTC),
                    created_by=actor.id,
                    tables=tables,
                    media=refs,
                    media_missing=missing,
                    from_revision=request.from_revision,
                    to_revision=request.to_revision,
                )
            )
            if request.verify:
                report = await verify_archive(self._store, backup_id)
                if report.findings:
                    await self._store.delete(backup_id)
                    raise CorruptBackupError(
                        "The new backup failed integrity verification."
                    )
        except BaseException:
            await writer.abort()
            raise
        logger.info(
            "instance backup created",
            backup_id=backup_id,
            label=request.label,
            actor_id=actor.id,
            size=stored.summary.size,
        )
        return stored.summary
