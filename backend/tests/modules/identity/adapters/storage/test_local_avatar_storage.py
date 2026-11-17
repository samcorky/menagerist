import uuid
from typing import TYPE_CHECKING

import pytest

from app.modules.identity.adapters.storage.in_memory_avatar_storage import (
    InMemoryAvatarStorage,
)
from app.modules.identity.adapters.storage.local_avatar_storage import (
    LocalAvatarStorage,
)
from app.modules.identity.domain.avatar import AVATAR_SIZES
from app.modules.identity.ports.avatar_image_processor import ProcessedAvatar

if TYPE_CHECKING:
    from pathlib import Path

    from app.modules.identity.ports.avatar_storage import AvatarStorage

USER = uuid.UUID("01900000-0000-7000-8000-000000000001")


def _avatar(version: str) -> ProcessedAvatar:
    return ProcessedAvatar(
        version=version,
        images={size: f"{version}-{size}".encode() for size in AVATAR_SIZES},
    )


@pytest.fixture(params=["local", "memory"])
def storage(request: pytest.FixtureRequest, tmp_path: Path) -> AvatarStorage:
    """Each test runs against the disk adapter and its in-memory sibling."""
    if request.param == "local":
        return LocalAvatarStorage(tmp_path / "avatars")
    return InMemoryAvatarStorage()


async def test_save_then_read_each_size(storage: AvatarStorage) -> None:
    """Every size saved can be read back."""
    await storage.save(USER, _avatar("0123456789abcdef"))
    for size in AVATAR_SIZES:
        assert await storage.read(USER, "0123456789abcdef", size) == (
            f"0123456789abcdef-{size}".encode()
        )


async def test_read_unknown_version_is_none(storage: AvatarStorage) -> None:
    """A version that was never saved, or a size not stored, reads as nothing."""
    await storage.save(USER, _avatar("0123456789abcdef"))
    assert await storage.read(USER, "fedcba9876543210", 64) is None
    assert await storage.read(USER, "0123456789abcdef", 99) is None
    assert await storage.read(uuid.uuid7(), "0123456789abcdef", 64) is None


async def test_remove_keeps_named_version(storage: AvatarStorage) -> None:
    """Replacing a picture removes the old version's files only."""
    await storage.save(USER, _avatar("1111111111111111"))
    await storage.save(USER, _avatar("2222222222222222"))
    await storage.remove(USER, keep="2222222222222222")
    assert await storage.read(USER, "1111111111111111", 64) is None
    assert await storage.read(USER, "2222222222222222", 64) is not None


async def test_remove_all(storage: AvatarStorage) -> None:
    """Clearing a picture removes every file, and is safe to repeat."""
    await storage.save(USER, _avatar("1111111111111111"))
    await storage.remove(USER)
    await storage.remove(USER)
    assert await storage.read(USER, "1111111111111111", 64) is None


async def test_remove_all_deletes_directory(tmp_path: Path) -> None:
    """No empty folder is left behind for an account without a picture."""
    storage = LocalAvatarStorage(tmp_path / "avatars")
    await storage.save(USER, _avatar("1111111111111111"))
    await storage.remove(USER)
    assert not (tmp_path / "avatars" / str(USER)).exists()


async def test_files_named_by_version_and_size(tmp_path: Path) -> None:
    """Files sit at `<user>/<version>-<size>.webp`, with no temporary leftovers."""
    storage = LocalAvatarStorage(tmp_path / "avatars")
    await storage.save(USER, _avatar("0123456789abcdef"))
    names = sorted(p.name for p in (tmp_path / "avatars" / str(USER)).iterdir())
    assert names == sorted(f"0123456789abcdef-{s}.webp" for s in AVATAR_SIZES)


@pytest.mark.parametrize("version", ["../x", "ABCDEF0123456789", "0123", "g" * 16])
async def test_rejects_bad_version_string(tmp_path: Path, version: str) -> None:
    """A version is 16 lower-case hex digits, so no path is built from anything else."""
    storage = LocalAvatarStorage(tmp_path / "avatars")
    with pytest.raises(ValueError, match="version"):
        await storage.read(USER, version, 64)
    with pytest.raises(ValueError, match="version"):
        await storage.save(USER, _avatar(version))


async def test_list_files_names_every_stored_size(storage: AvatarStorage) -> None:
    """Backups find every picture file by account, version and size."""
    other = uuid.UUID("01900000-0000-7000-8000-000000000002")
    await storage.save(USER, _avatar("0123456789abcdef"))
    await storage.save(other, _avatar("fedcba9876543210"))

    found = await storage.list_files()

    assert sorted((f.user_id, f.version, f.size) for f in found) == sorted(
        [(USER, "0123456789abcdef", s) for s in AVATAR_SIZES]
        + [(other, "fedcba9876543210", s) for s in AVATAR_SIZES]
    )


async def test_delete_removes_one_file(storage: AvatarStorage) -> None:
    """A rolled-back restore removes exactly the files it wrote, safely twice."""
    await storage.save(USER, _avatar("0123456789abcdef"))
    await storage.delete(USER, "0123456789abcdef", 64)
    await storage.delete(USER, "0123456789abcdef", 64)
    assert await storage.read(USER, "0123456789abcdef", 64) is None
    assert await storage.read(USER, "0123456789abcdef", 128) is not None


async def test_list_files_ignores_temporary_and_foreign_files(tmp_path: Path) -> None:
    """Half-written files and anything not named for a picture are left out."""
    storage = LocalAvatarStorage(tmp_path / "avatars")
    await storage.save(USER, _avatar("0123456789abcdef"))
    folder = tmp_path / "avatars" / str(USER)
    (folder / ".abc.part").write_bytes(b"x")
    (folder / "notes.txt").write_bytes(b"x")
    (tmp_path / "avatars" / "not-a-user").mkdir()
    assert len(await storage.list_files()) == len(AVATAR_SIZES)


async def test_list_files_on_an_empty_store(tmp_path: Path) -> None:
    """No folder yet means no pictures."""
    assert await LocalAvatarStorage(tmp_path / "missing").list_files() == []
