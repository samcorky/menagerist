from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.modules.system.domain.release import ImageRef


class PublishedImageProvider(Protocol):
    """A registry that publishes images, read without any local state."""

    async def revision(self, image: ImageRef) -> str | None:
        """Return the revision the published image was built from.

        `None` when the image is there but claims no revision, which is not a
        failure: an older image may carry no such label.

        Raises:
            ReleaseCheckError: If the registry could not be read.
        """
        ...
