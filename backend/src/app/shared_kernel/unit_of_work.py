from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
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

    def on_commit(self, callback: Callable[[], Awaitable[None]]) -> None:
        """Register a side effect to run only after this transaction truly commits.

        A `JoinedUnitOfWork` forwards these to the owner, so a callback
        registered by a composed sub-handler still runs exactly once, after
        the outer transaction actually commits.
        """
        ...


class JoinedUnitOfWork[TRepos]:
    """Runs a sub-handler against an already-open transaction.

    ``__aenter__``, ``__aexit__``, and ``commit()`` are all no-ops — the owner
    controls the real session lifecycle and commit — but ``on_commit`` callbacks
    are forwarded to ``owner``, so a sub-handler's deferred side effect still
    runs exactly once, only after the owner's commit genuinely succeeds.
    """

    def __init__(self, repos: TRepos, owner: UnitOfWork[TRepos]) -> None:
        self._repos = repos
        self._owner = owner

    async def __aenter__(self) -> TRepos:
        """Return the already-open repositories without starting a new transaction."""
        return self._repos

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """No-op: the owner's ``__aexit__`` handles rollback and cleanup."""

    async def commit(self) -> None:
        """No-op: call the owner's ``commit()`` to actually commit the transaction."""

    def on_commit(self, callback: Callable[[], Awaitable[None]]) -> None:
        """Forward the callback to the owning unit of work."""
        self._owner.on_commit(callback)


class InMemoryUnitOfWork[TRepos]:
    """No-op transaction boundary wrapping an already-built repository bundle.

    Exists so tests can construct a module's in-memory repositories directly
    and hand them to a use case without spoofing a session factory - there is
    no session, so there is nothing to begin, roll back, or close. ``committed``
    and ``rolled_back`` let a test assert a use case reached (or correctly
    avoided) its commit point.  ``on_commit`` callbacks fire in registration
    order immediately after ``commit()`` succeeds, mirroring real-DB timing.
    """

    def __init__(self, repos: TRepos) -> None:
        self._repos = repos
        self.committed = False
        self.rolled_back = False
        self._callbacks: list[Callable[[], Awaitable[None]]] = []

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
        """Record that this unit of work was committed and run deferred callbacks."""
        self.committed = True
        callbacks, self._callbacks = self._callbacks, []
        for callback in callbacks:
            await callback()

    def on_commit(self, callback: Callable[[], Awaitable[None]]) -> None:
        """Enqueue a callback to run when ``commit()`` is called."""
        self._callbacks.append(callback)
