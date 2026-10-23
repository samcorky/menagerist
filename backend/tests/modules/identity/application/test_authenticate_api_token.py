import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import time_machine

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.modules.identity.adapters.security.secrets_api_token_generator import (
    SecretsApiTokenGenerator,
)
from app.modules.identity.application.authenticate_api_token import (
    AuthenticateApiToken,
    AuthenticateApiTokenCommand,
)
from app.shared_kernel.actor import ANONYMOUS_ACTOR

if TYPE_CHECKING:
    from tests.modules.identity.application.conftest import Cases, IssueToken
    from tests.modules.identity.conftest import MakeUser, World

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)


async def _resolve(cases: Cases, value: str) -> object:
    return await cases.authenticate_api_token.handle(
        AuthenticateApiTokenCommand(value=value), ANONYMOUS_ACTOR
    )


class SpyGenerator(SecretsApiTokenGenerator):
    """Counts hash and comparison calls."""

    def __init__(self) -> None:
        self.hashes = 0
        self.comparisons = 0

    def hash(self, secret: str) -> str:
        """Count, then hash."""
        self.hashes += 1
        return super().hash(secret)

    def matches(self, secret: str, stored_hash: str) -> bool:
        """Count, then compare."""
        self.comparisons += 1
        return super().matches(secret, stored_hash)


@time_machine.travel(NOW, tick=False)
async def test_a_valid_value_resolves_owner_and_grants(
    cases: Cases, world: World, make_user: MakeUser, issue_token: IssueToken
) -> None:
    """The result carries the user, the token id and exactly its grants."""
    user = make_user()
    await world.users.add(user)
    grants = frozenset({"graph:item:read", "media:item:read"})
    created = await issue_token(user, grants=grants)

    resolved = await cases.authenticate_api_token.handle(
        AuthenticateApiTokenCommand(value=created.plaintext), ANONYMOUS_ACTOR
    )

    assert resolved is not None
    assert resolved.user is user
    assert resolved.token_id == created.token.id
    assert resolved.grants == grants


@time_machine.travel(NOW, tick=False)
async def test_unusable_values_resolve_to_nothing(
    cases: Cases, world: World, make_user: MakeUser, issue_token: IssueToken
) -> None:
    """Malformed, unknown, wrong-secret and revoked values are all `None`."""
    user = make_user()
    await world.users.add(user)
    created = await issue_token(user)
    parsed = cases.api_tokens.parse(created.plaintext)
    assert parsed is not None
    wrong_secret = f"mnst_{parsed.token_id.hex}_{'0' * 64}"
    unknown = cases.api_tokens.new_token().plaintext

    for value in ("", "garbage", "Bearer x", wrong_secret, unknown):
        assert await _resolve(cases, value) is None
    await world.tokens.delete(created.token.id)
    assert await _resolve(cases, created.plaintext) is None


@time_machine.travel(NOW, tick=False)
async def test_an_expired_token_is_refused_and_deleted(
    cases: Cases, world: World, make_user: MakeUser, issue_token: IssueToken
) -> None:
    """Expiry is checked on use and removes the row."""
    user = make_user()
    await world.users.add(user)
    created = await issue_token(user, days=1)

    with time_machine.travel(NOW + timedelta(days=1), tick=False):
        assert await _resolve(cases, created.plaintext) is None

    assert await world.tokens.get(created.token.id) is None


@time_machine.travel(NOW, tick=False)
async def test_a_disabled_owner_is_refused(
    cases: Cases, world: World, make_user: MakeUser, issue_token: IssueToken
) -> None:
    """Disabling the user stops their tokens at once."""
    user = make_user()
    await world.users.add(user)
    created = await issue_token(user)
    user.disabled = True
    await world.users.save(user)

    assert await _resolve(cases, created.plaintext) is None


@time_machine.travel(NOW, tick=False)
async def test_a_token_whose_owner_is_gone_is_refused(
    cases: Cases, world: World, make_user: MakeUser, issue_token: IssueToken
) -> None:
    """An orphaned row authenticates nobody."""
    user = make_user()
    await world.users.add(user)
    created = await issue_token(user)
    world.users._users.pop(user.id)

    assert await _resolve(cases, created.plaintext) is None


@time_machine.travel(NOW, tick=False)
async def test_last_used_is_saved_when_unset_or_a_minute_old_only(
    cases: Cases, world: World, make_user: MakeUser, issue_token: IssueToken
) -> None:
    """The write goes through `save` and happens at most once a minute."""
    user = make_user()
    await world.users.add(user)
    created = await issue_token(user)

    async def last_used() -> datetime | None:
        stored = await world.tokens.get(created.token.id)
        assert stored is not None
        return stored.last_used_at

    assert await last_used() is None
    assert await _resolve(cases, created.plaintext) is not None
    assert await last_used() == NOW

    with time_machine.travel(NOW + timedelta(seconds=59), tick=False):
        await _resolve(cases, created.plaintext)
    assert await last_used() == NOW

    later = NOW + timedelta(minutes=1)
    with time_machine.travel(later, tick=False):
        await _resolve(cases, created.plaintext)
    assert await last_used() == later


@time_machine.travel(NOW, tick=False)
async def test_an_unknown_id_costs_the_same_as_a_wrong_secret(
    world: World, make_user: MakeUser, cases: Cases, issue_token: IssueToken
) -> None:
    """Unknown ids compare against a decoy, so nothing differs by call count."""
    user = make_user()
    await world.users.add(user)
    created = await issue_token(user)
    parsed = cases.api_tokens.parse(created.plaintext)
    assert parsed is not None

    wrong = SpyGenerator()
    ghost = SpyGenerator()
    for spy, value in (
        (wrong, f"mnst_{parsed.token_id.hex}_{'0' * 64}"),
        (ghost, f"mnst_{uuid.uuid7().hex}_{'0' * 64}"),
    ):
        handler = AuthenticateApiToken(world.uow, get_access_guard(), spy)
        spy.hashes = spy.comparisons = 0
        assert (
            await handler.handle(
                AuthenticateApiTokenCommand(value=value), ANONYMOUS_ACTOR
            )
            is None
        )

    assert (ghost.hashes, ghost.comparisons) == (wrong.hashes, wrong.comparisons)
    assert ghost.comparisons == 1


def test_the_command_repr_hides_the_value() -> None:
    """Tracebacks never show the token."""
    assert "mnst_" not in repr(AuthenticateApiTokenCommand(value="mnst_secret"))
