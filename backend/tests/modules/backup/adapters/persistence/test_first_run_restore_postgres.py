import hashlib
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.entrypoints.api.shared.authorisation import RoleAuthorisationAdapter
from app.entrypoints.api.shared.backup_media_files import BackupMediaFiles
from app.entrypoints.api.shared.bridges.backup_setup_gate import get_setup_gate
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
from app.modules.backup.application.restore_on_first_run import (
    RestoreOnFirstRun,
    RestoreOnFirstRunCommand,
)
from app.modules.backup.domain.errors import RestoreTargetNotEmptyError
from app.modules.identity.adapters.persistence.unit_of_work import create_identity_uow
from app.modules.identity.adapters.persistence.user_repository import (
    SqlAlchemyUserRepository,
)
from app.modules.identity.adapters.security.password_authenticator import (
    PasswordAuthenticator,
)
from app.modules.identity.adapters.security.scrypt_password_hasher import (
    ScryptPasswordHasher,
)
from app.modules.identity.adapters.security.session_token_generator import (
    SecretsSessionTokenGenerator,
)
from app.modules.identity.application.sign_in import SignIn, SignInCommand
from app.modules.identity.application.sign_in_throttle import SignInThrottle
from app.modules.identity.domain.user import Role, User
from app.modules.media.adapters.persistence.in_memory_media_asset_repository import (
    InMemoryMediaAssetRepository,
)
from app.modules.media.adapters.storage.local_filesystem import (
    LocalFilesystemMediaStorage,
)
from app.modules.media.domain.media_asset import MediaAsset
from app.shared_kernel.actor import ANONYMOUS_ACTOR, SYSTEM_ACTOR

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    from app.modules.backup.domain.backup import MediaFileRef

pytestmark = pytest.mark.integration


async def _chunks(data: bytes) -> AsyncIterator[bytes]:
    yield data


@pytest.mark.parametrize("fail_media", [False, True])
async def test_first_run_restores_credentials_and_rolls_back_media_failure(
    snapshot_database: str, tmp_path: Path, fail_media: bool
) -> None:
    """Restore archived sign-in or leave setup and originals intact."""
    engine = create_async_engine(snapshot_database)
    factory = async_sessionmaker(engine)
    gate_stream = get_setup_gate(factory)
    try:
        hasher = ScryptPasswordHasher()
        user = User.create(
            username="archived",
            display_name="Archived administrator",
            password_hash=hasher.hash("archived-password"),
            role=Role.ADMIN,
            now=datetime.now(UTC),
        )
        async with factory.begin() as session:
            await SqlAlchemyUserRepository(session).add(user)
        assets = InMemoryMediaAssetRepository()
        asset = MediaAsset.create(
            owner_id=user.id,
            filename="original.bin",
            content_type="application/octet-stream",
            size=3,
            sha256=hashlib.sha256(b"new").hexdigest(),
        )
        await assets.add(asset)
        source_media = BackupMediaFiles(
            assets, LocalFilesystemMediaStorage(tmp_path / "source-media")
        )
        ref = (await source_media.list_files())[0]
        await source_media.write(ref, _chunks(b"new"))
        store = LocalDirectoryBackupStore(tmp_path / "backups")
        backup = await CreateBackup(
            store,
            SqlAlchemyDatabaseSnapshot(factory),
            source_media,
            RoleAuthorisationAdapter(),
            app_version="test",
        ).handle(CreateBackupCommand(), SYSTEM_ACTOR)
        async with engine.begin() as connection:
            await connection.execute(text("DELETE FROM users"))

        class TargetMedia(BackupMediaFiles):
            async def write(
                self, ref: MediaFileRef, stream: AsyncIterator[bytes]
            ) -> None:
                """Fail after the original was replaced when requested."""
                await super().write(ref, stream)
                content = b"".join([chunk async for chunk in self.open(ref)])
                if fail_media and content == b"new":
                    raise OSError("media failed")

        target_media = TargetMedia(
            assets, LocalFilesystemMediaStorage(tmp_path / "target-media")
        )
        await target_media.write(ref, _chunks(b"old"))
        gate = await anext(gate_stream)
        workspace = LocalBackupWorkspace(tmp_path / "backups")
        restore = RestoreOnFirstRun(
            gate, store, SqlAlchemyDatabaseRestorer(factory), target_media, workspace
        )
        command = RestoreOnFirstRunCommand(stream=store.read_bytes(backup.id))
        if fail_media:
            with pytest.raises(OSError, match="media failed"):
                await restore.handle(command, ANONYMOUS_ACTOR)
            assert await gate.is_open()
            assert b"".join([chunk async for chunk in target_media.open(ref)]) == b"old"
            async with engine.connect() as connection:
                assert await connection.scalar(text("SELECT count(*) FROM users")) == 0
        else:
            await restore.handle(command, ANONYMOUS_ACTOR)
            assert not await gate.is_open()
            sign_in = SignIn(
                create_identity_uow(factory),
                PasswordAuthenticator(
                    create_identity_uow(factory),
                    hasher,
                    decoy_hash=hasher.hash("decoy"),
                ),
                SecretsSessionTokenGenerator(),
                hasher,
                SignInThrottle(),
                decoy_hash=hasher.hash("decoy"),
                session_ttl=timedelta(hours=1),
            )
            signed_in = await sign_in.handle(
                SignInCommand(username="archived", password="archived-password"),
                ANONYMOUS_ACTOR,
            )
            assert signed_in.user.id == user.id
            assert signed_in.user.role == Role.ADMIN
            assert b"".join([chunk async for chunk in target_media.open(ref)]) == b"new"
            with pytest.raises(RestoreTargetNotEmptyError):
                await restore.handle(
                    RestoreOnFirstRunCommand(stream=store.read_bytes(backup.id)),
                    ANONYMOUS_ACTOR,
                )
        assert [item.id for item in await store.list()] == [backup.id]
        assert list((tmp_path / "backups" / ".staging").iterdir()) == []
    finally:
        await anext(gate_stream, None)
        await engine.dispose()
