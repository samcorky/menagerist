from abc import ABC, abstractmethod
from enum import StrEnum
from typing import TYPE_CHECKING, final

# Needed at runtime: the CQRS signature test evaluates __init__ annotations.
from app.shared_kernel.access_policy import AccessPolicy  # noqa: TC001
from app.shared_kernel.authorisation import AuthorisationPort  # noqa: TC001

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


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


class _PolicyHolder:
    """Mixin: keeps the `AccessPolicy` a scoped use case consults."""

    _policy: AccessPolicy

    # A method, not __init__: a mixin __init__ would disturb the cooperative
    # super().__init__ chain.
    def _set_policy(self, policy: AccessPolicy) -> None:
        self._policy = policy


class ScopedCommandHandler[TUoW, TCommand, TResult](
    _PolicyHolder, CommandHandler[TUoW, TCommand, TResult], ABC
):
    """State-mutating use case over content that an `AccessPolicy` scopes."""

    def __init__(self, uow: TUoW, policy: AccessPolicy) -> None:
        super().__init__(uow)
        self._set_policy(policy)


class ScopedQueryHandler[TRepos, TQuery, TResult](
    _PolicyHolder, QueryHandler[TRepos, TQuery, TResult], ABC
):
    """Read-only use case over content that an `AccessPolicy` scopes."""

    def __init__(self, repos: TRepos, policy: AccessPolicy) -> None:
        super().__init__(repos)
        self._set_policy(policy)


# TPermission defaults to StrEnum itself; pin it per-module to
# catch cross-module permission mixups at type-check time. Requires
# Python 3.13+ syntax (PEP 696 default generic params).


class _PermissionGate[TRequest, TResult, TPermission: StrEnum = StrEnum](ABC):
    """Mixin: the permission check shared by every Authorised* use case.

    Must precede the `UseCase` base in the MRO so its final `handle` wins.
    """

    _authorisation: AuthorisationPort

    @property
    @abstractmethod
    def required_permission(self) -> TPermission:
        """Permission the actor must hold to invoke this use case."""
        ...

    @final
    async def handle(self, request: TRequest, actor: Actor) -> TResult:
        """Check `actor` holds `required_permission`, then execute `request`."""
        await self._authorisation.check(actor, self.required_permission)
        return await self._handle(request, actor)

    @abstractmethod
    async def _handle(self, request: TRequest, actor: Actor) -> TResult:
        """Execute `request` on behalf of `actor`, after authorisation."""
        ...


class AuthorisedUseCase[TRequest, TResult, TPermission: StrEnum = StrEnum](
    _PermissionGate[TRequest, TResult, TPermission], UseCase[TRequest, TResult]
):
    """Authorised use case with no persistence dependency at all."""

    def __init__(self, authorisation: AuthorisationPort) -> None:
        self._authorisation = authorisation


class AuthorisedCommandHandler[TUoW, TCommand, TResult, TPermission: StrEnum = StrEnum](
    _PermissionGate[TCommand, TResult, TPermission],
    CommandHandler[TUoW, TCommand, TResult],
):
    """State-mutating use case with a UoW AND a mandatory permission check."""

    def __init__(self, uow: TUoW, authorisation: AuthorisationPort) -> None:
        super().__init__(uow)
        self._authorisation = authorisation


class AuthorisedQueryHandler[TRepos, TQuery, TResult, TPermission: StrEnum = StrEnum](
    _PermissionGate[TQuery, TResult, TPermission],
    QueryHandler[TRepos, TQuery, TResult],
):
    """Read-only use case with repos AND a mandatory permission check."""

    def __init__(self, repos: TRepos, authorisation: AuthorisationPort) -> None:
        super().__init__(repos)
        self._authorisation = authorisation
