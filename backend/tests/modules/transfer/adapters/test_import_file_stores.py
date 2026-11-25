"""Where uploaded import files wait: on disk, and the in-memory twin."""

import uuid
from typing import TYPE_CHECKING

import pytest

from app.modules.transfer.adapters.storage import local_import_files
from app.modules.transfer.adapters.storage.in_memory_import_files import (
    InMemoryImportFileStore,
)
from app.modules.transfer.adapters.storage.local_import_files import (
    LocalImportFileStore,
)
from app.modules.transfer.domain.errors import ImportFileTooLargeError

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    from app.modules.transfer.ports.import_file_store import ImportFileStore

OWNER = uuid.UUID(int=0xA1)
FILE = uuid.UUID(int=0xF1)


async def _chunks(*parts: bytes) -> AsyncIterator[bytes]:
    for part in parts:
        yield part


@pytest.fixture(params=["disk", "memory"])
def store(request: pytest.FixtureRequest, tmp_path: Path) -> ImportFileStore:
    """Each store, so both behave the same."""
    if request.param == "disk":
        return LocalImportFileStore(tmp_path)
    return InMemoryImportFileStore()


async def test_a_stored_file_reads_back_until_deleted(store: ImportFileStore) -> None:
    """The size is returned, and deleting twice is harmless."""
    size = await store.put(OWNER, FILE, _chunks(b"a,b\n", b"1,2\n"), max_bytes=100)
    assert size == 8
    assert await store.read(OWNER, FILE) == b"a,b\n1,2\n"
    await store.delete(OWNER, FILE)
    await store.delete(OWNER, FILE)
    assert await store.read(OWNER, FILE) is None


async def test_a_file_over_the_limit_keeps_nothing(store: ImportFileStore) -> None:
    """The limit is checked while the file streams in."""
    with pytest.raises(ImportFileTooLargeError):
        await store.put(OWNER, FILE, _chunks(b"12345", b"67890"), max_bytes=8)
    assert await store.read(OWNER, FILE) is None


async def test_files_on_disk_sit_in_the_owners_folder(tmp_path: Path) -> None:
    """A half-written file is never left behind."""
    store = LocalImportFileStore(tmp_path)
    await store.put(OWNER, FILE, _chunks(b"x"), max_bytes=8)
    assert [p.name for p in (tmp_path / str(OWNER)).iterdir()] == [f"{FILE}.csv"]
    with pytest.raises(ImportFileTooLargeError):
        await store.put(OWNER, uuid.UUID(int=2), _chunks(b"123456789"), max_bytes=8)
    assert [p.name for p in (tmp_path / str(OWNER)).iterdir()] == [f"{FILE}.csv"]


def test_the_store_is_under_the_media_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Deployments already keep that directory on a volume."""

    class Settings:
        storage_path = tmp_path

    monkeypatch.setattr(local_import_files, "get_media_settings", Settings)
    store = local_import_files.import_file_store()
    assert store._base == tmp_path / "imports"
