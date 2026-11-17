from typing import TYPE_CHECKING

from app.modules.identity.ports.avatar_storage import StoredPicture

if TYPE_CHECKING:
    import uuid

    from app.modules.identity.ports.avatar_image_processor import ProcessedAvatar


class InMemoryAvatarStorage:
    """`AvatarStorage` held in a dictionary, for tests."""

    def __init__(self) -> None:
        self.files: dict[tuple[uuid.UUID, str, int], bytes] = {}

    async def save(self, user_id: uuid.UUID, avatar: ProcessedAvatar) -> None:
        """Keep every size of `avatar`."""
        for size, data in avatar.images.items():
            self.files[user_id, avatar.version, size] = data

    async def read(self, user_id: uuid.UUID, version: str, size: int) -> bytes | None:
        """Return the kept bytes, or `None`."""
        return self.files.get((user_id, version, size))

    async def remove(self, user_id: uuid.UUID, *, keep: str | None = None) -> None:
        """Forget the account's files except version `keep`."""
        for key in [k for k in self.files if k[0] == user_id and k[1] != keep]:
            del self.files[key]

    async def delete(self, user_id: uuid.UUID, version: str, size: int) -> None:
        """Forget one file."""
        self.files.pop((user_id, version, size), None)

    async def list_files(self) -> list[StoredPicture]:
        """Return every kept file."""
        return [
            StoredPicture(user_id=user_id, version=version, size=size)
            for user_id, version, size in self.files
        ]
