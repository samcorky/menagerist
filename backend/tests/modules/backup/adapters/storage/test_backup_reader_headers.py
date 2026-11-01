import gzip
import io
import tarfile

import pytest

from app.modules.backup.adapters.storage.local_backup_reader import (
    LocalBackupReader,
    require_tar_parser_hooks,
)
from app.modules.backup.domain.errors import CorruptBackupError


@pytest.mark.parametrize(
    "kind",
    [
        tarfile.XHDTYPE,
        tarfile.XGLTYPE,
        tarfile.GNUTYPE_LONGNAME,
        tarfile.GNUTYPE_LONGLINK,
    ],
)
async def test_rejects_large_extension_before_reading_body(kind: bytes) -> None:
    """Reject declared metadata sizes before tarfile allocates their bodies."""
    info = tarfile.TarInfo("extension")
    info.type = kind
    info.size = 1024**3
    reader = LocalBackupReader(gzip.compress(info.tobuf()))
    with pytest.raises(CorruptBackupError, match="metadata"):
        async for _ in reader.members():
            pass


async def test_rejects_deep_extension_chain() -> None:
    """Nested extension headers cannot exhaust the Python call stack."""
    info = tarfile.TarInfo("extension")
    info.type = tarfile.XHDTYPE
    reader = LocalBackupReader(gzip.compress(info.tobuf() * 40))
    with pytest.raises(CorruptBackupError, match="metadata"):
        async for _ in reader.members():
            pass


@pytest.mark.parametrize("format", [tarfile.PAX_FORMAT, tarfile.GNU_FORMAT])
async def test_accepts_bounded_extended_names(format: int) -> None:
    """Normal PAX and GNU metadata still resolve the following regular file."""
    output = io.BytesIO()
    name = "data/" + "a" * 160 + ".ndjson"
    with tarfile.open(fileobj=output, mode="w:gz", format=format) as archive:
        info = tarfile.TarInfo(name)
        info.size = 7
        archive.addfile(info, io.BytesIO(b"content"))
    rows = []
    async for member in LocalBackupReader(output.getvalue()).members():
        rows.append((member.name, b"".join([chunk async for chunk in member.chunks])))
    assert rows == [(name, b"content")]


@pytest.mark.parametrize(
    "headers",
    [
        {"GNU.sparse.size": "1", "GNU.sparse.numblocks": "0"},
        {"GNU.sparse.map": "0,1"},
        {"GNU.sparse.major": "1", "GNU.sparse.minor": "0"},
    ],
)
async def test_rejects_pax_sparse_formats(headers: dict[str, str]) -> None:
    """Sparse metadata is refused before expanding extent maps."""
    output = io.BytesIO()
    with tarfile.open(
        fileobj=output, mode="w:gz", format=tarfile.PAX_FORMAT
    ) as archive:
        info = tarfile.TarInfo("data/table.ndjson")
        info.pax_headers = headers
        archive.addfile(info)
    with pytest.raises(CorruptBackupError, match="Sparse"):
        async for _ in LocalBackupReader(output.getvalue()).members():
            pass


async def test_rejects_old_gnu_sparse_format() -> None:
    """Legacy sparse headers are refused before reading extension blocks."""
    info = tarfile.TarInfo("data/table.ndjson")
    info.type = tarfile.GNUTYPE_SPARSE
    with pytest.raises(CorruptBackupError, match="Sparse"):
        async for _ in LocalBackupReader(gzip.compress(info.tobuf())).members():
            pass


def test_the_tar_parser_hooks_exist_on_this_python() -> None:
    """The reader bounds headers through the tarfile parser methods."""
    require_tar_parser_hooks(tarfile.TarInfo)


def test_a_tarfile_without_the_parser_hooks_fails_loudly() -> None:
    """On a Python that parses elsewhere the limits would never run: refuse to load."""

    class OldTarInfo:
        @classmethod
        def fromtarfile(cls) -> None: ...

    with pytest.raises(RuntimeError, match="frombuf"):
        require_tar_parser_hooks(OldTarInfo)
