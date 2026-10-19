import hashlib
import io
import json
import tarfile
from typing import TYPE_CHECKING
from uuid import uuid7

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.entrypoints.api.shared.authorization import RoleAuthorizationAdapter
from app.entrypoints.api.shared.backup_media_files import BackupMediaFiles
from app.modules.backup.adapters.persistence.database_snapshot import (
    SqlAlchemyDatabaseSnapshot,
)
from app.modules.backup.adapters.persistence.table_rules import TABLE_RULES, TableRule
from app.modules.backup.adapters.storage.local_backup_store import (
    LocalDirectoryBackupStore,
)
from app.modules.backup.application.archive import parse_manifest
from app.modules.backup.application.create_backup import (
    CreateBackup,
    CreateBackupCommand,
)
from app.modules.backup.application.verify_backup import VerifyBackup, VerifyBackupQuery
from app.modules.backup.domain.errors import CorruptBackupError
from app.modules.backup.domain.verification import FindingKind
from app.modules.media.adapters.persistence.media_asset_repository import (
    SqlAlchemyMediaAssetRepository,
)
from app.modules.media.adapters.storage.local_filesystem import (
    LocalFilesystemMediaStorage,
)
from app.modules.media.domain.media_asset import MediaAsset
from app.shared_kernel.actor import SYSTEM_ACTOR

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    from sqlalchemy import Table
    from sqlalchemy.ext.asyncio import AsyncConnection

pytestmark = pytest.mark.integration


