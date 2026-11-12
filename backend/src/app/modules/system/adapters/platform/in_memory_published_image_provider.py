from typing import TYPE_CHECKING

from app.modules.system.domain.release import ReleaseCheckError

if TYPE_CHECKING:
    from app.modules.system.domain.release import CheckFailure, ImageRef


class InMemoryPublishedImageProvider:
    """Serves a fixed revision, or a fixed failure, for tests."""

    def __init__(
        self,
        revision: str | None = None,
        *,
        failure: CheckFailure | None = None,
    ) -> None:
        self.published = revision
        self.failure = failure
        self.calls: list[ImageRef] = []

    async def revision(self, image: ImageRef) -> str | None:
        """Return the configured revision or raise the configured failure."""
        self.calls.append(image)
        if self.failure is not None:
            raise ReleaseCheckError(self.failure)
        return self.published
