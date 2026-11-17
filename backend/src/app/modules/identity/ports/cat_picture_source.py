from typing import Protocol


class CatPictureSource(Protocol):
    """Somewhere Random cat can get a picture of a cat from."""

    async def fetch(self) -> bytes:
        """Return one cat picture's bytes, as the service sent them.

        Raises:
            CatServiceUnavailableError: If no usable cat could be had.
        """
        ...
