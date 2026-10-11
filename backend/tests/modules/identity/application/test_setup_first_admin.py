from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
import time_machine

from app.modules.identity.application.setup_first_admin import SetupFirstAdminCommand
from app.modules.identity.domain.errors import (
    InvalidPasswordError,
    InvalidUserError,
    SetupAlreadyDoneError,
)
from app.modules.identity.domain.user import Role
from app.modules.identity.ports.existing_data_claim import ClaimReport
from app.shared_kernel.actor import ANONYMOUS_ACTOR

if TYPE_CHECKING:
    from tests.modules.identity.application.conftest import MakeCases, MakeClaim
    from tests.modules.identity.conftest import MakeUser, World

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)


def _command(**overrides: str) -> SetupFirstAdminCommand:
    values = {
        "username": "Admin",
        "display_name": "Admin",
        "password": "password-123",
    } | overrides
    return SetupFirstAdminCommand(**values)


@time_machine.travel(NOW, tick=False)
async def test_setup_creates_a_signed_in_admin_and_claims_existing_data(
    world: World, make_cases: MakeCases, make_claim: MakeClaim
) -> None:
    """The first account is an admin with a live session; data is claimed once."""
    claim = make_claim(ClaimReport(counts={"collections": 2}))
    cases = make_cases(claim)

    result = await cases.setup.handle(_command(), ANONYMOUS_ACTOR)

    assert result.user.role is Role.ADMIN
    assert result.user.username == "admin"
    assert not result.user.password_expired
    assert result.token == "token-1"
    assert result.claim.counts == {"collections": 2}
    assert claim.owners == [result.user.id]
    assert await world.users.count() == 1
    assert world.uow.committed


async def test_setup_refused_once_an_account_exists(
    world: World, make_user: MakeUser, make_cases: MakeCases, make_claim: MakeClaim
) -> None:
    """A second setup is a conflict and writes nothing."""
    await world.users.add(make_user("alice"))
    claim = make_claim(ClaimReport())
    cases = make_cases(claim)

    with pytest.raises(SetupAlreadyDoneError):
        await cases.setup.handle(_command(), ANONYMOUS_ACTOR)

    assert not world.uow.committed
    assert claim.owners == []
    assert await world.users.count() == 1


async def test_setup_validates_the_password_and_username(
    world: World, make_cases: MakeCases
) -> None:
    """Weak passwords and bad usernames are rejected before anything is stored."""
    cases = make_cases()

    with pytest.raises(InvalidPasswordError):
        await cases.setup.handle(_command(password="short"), ANONYMOUS_ACTOR)
    with pytest.raises(InvalidUserError):
        await cases.setup.handle(_command(username="a b"), ANONYMOUS_ACTOR)

    assert not world.uow.committed
    assert await world.users.count() == 0


async def test_setup_refused_when_another_setup_wins_the_race(
    world: World,
    make_cases: MakeCases,
    make_claim: MakeClaim,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An account that appears after the unlocked check is caught by the locked one."""
    counts = iter([0, 1])

    async def count() -> int:
        return next(counts)

    monkeypatch.setattr(world.users, "count", count)
    claim = make_claim(ClaimReport())
    cases = make_cases(claim)

    with pytest.raises(SetupAlreadyDoneError):
        await cases.setup.handle(_command(), ANONYMOUS_ACTOR)

    assert not world.uow.committed
    assert claim.owners == []
    assert world.users._users == {}
