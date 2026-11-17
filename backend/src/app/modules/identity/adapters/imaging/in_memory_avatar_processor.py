import hashlib

from app.modules.identity.domain.avatar import AVATAR_SIZES, CropSquare
from app.modules.identity.domain.errors import InvalidAvatarError
from app.modules.identity.ports.avatar_image_processor import ProcessedAvatar


class InMemoryAvatarProcessor:
    """Deterministic `AvatarImageProcessor` for tests: no decoding happens.

    The version is derived from the input, so different bytes give a different
    picture. Set `fail_next` to make the next call refuse its input.
    """

    def __init__(self) -> None:
        self.fail_next = False
        self.crops: list[CropSquare | None] = []

    async def process(self, data: bytes, *, crop: CropSquare | None) -> ProcessedAvatar:
        """Return fake bytes per size, recording `crop`.

        Raises:
            InvalidAvatarError: If `fail_next` was set.
        """
        self.crops.append(crop)
        if self.fail_next:
            self.fail_next = False
            raise InvalidAvatarError("That file can't be used as a picture.")
        version = hashlib.sha256(data).hexdigest()[:16]
        return ProcessedAvatar(
            version=version,
            images={size: f"{version}-{size}".encode() for size in AVATAR_SIZES},
        )
