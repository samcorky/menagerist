import asyncio
import hashlib
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid7

import pytest
from sqlalchemy import create_engine, make_url, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.entrypoints.api.shared.backup_media_files import BackupMediaFiles
from app.modules.backup.adapters.persistence.database_restorer import (
    SqlAlchemyDatabaseRestorer,
)
from app.modules.backup.adapters.persistence.database_snapshot import (
    SqlAlchemyDatabaseSnapshot,
)
from app.modules.backup.adapters.storage.local_backup_store import (
    LocalDirectoryBackupStore,
)
from app.modules.backup.adapters.storage.local_backup_workspace import (
    LocalBackupWorkspace,
)
from app.modules.backup.application.create_backup import (
    CreateBackup,
    CreateBackupCommand,
)
from app.modules.backup.application.restore_backup import (
    RestoreBackup,
    RestoreBackupCommand,
)
from app.modules.backup.domain.errors import CorruptBackupError, IncompatibleBackupError
from app.modules.graph.adapters.persistence.node_repository import (
    SqlAlchemyNodeRepository,
)
from app.modules.graph.domain.node import Node
from app.modules.identity.adapters.persistence.user_repository import (
    SqlAlchemyUserRepository,
)
from app.modules.identity.adapters.security.scrypt_password_hasher import (
    ScryptPasswordHasher,
)
from app.modules.identity.domain.user import Role, User
from app.modules.media.adapters.persistence.in_memory_media_asset_repository import (
    InMemoryMediaAssetRepository,
)
from app.modules.media.adapters.storage.local_filesystem import (
    LocalFilesystemMediaStorage,
)
from app.modules.media.domain.media_asset import MediaAsset
from app.platform import alembic_runner
from app.platform.config import get_database_settings
from app.shared_kernel.actor import SYSTEM_ACTOR

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Coroutine

pytestmark = pytest.mark.integration

# Adjacent real migrations: the first schema change since the initial release
# moved the favourite flag off the item into its own per-user table.
PRE_FAVOURITES_REVISION = "e6f7a8b9c0d1"
FAVOURITES_REVISION = "b7c4e91a2d58"


async def _chunks(data: bytes) -> AsyncIterator[bytes]:
    yield data


async def _scratch_database(
    postgres_url: str,
    postgres_sync_url: str,
    monkeypatch: pytest.MonkeyPatch,
    *,
    revision: str,
) -> tuple[str, Coroutine[Any, Any, None]]:
    """Create and migrate a scratch database to an explicit revision."""
    name = f"backup_{uuid7().hex}"
    engine = create_engine(postgres_sync_url, isolation_level="AUTOCOMMIT")
    with engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    url = (
        make_url(postgres_url).set(database=name).render_as_string(hide_password=False)
    )
    with monkeypatch.context() as patch:
        patch.setenv("MENAGERIST_DATABASE_URL", url)
        get_database_settings.cache_clear()
        # Alembic's env.py starts its own event loop, so it needs a thread.
        await asyncio.to_thread(alembic_runner.upgrade, revision)
    get_database_settings.cache_clear()

    async def _drop() -> None:
        with engine.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        engine.dispose()

    return url, _drop()


async def test_restore_into_empty_database_round_trips(
    snapshot_database: str,
) -> None:
    """A backup of an empty instance restores cleanly onto another empty one."""
    engine = create_async_engine(snapshot_database)
    try:
        factory = async_sessionmaker(engine)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            backup_store = LocalDirectoryBackupStore(root)
            media = BackupMediaFiles(
                InMemoryMediaAssetRepository(),
                LocalFilesystemMediaStorage(root / "media"),
            )
            backup = await CreateBackup(
                backup_store,
                SqlAlchemyDatabaseSnapshot(factory),
                media,
                get_access_guard(),
                app_version="test",
            ).handle(CreateBackupCommand(), SYSTEM_ACTOR)

            restorer = SqlAlchemyDatabaseRestorer(factory)
            revision_before = await restorer.schema_revision()
            await RestoreBackup(
                backup_store,
                restorer,
                media,
                LocalBackupWorkspace(root),
                get_access_guard(),
            ).handle(
                RestoreBackupCommand(backup_id=backup.id, replace=False),
                SYSTEM_ACTOR,
            )
            assert await restorer.schema_revision() == revision_before
            assert await restorer.is_empty()
    finally:
        await engine.dispose()


