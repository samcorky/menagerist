from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.modules.identity.ports.session_token_generator import (  # noqa: TC001
    SessionTokenGenerator,
)
from app.modules.identity.ports.unit_of_work import IdentityUnitOfWork
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class SignOutCommand:
    """Request to end the session behind a token."""

    token: str

    def __repr__(self) -> str:
        """Keep the token out of logs and tracebacks."""
        return "SignOutCommand()"


class SignOut(CommandHandler[IdentityUnitOfWork, SignOutCommand, None]):
    """End a session; an unknown token is ignored."""

    def __init__(self, uow: IdentityUnitOfWork, tokens: SessionTokenGenerator) -> None:
        super().__init__(uow)
        self._tokens = tokens

    async def handle(self, command: SignOutCommand, actor: Actor) -> None:
        """Delete the session whose token is `command.token`, if any."""
        async with self._uow as repos:
            session = await repos.sessions.get_by_token_hash(
                self._tokens.token_hash(command.token)
            )
            if session is not None:
                await repos.sessions.delete(session.id)
                await self._uow.commit()
