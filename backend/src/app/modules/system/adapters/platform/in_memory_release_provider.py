from typing import TYPE_CHECKING

from app.modules.system.domain.release import ReleaseCheckError

if TYPE_CHECKING:
    from app.modules.system.domain.release import CheckFailure, Release, RepositoryRef


class InMemoryReleaseProvider:
    """Serves a fixed list of releases, or a fixed failure, for tests."""

    def __init__(
        self,
        releases: list[Release] | None = None,
        *,
        failure: CheckFailure | None = None,
    ) -> None:
        self.available = releases or []
        self.failure = failure
        self.calls: list[RepositoryRef] = []

    async def releases(self, repository: RepositoryRef) -> list[Release]:
        """Return the configured releases or raise the configured failure."""
        self.calls.append(repository)
        if self.failure is not None:
            raise ReleaseCheckError(self.failure)
        return list(self.available)
