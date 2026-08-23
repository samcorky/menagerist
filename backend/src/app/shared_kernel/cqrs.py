from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


class CommandHandler[TCommand, TResult](Protocol):
    """A use case that mutates state and owns its own commit boundary."""

    async def handle(self, command: TCommand, actor: Actor) -> TResult:
        """Execute `command` on behalf of `actor`."""
        ...


class QueryHandler[TQuery, TResult](Protocol):
    """A read-only use case with no commit boundary of its own."""

    async def handle(self, query: TQuery, actor: Actor) -> TResult:
        """Execute `query` on behalf of `actor`."""
        ...
