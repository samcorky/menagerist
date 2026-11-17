from app.modules.identity.domain.errors import CatServiceUnavailableError


class DisabledCatPictureSource:
    """`CatPictureSource` for an instance that never contacts a cat service."""

    @staticmethod
    async def fetch() -> bytes:
        """Refuse straight away, so the browser draws a cat instead.

        Raises:
            CatServiceUnavailableError: Always.
        """
        raise CatServiceUnavailableError("The cat service is turned off.")