async def test_restore_with_items_and_media_round_trips(
    snapshot_database: str, tmp_path: Path
) -> None:
    """Items, their favourites and attached media all come back through a restore."""
    engine = create_async_engine(snapshot_database)
    factory = async_sessionmaker(engine)
    try:
        hasher = ScryptPasswordHasher()
        user = User.create(
            username="collector",
            display_name="Collector",
            password_hash=hasher.hash("password"),
            role=Role.ADMIN,
            now=datetime.now(UTC),
        )
        node = Node.create(owner_id=user.id, name="Alien", type="film", favourite=True)
        async with factory.begin() as session:
            await SqlAlchemyUserRepository(session).add(user)
            await SqlAlchemyNodeRepository(session).add(node)

        assets = InMemoryMediaAssetRepository()
        asset = MediaAsset.create(
            owner_id=user.id,
            filename="poster.bin",
            content_type="application/octet-stream",
            size=3,
            sha256=hashlib.sha256(b"art").hexdigest(),
        )
        await assets.add(asset)
        source_media = BackupMediaFiles(
            assets, LocalFilesystemMediaStorage(tmp_path / "source-media")
        )
        ref = (await source_media.list_files())[0]
        await source_media.write(ref, _chunks(b"art"))

        store = LocalDirectoryBackupStore(tmp_path / "backups")
        backup = await CreateBackup(
            store,
            SqlAlchemyDatabaseSnapshot(factory),
            source_media,
            get_access_guard(),
            app_version="test",
        ).handle(CreateBackupCommand(), SYSTEM_ACTOR)

        async with engine.begin() as connection:
            await connection.execute(text("DELETE FROM node_favourites"))
            await connection.execute(text("DELETE FROM nodes"))
            await connection.execute(text("DELETE FROM users"))

        target_media = BackupMediaFiles(
            assets, LocalFilesystemMediaStorage(tmp_path / "target-media")
        )
        await RestoreBackup(
            store,
            SqlAlchemyDatabaseRestorer(factory),
            target_media,
            LocalBackupWorkspace(tmp_path / "backups"),
            get_access_guard(),
        ).handle(
            RestoreBackupCommand(backup_id=backup.id, replace=True),
            SYSTEM_ACTOR,
        )

        async with engine.connect() as connection:
            assert (
                await connection.scalar(
                    text("SELECT username FROM users WHERE id = :id"),
                    {"id": user.id},
                )
                == "collector"
            )
            assert (
                await connection.scalar(
                    text("SELECT name FROM nodes WHERE id = :id"), {"id": node.id}
                )
                == "Alien"
            )
            favourite_count = await connection.scalar(
                text(
                    """
                    SELECT count(*) FROM node_favourites
                    WHERE user_id = :uid AND node_id = :nid
                    """
                ),
                {"uid": user.id, "nid": node.id},
            )
            assert favourite_count == 1
        restored = b"".join([chunk async for chunk in target_media.open(ref)])
        assert restored == b"art"
    finally:
        await engine.dispose()