async def test_snapshot_reflects_old_schema_and_keeps_one_read_only_snapshot(
    snapshot_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reflection includes old columns and stable reads across concurrent commits."""
    engine = create_async_engine(snapshot_database)
    factory = async_sessionmaker(engine)
    snapshot = SqlAlchemyDatabaseSnapshot(factory)
    rows = snapshot._rows

    async def checked_rows(
        connection: AsyncConnection, table: Table
    ) -> AsyncIterator[bytes]:
        assert await connection.get_isolation_level() == "REPEATABLE READ"
        assert await connection.scalar(text("SHOW transaction_read_only")) == "on"
        async for chunk in rows(connection, table):
            yield chunk

    monkeypatch.setattr(snapshot, "_rows", checked_rows)
    try:
        async with engine.begin() as connection:
            # A live older schema can lack a column present in the current ORM.
            await connection.execute(text("ALTER TABLE users DROP COLUMN display_name"))
            await connection.execute(
                text("UPDATE alembic_version SET version_num = 'old-schema'")
            )
            await connection.execute(
                text(
                    """INSERT INTO users
                    (id, username, password_hash, role, password_expired,
                     disabled, created_at, updated_at) VALUES
                    (:id, 'archived', 'hash', 'admin', false, false, now(), now())"""
                ),
                {"id": uuid7()},
            )
        assert await snapshot.schema_revision() == "old-schema"
        members = {}
        async for member in snapshot.export():
            members[member.name] = b"".join([chunk async for chunk in member.chunks])
            if len(members) == 1:
                # A concurrent commit cannot leak into later table reads.
                async with engine.begin() as connection:
                    await connection.execute(
                        text("UPDATE users SET username = 'changed'")
                    )
        assert set(members) == {
            f"data/{name}.ndjson"
            for name, rule in TABLE_RULES.items()
            if rule is TableRule.KEEP
        }
        users = json.loads(members["data/users.ndjson"])
        assert users["username"] == "archived"
        assert "display_name" not in users
        assert members["data/presets.ndjson"]
        names = list(members)
        assert names.index("data/nodes.ndjson") < names.index("data/edges.ndjson")
        assert names.index("data/media_assets.ndjson") < names.index(
            "data/media_attachments.ndjson"
        )
    finally:
        await engine.dispose()


async def test_unclassified_live_table_fails_before_any_member(
    snapshot_database: str,
) -> None:
    """A schema addition cannot silently disappear from an instance backup."""
    engine = create_async_engine(snapshot_database)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("CREATE TABLE future_table (id integer)"))
        snapshot = SqlAlchemyDatabaseSnapshot(async_sessionmaker(engine))
        with pytest.raises(CorruptBackupError, match="future_table"):
            _ = [member async for member in snapshot.export()]
    finally:
        await engine.dispose()


async def test_real_instance_archive_verifies_and_reports_tampered_members(
    snapshot_database: str, tmp_path: Path
) -> None:
    """Real rows and originals verify, while tampered bytes produce findings."""
    engine = create_async_engine(snapshot_database)
    factory = async_sessionmaker(engine)
    try:
        async with factory() as session:
            owner_id = uuid7()
            await session.execute(
                text("""INSERT INTO users
                    (id, username, display_name, password_hash, role,
                     password_expired, disabled, created_at, updated_at) VALUES
                    (:id, 'archived', 'Archived administrator', 'hash', 'admin',
                     false, false, now(), now())"""),
                {"id": owner_id},
            )
            await session.execute(
                text("""INSERT INTO nodes
                    (id, owner_id, name, attributes, favourite, tags,
                     created_at, updated_at, deleted_at) VALUES
                    (:id, :owner_id, 'Archived item', '{}', false, '[]',
                     now(), now(), now())"""),
                {"id": uuid7(), "owner_id": owner_id},
            )
            repository = SqlAlchemyMediaAssetRepository(session)
            storage = LocalFilesystemMediaStorage(tmp_path / "media")
            media = BackupMediaFiles(repository, storage)
            payload = b"original media bytes"
            asset = MediaAsset.create(
                owner_id=owner_id,
                filename="original.png",
                content_type="image/png",
                size=len(payload),
                sha256=hashlib.sha256(payload).hexdigest(),
            )
            await repository.add(asset)
            await session.commit()

            async def chunks() -> AsyncIterator[bytes]:
                yield payload

            await storage.store(asset.id, asset.status, chunks())
            store = LocalDirectoryBackupStore(tmp_path / "backups")
            authorization = RoleAuthorizationAdapter()
            summary = await CreateBackup(
                store,
                SqlAlchemyDatabaseSnapshot(factory),
                media,
                authorization,
                app_version="test",
            ).handle(CreateBackupCommand(), SYSTEM_ACTOR)
            verifier = VerifyBackup(store, authorization)
            query = VerifyBackupQuery(backup_id=summary.id)
            assert not (await verifier.handle(query, SYSTEM_ACTOR)).findings

        archive_path = tmp_path / "backups" / "instance" / f"{summary.id}.tar.gz"
        original = archive_path.read_bytes()
        with tarfile.open(fileobj=io.BytesIO(original), mode="r:gz") as archive:
            entries = []
            for info in archive:
                stream = archive.extractfile(info)
                assert stream is not None
                entries.append((info.name, stream.read()))
        manifest = parse_manifest(dict(entries)["manifest.json"])
        assert {table.name for table in manifest.tables} == {
            name for name, rule in TABLE_RULES.items() if rule is TableRule.KEEP
        }
        assert manifest.media[0].asset_id == asset.id
        assert manifest.media[0].sha256 == asset.sha256
        assert json.loads(dict(entries)["data/users.ndjson"])["role"] == "admin"
        assert json.loads(dict(entries)["data/nodes.ndjson"])["deleted_at"] is not None
        for target in ("data/presets.ndjson", f"media/{asset.id}", "manifest.json"):
            buffer = io.BytesIO()
            with tarfile.open(
                fileobj=buffer, mode="w:gz", format=tarfile.PAX_FORMAT
            ) as archive:
                for name, content in entries:
                    if name == target:
                        content = content.replace(b"a", b"b", 1)
                        if name.startswith("media/"):
                            content = b"tampered"
                    info = tarfile.TarInfo(name)
                    info.size = len(content)
                    archive.addfile(info, io.BytesIO(content))
            archive_path.write_bytes(buffer.getvalue())
            sidecar = archive_path.with_suffix("").with_suffix(".sha256")
            digest = hashlib.sha256(buffer.getvalue()).hexdigest()
            sidecar.write_text(f"{digest}  {archive_path.name}\n")
            report = await verifier.handle(query, SYSTEM_ACTOR)
            assert any(finding.member == target for finding in report.findings)
        archive_path.write_bytes(original)
        sidecar.write_text(f"{'0' * 64}  {archive_path.name}\n")
        report = await verifier.handle(query, SYSTEM_ACTOR)
        assert any(
            finding.kind is FindingKind.ARCHIVE_DIGEST_MISMATCH
            for finding in report.findings
        )
        sidecar.write_text(
            f"{hashlib.sha256(original).hexdigest()}  {archive_path.name}\n"
        )
        archive_path.write_bytes(original + b"extra bytes")
        report = await verifier.handle(query, SYSTEM_ACTOR)
        assert report.findings
    finally:
        await engine.dispose()
