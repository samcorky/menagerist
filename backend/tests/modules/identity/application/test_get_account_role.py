"""An account's role, for work run later on its behalf."""

import uuid
from typing import TYPE_CHECKING

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.modules.identity.application.get_account_role import (
    GetAccountRole,
    GetAccountRoleQuery,
)
from app.modules.identity.domain.user import Role
from app.modules.identity.ports.unit_of_work import IdentityRepos
from app.shared_kernel.actor import SYSTEM_ACTOR

if TYPE_CHECKING:
    from tests.modules.identity.conftest import MakeUser, World


def _query(world: World) -> GetAccountRole:
    return GetAccountRole(
        IdentityRepos(
            users=world.users,
            sessions=world.sessions,
            attempts=world.attempts,
            tokens=world.tokens,
            devices=world.devices,
        ),
        get_access_guard(),
    )


async def test_an_enabled_account_has_its_role(
    world: World, make_user: MakeUser
) -> None:
    """The role is read as it is now."""
    admin = make_user("alice", role=Role.ADMIN)
    await world.users.add(admin)
    role = await _query(world).handle(
        GetAccountRoleQuery(user_id=admin.id), SYSTEM_ACTOR
    )
    assert role == "admin"


async def test_a_disabled_or_missing_account_has_none(
    world: World, make_user: MakeUser
) -> None:
    """Work queued by either does not run."""
    disabled = make_user("bob")
    disabled.disable()
    await world.users.add(disabled)
    query = _query(world)
    for user_id in (disabled.id, uuid.uuid7()):
        found = await query.handle(GetAccountRoleQuery(user_id=user_id), SYSTEM_ACTOR)
        assert found is None
