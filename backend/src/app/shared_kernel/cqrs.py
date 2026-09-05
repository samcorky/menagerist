from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


class CommandHandler[TUoW, TCommand, TResult](ABC):
    """Base for state-mutating use cases.

    Enforces that every command use case receives a unit of work in its
    constructor and stores it as `self._uow`; subclasses only need to
    implement `handle()`.
    """

    def __init__(self, uow: TUoW) -> None:
        self._uow = uow

    @abstractmethod
    async def handle(self, command: TCommand, actor: Actor) -> TResult:
        """Execute `command` on behalf of `actor`."""
        ...


class QueryHandler[TUoW, TQuery, TResult](ABC):
    """Base for read-only use cases.

    Mirrors `CommandHandler`: receives a unit of work so that the session
    lifecycle is fully controlled inside `handle()` — opens on entry,
    closes on exit — with no dependency on FastAPI's async generator
    cleanup machinery.
    """

    def __init__(self, uow: TUoW) -> None:
        self._uow = uow

    @abstractmethod
    async def handle(self, query: TQuery, actor: Actor) -> TResult:
        """Execute `query` on behalf of `actor`."""
        ...
