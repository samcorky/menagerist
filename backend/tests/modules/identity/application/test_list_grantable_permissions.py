from typing import TYPE_CHECKING

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.entrypoints.api.shared.authorisation import (
    TOKEN_GRANTABLE_PERMISSIONS,
    RoleAuthorisationAdapter,
)
from app.modules.identity.application.list_grantable_permissions import (
    ListGrantablePermissions,
    ListGrantablePermissionsQuery,
)
from app.modules.identity.domain.user import Role
from app.modules.identity.ports.unit_of_work import IdentityRepos

if TYPE_CHECKING:
    from tests.modules.identity.application.conftest import ActorFor, Cases
    from tests.modules.identity.conftest import MakeUser, World

EXPECTED = sorted(p.value for p in TOKEN_GRANTABLE_PERMISSIONS)


async def test_a_member_sees_the_twelve_grantable_content_permissions(
    cases: Cases, make_user: MakeUser, actor_for: ActorFor
) -> None:
    """Backup export and import are not offered."""
    listed = await cases.list_grantable.handle(
        ListGrantablePermissionsQuery(), actor_for(make_user())
    )

    assert listed == EXPECTED
    assert len(listed) == 12
    assert not any(p.startswith("backup:") for p in listed)


async def test_an_admin_sees_the_same_list(
    cases: Cases, make_user: MakeUser, actor_for: ActorFor
) -> None:
    """No admin permission is grantable."""
    listed = await cases.list_grantable.handle(
        ListGrantablePermissionsQuery(), actor_for(make_user(role=Role.ADMIN))
    )

    assert listed == EXPECTED


async def test_a_permission_the_role_lost_disappears(
    world: World, make_user: MakeUser, actor_for: ActorFor
) -> None:
    """The list reflects what the owner holds now."""
    reduced = frozenset(
        p for p in TOKEN_GRANTABLE_PERMISSIONS if p.value != "graph:type:write"
    )
    handler = ListGrantablePermissions(
        IdentityRepos(
            users=world.users,
            sessions=world.sessions,
            attempts=world.attempts,
            tokens=world.tokens,
        ),
        get_access_guard(),
        RoleAuthorisationAdapter(member_permissions=reduced),
        grantable=frozenset(EXPECTED),
    )

    listed = await handler.handle(
        ListGrantablePermissionsQuery(), actor_for(make_user())
    )

    assert "graph:type:write" not in listed
    assert "graph:item:read" in listed
