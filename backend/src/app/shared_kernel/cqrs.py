from abc import ABC, abstractmethod
from enum import StrEnum
from typing import TYPE_CHECKING, final

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor
    from app.shared_kernel.authorization import AuthorizationPort


class UseCase[TRequest, TResult](ABC):
    """Root contract for any actor-driven use case."""

    @abstractmethod
    async def handle(self, request: TRequest, actor: Actor) -> TResult:
        """Execute `request` on behalf of `actor`."""
        ...


class CommandHandler[TUoW, TCommand, TResult](UseCase[TCommand, TResult], ABC):
    """State-mutating use case with a unit of work."""

    def __init__(self, uow: TUoW) -> None:
        self._uow = uow


class QueryHandler[TRepos, TQuery, TResult](UseCase[TQuery, TResult], ABC):
    """Read-only use case with an already-open repo bundle.

    No commit boundary - entering/exiting the UoW's transactional scope moves to
    whatever builds the handler, e.g. the FastAPI dependency function.
    """

    def __init__(self, repos: TRepos) -> None:
        self._repos = repos


# TPermission defaults to StrEnum itself; pin it per-module (see §4) to
# catch cross-module permission mixups at type-check time. Requires
# Python 3.13+ syntax (PEP 696 default generic params).


class AuthorisedUseCase[TRequest, TResult, TPermission: StrEnum = StrEnum](
    UseCase[TRequest, TResult]
):
    """Authorised use case with no persistence dependency at all."""

    @property
    @abstractmethod
    def required_permission(self) -> TPermission:
        """Permission the actor must hold to invoke this use case."""
        ...

    def __init__(self, authorization: AuthorizationPort) -> None:
        self._authorization = authorization

    @final
    async def handle(self, request: TRequest, actor: Actor) -> TResult:
        """Check `actor` holds `required_permission`, then execute `request`."""
        await self._authorization.check(actor, self.required_permission)
        return await self._handle(request, actor)

    @abstractmethod
    async def _handle(self, request: TRequest, actor: Actor) -> TResult:
        """Execute `request` on behalf of `actor`, after authorisation."""
        ...


class AuthorisedCommandHandler[TUoW, TCommand, TResult, TPermission: StrEnum = StrEnum](
    CommandHandler[TUoW, TCommand, TResult]
):
    """State-mutating use case with a UoW AND a mandatory permission check."""

    @property
    @abstractmethod
    def required_permission(self) -> TPermission:
        """Permission the actor must hold to invoke this command."""
        ...

    def __init__(self, uow: TUoW, authorization: AuthorizationPort) -> None:
        super().__init__(uow)
        self._authorization = authorization

    @final
    async def handle(self, request: TCommand, actor: Actor) -> TResult:
        """Check `actor` holds `required_permission`, then execute `request`."""
        await self._authorization.check(actor, self.required_permission)
        return await self._handle(request, actor)

    @abstractmethod
    async def _handle(self, command: TCommand, actor: Actor) -> TResult:
        """Execute `command` on behalf of `actor`, after authorisation."""
        ...


class AuthorisedQueryHandler[TRepos, TQuery, TResult, TPermission: StrEnum = StrEnum](
    QueryHandler[TRepos, TQuery, TResult]
):
    """Read-only use case with repos AND a mandatory permission check."""

    @property
    @abstractmethod
    def required_permission(self) -> TPermission:
        """Permission the actor must hold to invoke this query."""
        ...

    def __init__(self, repos: TRepos, authorization: AuthorizationPort) -> None:
        super().__init__(repos)
        self._authorization = authorization

    @final
    async def handle(self, request: TQuery, actor: Actor) -> TResult:
        """Check `actor` holds `required_permission`, then execute `request`."""
        await self._authorization.check(actor, self.required_permission)
        return await self._handle(request, actor)

    @abstractmethod
    async def _handle(self, query: TQuery, actor: Actor) -> TResult:
        """Execute `query` on behalf of `actor`, after authorisation."""
        ...
