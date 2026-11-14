import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.modules.identity.application.client_device import ClientDevice
from app.modules.identity.domain.device import Device
from app.modules.identity.domain.session import Session
from app.modules.identity.domain.user import User

if TYPE_CHECKING:
    from app.modules.identity.ports.session_token_generator import SessionTokenGenerator
    from app.modules.identity.ports.unit_of_work import IdentityRepos


@dataclass(kw_only=True, frozen=True)
class SignedInResult:
    """A user, the secret token of their new session and their device cookie."""

    user: User
    token: str = field(repr=False)
    session_id: uuid.UUID
    device_token: str = field(repr=False)


@dataclass(kw_only=True, frozen=True)
class StartedSession:
    """A new session's secret token and row id, and the browser's device cookie."""

    token: str = field(repr=False)
    session_id: uuid.UUID
    device_token: str = field(repr=False)
    device_id: uuid.UUID


async def known_device(
    repos: IdentityRepos,
    tokens: SessionTokenGenerator,
    device_token: str | None,
    *,
    username: str,
    now: datetime,
) -> Device | None:
    """Return the live device behind `device_token` if it is `username`'s.

    The lookup runs by the cookie alone, before anything about `username` is
    known, so its cost does not depend on whether the account exists.
    """
    if not device_token:
        return None
    device = await repos.devices.get_by_token_hash(tokens.token_hash(device_token))
    if device is None or device.is_expired(now):
        return None
    owner = await repos.users.get(device.user_id)
    if owner is None or owner.username != username.lower():
        return None
    return device


async def start_session(
    repos: IdentityRepos,
    tokens: SessionTokenGenerator,
    user: User,
    ttl: timedelta,
    *,
    device_ttl: timedelta,
    client_ip: str | None = None,
    device: ClientDevice | None = None,
    device_token: str | None = None,
) -> StartedSession:
    """Store a new session for `user` in a remembered browser.

    The browser is the device behind `device_token` when that is a live device of
    `user`'s: its older sessions are ended (the browser held only one session
    cookie, so they can no longer be used) and its details refreshed. Otherwise a
    new device is remembered with a new token.
    """
    now = datetime.now(UTC)
    token = tokens.new_token()
    client = device if device is not None else ClientDevice()
    remembered = (
        await repos.devices.get_by_token_hash(tokens.token_hash(device_token))
        if device_token
        else None
    )
    if (
        device_token
        and remembered is not None
        and remembered.user_id == user.id
        and not remembered.is_expired(now)
    ):
        await repos.sessions.delete_for_device(remembered.id)
        remembered.seen(
            now,
            ttl=device_ttl,
            user_agent=client.user_agent,
            platform=client.platform,
            mobile=client.mobile,
        )
        await repos.devices.save(remembered)
        kept_token = device_token
    else:
        kept_token = tokens.new_token()
        remembered = Device.create(
            user_id=user.id,
            token_hash=tokens.token_hash(kept_token),
            now=now,
            ttl=device_ttl,
            user_agent=client.user_agent,
            platform=client.platform,
            mobile=client.mobile,
        )
        await repos.devices.add(remembered)
    session = Session.create(
        user_id=user.id,
        token_hash=tokens.token_hash(token),
        now=now,
        ttl=ttl,
        user_agent=client.user_agent,
        client_ip=client_ip,
        client_platform=client.platform,
        client_mobile=client.mobile,
        device_id=remembered.id,
        display_mode=client.display_mode,
    )
    await repos.sessions.add(session)
    return StartedSession(
        token=token,
        session_id=session.id,
        device_token=kept_token,
        device_id=remembered.id,
    )
