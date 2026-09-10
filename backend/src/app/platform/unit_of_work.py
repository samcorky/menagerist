from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from types import TracebackType

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class SqlAlchemySessionUnitOfWork[TRepos]:
    """Real, SQLAlchemy-backed `UnitOfWork[TRepos]` shared by every module.

    A module never subclasses this - it supplies a `build_repos` callable
    that wraps a freshly-opened session in its own repository bundle, and
    gets session lifecycle (begin, rollback-on-exception, always-close,
    commit) for free.  ``on_commit`` callbacks are run in registration order
    immediately after the SQLAlchemy commit succeeds.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        build_repos: Callable[[AsyncSession], TRepos],
    ) -> None:
        self._session_factory = session_factory
        self._build_repos = build_repos
        self._session: AsyncSession | None = None
        self._callbacks: list[Callable[[], Awaitable[None]]] = []

    async def __aenter__(self) -> TRepos:
        """Begin a session and return the module's repository bundle."""
        self._session = self._session_factory()
        return self._build_repos(self._session)

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Roll back on exception, then always close the session."""
        assert self._session is not None
        try:
            if exc_type is not None:
                await self._session.rollback()
        finally:
            await self._session.close()

    async def commit(self) -> None:
        """Commit the session, then run any registered on_commit callbacks."""
        assert self._session is not None
        await self._session.commit()
        callbacks, self._callbacks = self._callbacks, []
        for callback in callbacks:
            await callback()

    def on_commit(self, callback: Callable[[], Awaitable[None]]) -> None:
        """Enqueue a side-effect callback to run after the next successful commit."""
        self._callbacks.append(callback)
