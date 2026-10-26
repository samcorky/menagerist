import uuid

import pytest

from app.entrypoints.api.shared.authorisation import (
    ADMIN_ONLY_ACTIONS,
    CONTENT_PERMISSIONS,
    MEMBER_PERMISSIONS,
    RoleAuthorisationAdapter,
)
from app.entrypoints.api.shared.permissions import ALL_PERMISSIONS, expand
from app.modules.graph.application.permissions import GraphPermission
from app.modules.identity.application.permissions import IdentityPermission
from app.shared_kernel.actor import SYSTEM_ACTOR, Actor
from app.shared_kernel.errors import ForbiddenError

MEMBER = Actor(id=uuid.uuid4(), roles=frozenset({"member"}))
ADMIN = Actor(id=uuid.uuid4(), roles=frozenset({"admin"}))
REVOKE = IdentityPermission.REVOKE_SESSION
LIST = IdentityPermission.LIST_SESSIONS


CONTENT_VALUES = frozenset(
    {
        "graph:item:read",
        "graph:item:write",
        "graph:item:purge",
        "graph:type:read",
        "graph:type:write",
        "media:item:read",
        "media:item:write",
        "collections:collection:read",
        "collections:collection:write",
        "collections:collection:purge",
        "presets:preset:read",
        "presets:preset:write",
        "examples:pack:read",
        "examples:pack:install",
        "backup:own_data:export",
        "backup:own_data:import",
    }
)


def test_the_default_member_grant_is_the_content_set() -> None:
    """Members hold the content permissions and none of the admin ones."""
    assert MEMBER_PERMISSIONS == CONTENT_PERMISSIONS
    assert frozenset(CONTENT_PERMISSIONS) == CONTENT_VALUES
    assert not CONTENT_PERMISSIONS & ADMIN_ONLY_ACTIONS
    assert ALL_PERMISSIONS - MEMBER_PERMISSIONS == ADMIN_ONLY_ACTIONS
    assert len(ALL_PERMISSIONS) == 34


def test_the_admin_only_set_matches_the_catalogue() -> None:
    """Structure, identity, diagnostics and backups are admin-only."""
    assert (
        frozenset(
            {
                "graph:node_type:delete",
                "graph:edge_type:delete",
                "graph:node_type:purge_attribute",
                "graph:edge_type:purge_attribute",
                "identity:user:create",
                "identity:user:list",
                "identity:user:update",
                "identity:user:reset_password",
                "identity:user:unlock",
                "identity:session:list",
                "identity:session:revoke",
                "system:diagnostics:read",
                "scheduling:job:read",
                "scheduling:job:run",
                "backup:archive:create",
                "backup:archive:read",
                "backup:archive:restore",
                "backup:archive:delete",
            }
        )
        == ADMIN_ONLY_ACTIONS
    )


async def test_members_are_forbidden_exactly_the_admin_only_actions() -> None:
    """Members are refused the admin-only set and allowed everything else."""
    adapter = RoleAuthorisationAdapter()
    for permission in ALL_PERMISSIONS:
        if permission in ADMIN_ONLY_ACTIONS:
            with pytest.raises(ForbiddenError):
                await adapter.check(MEMBER, permission)
        else:
            await adapter.check(MEMBER, permission)


async def test_admins_and_the_system_hold_every_permission() -> None:
    """Admins and the system pass every catalogue check."""
    adapter = RoleAuthorisationAdapter()
    for permission in ALL_PERMISSIONS:
        await adapter.check(ADMIN, permission)
        await adapter.check(SYSTEM_ACTOR, permission)


async def test_unknown_permissions_are_denied_to_everyone() -> None:
    """A string outside the catalogue is denied, admin or not."""
    adapter = RoleAuthorisationAdapter()
    for actor in (MEMBER, ADMIN, SYSTEM_ACTOR):
        with pytest.raises(ForbiddenError):
            await adapter.check(actor, "nonsense:thing:do")


def test_effective_permissions_by_role() -> None:
    """Admin and system get everything; members get the content set."""
    adapter = RoleAuthorisationAdapter()
    assert adapter.effective_permissions(ADMIN) == ALL_PERMISSIONS
    assert adapter.effective_permissions(SYSTEM_ACTOR) == ALL_PERMISSIONS
    assert adapter.effective_permissions(MEMBER) == expand(CONTENT_PERMISSIONS)


async def test_granted_permissions_expand_through_implications() -> None:
    """A member granted REVOKE_SESSION also holds LIST_SESSIONS."""
    adapter = RoleAuthorisationAdapter(member_permissions=frozenset({REVOKE}))
    assert adapter.effective_permissions(MEMBER) == frozenset({REVOKE, LIST})
    await adapter.check(MEMBER, LIST)
    with pytest.raises(ForbiddenError):
        await adapter.check(MEMBER, GraphPermission.DELETE_EDGE_TYPE)


def _token_actor(base: Actor, *grants: str) -> Actor:
    return Actor(id=base.id, roles=base.roles, grants=frozenset(grants))


def test_token_actor_holds_its_grants_and_their_implications_only() -> None:
    """A member token with item write holds item write and the implied read."""
    held = RoleAuthorisationAdapter().effective_permissions(
        _token_actor(MEMBER, "graph:item:write")
    )
    assert held == {GraphPermission.ITEM_WRITE, GraphPermission.ITEM_READ}


def test_admin_token_never_holds_admin_permissions() -> None:
    """An admin's token is bounded by its grants, not by the admin role."""
    held = RoleAuthorisationAdapter().effective_permissions(
        _token_actor(ADMIN, "graph:item:write")
    )
    assert held == {GraphPermission.ITEM_WRITE, GraphPermission.ITEM_READ}


def test_a_grant_outside_the_owners_role_adds_nothing() -> None:
    """A member cannot gain an admin permission by granting it to a token."""
    held = RoleAuthorisationAdapter().effective_permissions(
        _token_actor(MEMBER, "identity:user:list", "graph:item:read")
    )
    assert held == {GraphPermission.ITEM_READ}


def test_unknown_grant_strings_add_nothing() -> None:
    """Grant strings naming no catalogue permission deny."""
    adapter = RoleAuthorisationAdapter()
    assert adapter.effective_permissions(_token_actor(MEMBER, "nope:x:y")) == set()


def test_losing_the_role_that_held_a_permission_removes_it_from_the_token() -> None:
    """The token is a ceiling: the owner's current role still decides."""
    adapter = RoleAuthorisationAdapter(member_permissions=frozenset())
    held = adapter.effective_permissions(_token_actor(MEMBER, "graph:item:read"))
    assert held == set()


def test_session_actor_is_unchanged_by_the_ceiling() -> None:
    """`grants=None` leaves the member and admin sets as they were."""
    adapter = RoleAuthorisationAdapter()
    assert adapter.effective_permissions(MEMBER) == expand(MEMBER_PERMISSIONS)
    assert adapter.effective_permissions(ADMIN) == ALL_PERMISSIONS
