from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.modules.identity.domain.session import Session
from app.modules.identity.domain.user import User

if TYPE_CHECKING:
    from app.modules.identity.ports.session_token_generator import SessionTokenGenerator
    from app.modules.identity.ports.unit_of_work import IdentityRepos


@dataclass(kw_only=True, frozen=True)
class SignedInResult:
    """A user and the secret token of the session just started for them."""

    user: User
    token: str = field(repr=False)


async def start_session(
    repos: IdentityRepos,
    tokens: SessionTokenGenerator,
    user: User,
    ttl: timedelta,
) -> str:
    """Store a new session for `user` and return its secret token."""
    token = tokens.new_token()
    session = Session.create(
        user_id=user.id,
        token_hash=tokens.token_hash(token),
        now=datetime.now(UTC),
        ttl=ttl,
    )
    await repos.sessions.add(session)
    return token
