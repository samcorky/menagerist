import uuid

import pytest

from app.entrypoints.api.shared.authorization import (
    ADMIN_ONLY_ACTIONS,
    MEMBER_PERMISSIONS,
    RoleAuthorizationAdapter,
)
from app.entrypoints.api.shared.permissions import ALL_PERMISSIONS
from app.modules.graph.application.permissions import GraphPermission
from app.shared_kernel.actor import SYSTEM_ACTOR, Actor
from app.shared_kernel.errors import ForbiddenError

MEMBER = Actor(id=uuid.uuid4(), roles=frozenset({"member"}))
ADMIN = Actor(id=uuid.uuid4(), roles=frozenset({"admin"}))
DELETE = GraphPermission.DELETE_NODE_TYPE
PURGE = GraphPermission.PURGE_NODE_TYPE_ATTRIBUTE


def test_the_default_member_grant_is_empty() -> None:
    """Members hold nothing beyond signing in today."""
    assert frozenset() == MEMBER_PERMISSIONS
    assert ALL_PERMISSIONS - MEMBER_PERMISSIONS == ADMIN_ONLY_ACTIONS


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
                "backup:archive:create",
                "backup:archive:read",
                "backup:archive:restore",
                "backup:archive:delete",
            }
        )
        == ADMIN_ONLY_ACTIONS
    )


async def test_members_are_forbidden_catalogue_permissions() -> None:
    """Members hold none of the catalogue permissions by default."""
    adapter = RoleAuthorizationAdapter()
    for permission in ALL_PERMISSIONS:
        with pytest.raises(ForbiddenError):
            await adapter.check(MEMBER, permission)


async def test_admins_and_the_system_hold_every_permission() -> None:
    """Admins and the system pass every catalogue check."""
    adapter = RoleAuthorizationAdapter()
    for permission in ALL_PERMISSIONS:
        await adapter.check(ADMIN, permission)
        await adapter.check(SYSTEM_ACTOR, permission)


async def test_unknown_permissions_are_denied_to_everyone() -> None:
    """A string outside the catalogue is denied, admin or not."""
    adapter = RoleAuthorizationAdapter()
    for actor in (MEMBER, ADMIN, SYSTEM_ACTOR):
        with pytest.raises(ForbiddenError):
            await adapter.check(actor, "nonsense:thing:do")


def test_effective_permissions_by_role() -> None:
    """Admin and system get everything; members get the default grant."""
    adapter = RoleAuthorizationAdapter()
    assert adapter.effective_permissions(ADMIN) == ALL_PERMISSIONS
    assert adapter.effective_permissions(SYSTEM_ACTOR) == ALL_PERMISSIONS
    assert adapter.effective_permissions(MEMBER) == frozenset()


async def test_granted_permissions_expand_through_implications() -> None:
    """A member granted DELETE also holds what DELETE implies."""
    adapter = RoleAuthorizationAdapter(
        member_permissions=frozenset({DELETE}),
        implies={DELETE: frozenset({PURGE})},
    )
    assert adapter.effective_permissions(MEMBER) == frozenset({DELETE, PURGE})
    await adapter.check(MEMBER, PURGE)
    with pytest.raises(ForbiddenError):
        await adapter.check(MEMBER, GraphPermission.DELETE_EDGE_TYPE)