async def test_restore_refused_across_a_real_migration(
    postgres_url: str, postgres_sync_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pre-migration archive restores onto its own revision but not past it.

    Models the documented rollback procedure in docs/DEPLOYING.md against the
    real favourites migration (e6f7a8b9c0d1 -> b7c4e91a2d58): back up at the
    older revision, migrate forward for real, then confirm the archive is
    refused on the newer revision (even with replace=True) and still restores
    cleanly onto a fresh database pinned at the revision it was taken at.
    """
    old_url, drop_old = await _scratch_database(
        postgres_url, postgres_sync_url, monkeypatch, revision=PRE_FAVOURITES_REVISION
    )
    engine = create_async_engine(old_url)
    try:
        factory = async_sessionmaker(engine)
        hasher = ScryptPasswordHasher()
        user = User.create(
            username="archivist",
            display_name="Archivist",
            password_hash=hasher.hash("password"),
            role=Role.ADMIN,
            now=datetime.now(UTC),
        )
        async with factory.begin() as session:
            await SqlAlchemyUserRepository(session).add(user)
        node_id = uuid7()
        async with engine.begin() as connection:
            # The ORM repository targets head's schema (node_favourites), not
            # this older revision's `nodes.favourite` column, so insert directly.
            await connection.execute(
                text(
                    """
                    INSERT INTO nodes
                        (id, owner_id, name, attributes, favourite, tags,
                         created_at, updated_at)
                    VALUES
                        (:id, :owner_id, 'Alien', '{}', true, '[]', now(), now())
                    """
                ),
                {"id": node_id, "owner_id": user.id},
            )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = LocalDirectoryBackupStore(root)
            media = BackupMediaFiles(
                InMemoryMediaAssetRepository(),
                LocalFilesystemMediaStorage(root / "media"),
            )
            pre_migration_revision = await SqlAlchemyDatabaseRestorer(
                factory
            ).schema_revision()
            assert pre_migration_revision == PRE_FAVOURITES_REVISION
            backup = await CreateBackup(
                store,
                SqlAlchemyDatabaseSnapshot(factory),
                media,
                get_access_guard(),
                app_version="test",
            ).handle(
                CreateBackupCommand(
                    label="pre-migration",
                    from_revision=pre_migration_revision,
                    to_revision=FAVOURITES_REVISION,
                ),
                SYSTEM_ACTOR,
            )

            with monkeypatch.context() as patch:
                patch.setenv("MENAGERIST_DATABASE_URL", old_url)
                get_database_settings.cache_clear()
                await asyncio.to_thread(alembic_runner.upgrade, FAVOURITES_REVISION)
            get_database_settings.cache_clear()

            async with engine.connect() as connection:
                migrated_favourite_count = await connection.scalar(
                    text("SELECT count(*) FROM node_favourites WHERE user_id = :uid"),
                    {"uid": user.id},
                )
            assert migrated_favourite_count == 1

            restorer_after_migration = SqlAlchemyDatabaseRestorer(factory)
            assert (
                await restorer_after_migration.schema_revision() == FAVOURITES_REVISION
            )
            for replace in (False, True):
                with pytest.raises(IncompatibleBackupError):
                    await RestoreBackup(
                        store,
                        restorer_after_migration,
                        media,
                        LocalBackupWorkspace(root),
                        get_access_guard(),
                    ).handle(
                        RestoreBackupCommand(backup_id=backup.id, replace=replace),
                        SYSTEM_ACTOR,
                    )

            rollback_url, drop_rollback = await _scratch_database(
                postgres_url,
                postgres_sync_url,
                monkeypatch,
                revision=PRE_FAVOURITES_REVISION,
            )
            rollback_engine = create_async_engine(rollback_url)
            try:
                rollback_factory = async_sessionmaker(rollback_engine)
                await RestoreBackup(
                    store,
                    SqlAlchemyDatabaseRestorer(rollback_factory),
                    media,
                    LocalBackupWorkspace(root),
                    get_access_guard(),
                ).handle(
                    RestoreBackupCommand(backup_id=backup.id, replace=False),
                    SYSTEM_ACTOR,
                )
                async with rollback_engine.connect() as connection:
                    assert (
                        await connection.scalar(
                            text("SELECT username FROM users WHERE id = :id"),
                            {"id": user.id},
                        )
                        == "archivist"
                    )
                    assert (
                        await connection.scalar(
                            text("SELECT favourite FROM nodes WHERE owner_id = :id"),
                            {"id": user.id},
                        )
                        is True
                    )
            finally:
                await rollback_engine.dispose()
                await drop_rollback
    finally:
        await engine.dispose()
        await drop_old


async def test_restore_refuses_a_truncated_archive(
    snapshot_database: str, tmp_path: Path
) -> None:
    """A truncated archive is refused without touching the database."""
    engine = create_async_engine(snapshot_database)
    try:
        factory = async_sessionmaker(engine)
        hasher = ScryptPasswordHasher()
        user = User.create(
            username="intact",
            display_name="Intact",
            password_hash=hasher.hash("password"),
            role=Role.ADMIN,
            now=datetime.now(UTC),
        )
        async with factory.begin() as session:
            await SqlAlchemyUserRepository(session).add(user)

        store = LocalDirectoryBackupStore(tmp_path / "backups")
        media = BackupMediaFiles(
            InMemoryMediaAssetRepository(),
            LocalFilesystemMediaStorage(tmp_path / "media"),
        )
        backup = await CreateBackup(
            store,
            SqlAlchemyDatabaseSnapshot(factory),
            media,
            get_access_guard(),
            app_version="test",
        ).handle(CreateBackupCommand(), SYSTEM_ACTOR)

        archive_path = tmp_path / "backups" / "instance" / f"{backup.id}.tar.gz"
        original = archive_path.read_bytes()
        archive_path.write_bytes(original[: len(original) // 2])

        async with engine.connect() as connection:
            before = await connection.scalar(text("SELECT count(*) FROM users"))

        with pytest.raises(CorruptBackupError):
            await RestoreBackup(
                store,
                SqlAlchemyDatabaseRestorer(factory),
                media,
                LocalBackupWorkspace(tmp_path / "backups"),
                get_access_guard(),
            ).handle(
                RestoreBackupCommand(backup_id=backup.id, replace=True),
                SYSTEM_ACTOR,
            )

        async with engine.connect() as connection:
            after = await connection.scalar(text("SELECT count(*) FROM users"))
        assert after == before
    finally:
        await engine.dispose()
