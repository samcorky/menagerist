from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.modules.system.domain.release import Release, RepositoryRef


class ReleaseProvider(Protocol):
    """A place that publishes releases, read without any local state."""

    async def releases(self, repository: RepositoryRef) -> list[Release]:
        """Return the published, non-draft releases the source lists first.

        Raises:
            ReleaseCheckError: If the source could not be read.
        """
        ...
