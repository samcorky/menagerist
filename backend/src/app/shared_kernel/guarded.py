from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar, final

# Needed at runtime: the CQRS signature test evaluates __init__ annotations.
from app.shared_kernel.access import Content
from app.shared_kernel.access_guard import AccessGuard  # noqa: TC001

if TYPE_CHECKING:
    from app.shared_kernel.access import Access
    from app.shared_kernel.actor import Actor
    from app.shared_kernel.content_filter import ContentFilter


class GuardedUseCase[TRequest, TResult](ABC):
    """Use case that declares who may call it and is checked by an `AccessGuard`.

    Subclasses set `access`, assign `self._guard` in `__init__` and implement
    `_handle`; `handle` is final so the check cannot be skipped.
    """

    access: ClassVar[Access]
    _guard: AccessGuard

    @final
    async def handle(self, request: TRequest, actor: Actor) -> TResult:
        """Check `actor` against `access`, then execute `request`."""
        await self._guard.check(actor, self.access)
        return await self._handle(request, actor)

    @abstractmethod
    async def _handle(self, request: TRequest, actor: Actor) -> TResult:
        """Execute `request` once access has been granted."""
        ...

    def scope(self, actor: Actor) -> ContentFilter:
        """Return the content `actor` may see.

        Raises:
            TypeError: If this use case does not declare `Content` access.
        """
        if not isinstance(self.access, Content):
            msg = f"{type(self).__name__} does not declare Content access"
            raise TypeError(msg)
        return self._guard.scope_for(actor)


class GuardedCommandHandler[TUoW, TCommand, TResult](
    GuardedUseCase[TCommand, TResult], ABC
):
    """State-mutating guarded use case with a unit of work."""

    def __init__(self, uow: TUoW, guard: AccessGuard) -> None:
        self._uow = uow
        self._guard = guard


class GuardedQueryHandler[TRepos, TQuery, TResult](
    GuardedUseCase[TQuery, TResult], ABC
):
    """Read-only guarded use case with an already-open repo bundle."""

    def __init__(self, repos: TRepos, guard: AccessGuard) -> None:
        self._repos = repos
        self._guard = guard
