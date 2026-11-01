from typing import TYPE_CHECKING

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.modules.identity.application.get_setup_status import (
    GetSetupStatus,
    GetSetupStatusQuery,
)
from app.modules.identity.ports.unit_of_work import IdentityRepos
from app.shared_kernel.actor import ANONYMOUS_ACTOR

if TYPE_CHECKING:
    from tests.modules.identity.conftest import MakeUser, World


async def test_setup_is_required_only_while_there_are_no_accounts(
    world: World, make_user: MakeUser
) -> None:
    """Status flips once the first account exists."""
    use_case = GetSetupStatus(
        IdentityRepos(
            users=world.users,
            sessions=world.sessions,
            attempts=world.attempts,
            tokens=world.tokens,
        ),
        get_access_guard(),
    )

    assert await use_case.handle(GetSetupStatusQuery(), ANONYMOUS_ACTOR) is True
    await world.users.add(make_user("alice"))
    assert await use_case.handle(GetSetupStatusQuery(), ANONYMOUS_ACTOR) is False
