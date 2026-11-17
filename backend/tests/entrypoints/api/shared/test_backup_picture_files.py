import hashlib
from typing import TYPE_CHECKING
from uuid import uuid7

import pytest

from app.entrypoints.api.shared.backup_picture_files import BackupPictureFiles
from app.modules.backup.domain.backup import PICTURE_SIZES, PictureFileRef
from app.modules.backup.domain.errors import MediaFileMissingError
from app.modules.identity.adapters.storage.local_avatar_storage import (
    LocalAvatarStorage,
)
from app.modules.identity.domain.avatar import AVATAR_SIZES
from app.modules.identity.ports.avatar_image_processor import ProcessedAvatar

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

USER = uuid7()
VERSION = "0123456789abcdef"


async def _chunks(data: bytes) -> AsyncIterator[bytes]:
    yield data


def _ref(data: bytes, pixels: int = 64) -> PictureFileRef:
    return PictureFileRef(
        user_id=USER,
        version=VERSION,
        pixels=pixels,
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )


def test_backup_sizes_match_the_stored_sizes() -> None:
    """Backups accept exactly the sizes identity stores."""
    assert frozenset(AVATAR_SIZES) == PICTURE_SIZES


async def test_lists_stored_pictures_with_size_and_hash(tmp_path: Path) -> None:
    """Each stored file is described so the archive can check it."""
    storage = LocalAvatarStorage(tmp_path)
    await storage.save(
        USER,
        ProcessedAvatar(
            version=VERSION, images={s: f"p{s}".encode() for s in AVATAR_SIZES}
        ),
    )
    refs = await BackupPictureFiles(storage).list_files()
    assert sorted(refs, key=lambda r: r.pixels) == [
        _ref(f"p{s}".encode(), s) for s in sorted(AVATAR_SIZES)
    ]


async def test_write_open_exists_and_remove(tmp_path: Path) -> None:
    """A restored file can be read back, and a rolled-back one is gone."""
    files = BackupPictureFiles(LocalAvatarStorage(tmp_path))
    ref = _ref(b"cat")
    assert not await files.exists(ref)
    await files.write(ref, _chunks(b"cat"))
    assert await files.exists(ref)
    assert b"".join([chunk async for chunk in files.open(ref)]) == b"cat"
    await files.remove(ref)
    assert not await files.exists(ref)


async def test_open_missing_file_is_reported(tmp_path: Path) -> None:
    """A file that vanished is the same missing-file error media uses."""
    files = BackupPictureFiles(LocalAvatarStorage(tmp_path))
    with pytest.raises(MediaFileMissingError):
        async for _ in files.open(_ref(b"cat")):
            pass


def test_backups_read_pictures_from_the_media_folder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Instance backups use the same pictures folder the app serves from."""
    from app.entrypoints.api.shared import backup_dependencies
    from app.platform.config.media import MediaSettings

    monkeypatch.setattr(
        backup_dependencies,
        "get_media_settings",
        lambda: MediaSettings(storage_path=tmp_path),
    )
    files = backup_dependencies.get_picture_files()
    assert isinstance(files, BackupPictureFiles)
    assert files._storage._root == tmp_path / "avatars"  # type: ignore[attr-defined]
