import asyncio
import os
import re
import tempfile
import uuid
from typing import TYPE_CHECKING

import structlog

from app.modules.identity.domain.avatar import AVATAR_SIZES
from app.modules.identity.ports.avatar_storage import StoredPicture

if TYPE_CHECKING:
    from pathlib import Path

    from app.modules.identity.ports.avatar_image_processor import ProcessedAvatar

logger = structlog.get_logger()

_VERSION = re.compile(r"[0-9a-f]{16}")
_FILE = re.compile(r"(?P<version>[0-9a-f]{16})-(?P<size>[0-9]+)\.webp")


def _checked(version: str) -> str:
    if _VERSION.fullmatch(version) is None:
        raise ValueError(f"Not a picture version: {version!r}")
    return version


def _write_atomically(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=".", suffix=".part")
    try:
        with os.fdopen(handle, "wb") as file:
            file.write(data)
        os.replace(temporary, path)
    except BaseException:
        os.unlink(temporary)
        raise


def _read(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def _remove(folder: Path, keep: str | None) -> None:
    try:
        entries = list(folder.iterdir())
    except FileNotFoundError:
        return
    for entry in entries:
        if keep is None or not entry.name.startswith(f"{keep}-"):
            entry.unlink(missing_ok=True)
    if keep is None:
        try:
            folder.rmdir()
        except OSError:
            # Another request wrote a new picture in the meantime; keep it.
            logger.debug("pictures folder not empty", folder=str(folder))


def _listed(root: Path) -> list[StoredPicture]:
    try:
        folders = [entry for entry in root.iterdir() if entry.is_dir()]
    except FileNotFoundError:
        return []
    found: list[StoredPicture] = []
    for folder in folders:
        try:
            user_id = uuid.UUID(folder.name)
        except ValueError:
            continue
        for entry in folder.iterdir():
            match = _FILE.fullmatch(entry.name)
            if match and int(match["size"]) in AVATAR_SIZES and entry.is_file():
                found.append(
                    StoredPicture(
                        user_id=user_id,
                        version=match["version"],
                        size=int(match["size"]),
                    )
                )
    return found


class LocalAvatarStorage:
    """`AvatarStorage` on the local disk: `<root>/<user_id>/<version>-<size>.webp`."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def _folder(self, user_id: uuid.UUID) -> Path:
        return self._root / str(user_id)

    def _path(self, user_id: uuid.UUID, version: str, size: int) -> Path:
        return self._folder(user_id) / f"{_checked(version)}-{int(size)}.webp"

    async def save(self, user_id: uuid.UUID, avatar: ProcessedAvatar) -> None:
        """Write every size of `avatar`, each through a temporary file and rename.

        Raises:
            ValueError: If the version is not 16 lower-case hex digits.
        """
        for size, data in avatar.images.items():
            path = self._path(user_id, avatar.version, size)
            await asyncio.to_thread(_write_atomically, path, data)
        logger.debug("picture stored", user_id=user_id, version=avatar.version)

    async def read(self, user_id: uuid.UUID, version: str, size: int) -> bytes | None:
        """Return the stored bytes, or `None` if that version or size is not stored.

        Raises:
            ValueError: If the version is not 16 lower-case hex digits.
        """
        return await asyncio.to_thread(_read, self._path(user_id, version, size))

    async def remove(self, user_id: uuid.UUID, *, keep: str | None = None) -> None:
        """Delete the account's files except version `keep`, and the folder if empty."""
        await asyncio.to_thread(
            _remove, self._folder(user_id), None if keep is None else _checked(keep)
        )
        logger.debug("pictures removed", user_id=user_id, kept=keep)

    async def delete(self, user_id: uuid.UUID, version: str, size: int) -> None:
        """Delete one stored file, if it is there.

        Raises:
            ValueError: If the version is not 16 lower-case hex digits.
        """
        path = self._path(user_id, version, size)
        await asyncio.to_thread(path.unlink, missing_ok=True)

    async def list_files(self) -> list[StoredPicture]:
        """Return every file named for a picture; temporary files are skipped."""
        return await asyncio.to_thread(_listed, self._root)
