import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.modules.identity.ports.avatar_image_processor import ProcessedAvatar


@dataclass(frozen=True, kw_only=True)
class StoredPicture:
    """One stored picture file: whose, which version, and which size."""

    user_id: uuid.UUID
    version: str
    size: int


class AvatarStorage(Protocol):
    """Where account pictures' files are kept, by account, version and size."""

    async def save(self, user_id: uuid.UUID, avatar: ProcessedAvatar) -> None:
        """Write every size of `avatar` for `user_id`, each file atomically."""
        ...

    async def read(self, user_id: uuid.UUID, version: str, size: int) -> bytes | None:
        """Return one stored size of one version, or `None` if it is not stored."""
        ...

    async def remove(self, user_id: uuid.UUID, *, keep: str | None = None) -> None:
        """Delete `user_id`'s files except those of version `keep`; safe to repeat."""
        ...

    async def delete(self, user_id: uuid.UUID, version: str, size: int) -> None:
        """Delete one stored file; safe if it is already gone."""
        ...

    async def list_files(self) -> list[StoredPicture]:
        """Return every stored picture file, for backups."""
        ...
