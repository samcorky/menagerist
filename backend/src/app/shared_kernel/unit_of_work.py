from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from types import TracebackType


class UnitOfWork[TRepos](Protocol):
    """Transaction boundary that yields a module's repository bundle.

    A structural contract, not a base class - a module's concrete unit of
    work (real or in-memory) satisfies this by shape alone. See
    `InMemoryUnitOfWork` for the fast-test implementation and
    `app.platform.unit_of_work.SqlAlchemySessionUnitOfWork` for the real one.
    """

    async def __aenter__(self) -> TRepos:
        """Enter the transactional scope, returning the module's repositories."""
        ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Roll back on exception, then always release underlying resources."""
        ...

    async def commit(self) -> None:
        """Persist the changes made within this unit of work."""
        ...


class InMemoryUnitOfWork[TRepos]:
    """No-op transaction boundary wrapping an already-built repository bundle.

    Exists so tests can construct a module's in-memory repositories directly
    and hand them to a use case without spoofing a session factory - there is
    no session, so there is nothing to begin, roll back, or close. `committed`
    and `rolled_back` let a test assert a use case reached (or correctly
    avoided) its commit point.
    """

    def __init__(self, repos: TRepos) -> None:
        self._repos = repos
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self) -> TRepos:
        """Enter the transactional scope, returning the wrapped repositories."""
        return self._repos

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Record whether this unit of work exited due to an exception."""
        if exc_type is not None:
            self.rolled_back = True

    async def commit(self) -> None:
        """Record that this unit of work was committed."""
        self.committed = True
