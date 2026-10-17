import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.modules.identity.domain.session import Session
from app.modules.identity.domain.user import User

if TYPE_CHECKING:
    from app.modules.identity.application.client_device import ClientDevice
    from app.modules.identity.ports.session_token_generator import SessionTokenGenerator
    from app.modules.identity.ports.unit_of_work import IdentityRepos


@dataclass(kw_only=True, frozen=True)
class SignedInResult:
    """A user and the secret token of the session just started for them."""

    user: User
    token: str = field(repr=False)
    session_id: uuid.UUID


@dataclass(kw_only=True, frozen=True)
class StartedSession:
    """A new session's secret token and its row id."""

    token: str = field(repr=False)
    session_id: uuid.UUID


async def start_session(
    repos: IdentityRepos,
    tokens: SessionTokenGenerator,
    user: User,
    ttl: timedelta,
    *,
    client_ip: str | None = None,
    device: ClientDevice | None = None,
) -> StartedSession:
    """Store a new session for `user` and return its secret token and id."""
    token = tokens.new_token()
    session = Session.create(
        user_id=user.id,
        token_hash=tokens.token_hash(token),
        now=datetime.now(UTC),
        ttl=ttl,
        user_agent=device.user_agent if device is not None else None,
        client_ip=client_ip,
        client_platform=device.platform if device is not None else None,
        client_mobile=device.mobile if device is not None else None,
    )
    await repos.sessions.add(session)
    return StartedSession(token=token, session_id=session.id)
