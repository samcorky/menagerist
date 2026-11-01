import uuid

import pytest

from app.entrypoints.api.shared.access_guard import RoleAccessGuard, get_access_guard
from app.entrypoints.api.shared.access_policy import OwnerAccessPolicy
from app.entrypoints.api.shared.authorisation import RoleAuthorisationAdapter
from app.modules.graph.application.permissions import GraphPermission
from app.modules.media.application.permissions import MediaPermission
from app.shared_kernel.access import (
    Access,
    Content,
    OwnAccount,
    Public,
    Requires,
    System,
)
from app.shared_kernel.actor import ANONYMOUS_ACTOR, SYSTEM_ACTOR, Actor
from app.shared_kernel.errors import ForbiddenError, NotFoundError

MEMBER = Actor(id=uuid.uuid4(), roles=frozenset({"member"}))
ADMIN = Actor(id=uuid.uuid4(), roles=frozenset({"admin"}))
PERMISSION = GraphPermission.DELETE_NODE_TYPE
ACTORS = {
    "anonymous": ANONYMOUS_ACTOR,
    "system": SYSTEM_ACTOR,
    "member": MEMBER,
    "admin": ADMIN,
}
OWNERSHIP_CHECKS = ("assert_can_view", "assert_can_modify", "assert_can_delete")


class _Authorisation:
    """Allows or denies everything and records the actions it was asked about."""

    def __init__(self, *, allow: bool = True) -> None:
        self.allow = allow
        self.actions: list[str] = []

    async def check(self, actor: Actor, action: str) -> None:
        self.actions.append(action)
        if not self.allow:
            raise ForbiddenError("You do not have permission to do that.")


# Stance -> the actors it allows, as in the spec's allow/refuse table.
ALLOWED: dict[str, tuple[Access, set[str]]] = {
    "public": (Public(), {"anonymous", "system", "member", "admin"}),
    "system": (System(), {"system"}),
    "own_account": (OwnAccount(), {"member", "admin"}),
    "requires": (Requires(PERMISSION), {"system", "member", "admin"}),
    "content_with_permission": (
        Content(MediaPermission.ITEM_READ),
        {"system", "member", "admin"},
    ),
}


@pytest.mark.parametrize("actor_name", list(ACTORS))
@pytest.mark.parametrize("stance_name", list(ALLOWED))
async def test_stance_table(stance_name: str, actor_name: str) -> None:
    """Each stance allows and refuses exactly the actors in the spec."""
    access, allowed = ALLOWED[stance_name]
    guard = RoleAccessGuard(_Authorisation(), OwnerAccessPolicy())
    if actor_name in allowed:
        await guard.check(ACTORS[actor_name], access)
    else:
        with pytest.raises(ForbiddenError, match="do not have permission"):
            await guard.check(ACTORS[actor_name], access)


async def test_requires_denies_anonymous_before_any_permission_lookup() -> None:
    """The anonymous actor never reaches the authorisation port."""
    authorisation = _Authorisation(allow=True)
    guard = RoleAccessGuard(authorisation, OwnerAccessPolicy())
    with pytest.raises(ForbiddenError):
        await guard.check(ANONYMOUS_ACTOR, Requires(PERMISSION))
    assert authorisation.actions == []


async def test_requires_delegates_to_the_authorisation_port() -> None:
    """A member's permission is decided by the port, and its refusal propagates."""
    allowing = _Authorisation(allow=True)
    await RoleAccessGuard(allowing, OwnerAccessPolicy()).check(
        MEMBER, Requires(PERMISSION)
    )
    assert allowing.actions == [PERMISSION]
    denying = RoleAccessGuard(_Authorisation(allow=False), OwnerAccessPolicy())
    with pytest.raises(ForbiddenError):
        await denying.check(MEMBER, Requires(PERMISSION))


async def test_content_permission_denies_anonymous_before_any_lookup() -> None:
    """The anonymous actor never reaches the authorisation port."""
    authorisation = _Authorisation(allow=True)
    guard = RoleAccessGuard(authorisation, OwnerAccessPolicy())
    with pytest.raises(ForbiddenError):
        await guard.check(ANONYMOUS_ACTOR, Content(MediaPermission.ITEM_READ))
    assert authorisation.actions == []


async def test_content_permission_delegates_to_the_authorisation_port() -> None:
    """A member's content permission is decided by the port."""
    allowing = _Authorisation(allow=True)
    await RoleAccessGuard(allowing, OwnerAccessPolicy()).check(
        MEMBER, Content(MediaPermission.ITEM_READ)
    )
    assert allowing.actions == [MediaPermission.ITEM_READ]


async def test_content_permission_fails_for_a_member_with_an_empty_grant() -> None:
    """With no member grant, a member is refused a permissioned stance."""
    guard = RoleAccessGuard(
        RoleAuthorisationAdapter(member_permissions=frozenset()), OwnerAccessPolicy()
    )
    with pytest.raises(ForbiddenError):
        await guard.check(MEMBER, Content(MediaPermission.ITEM_READ))
    await guard.check(ADMIN, Content(MediaPermission.ITEM_READ))


@pytest.mark.parametrize("actor", list(ACTORS.values()), ids=list(ACTORS))
def test_scope_matches_the_owner_policy(actor: Actor) -> None:
    """The guard's scope is the policy's scope."""
    policy = OwnerAccessPolicy()
    assert RoleAccessGuard(_Authorisation(), policy).scope_for(actor) == (
        policy.scope_for(actor)
    )


@pytest.mark.parametrize("name", OWNERSHIP_CHECKS)
@pytest.mark.parametrize("actor", list(ACTORS.values()), ids=list(ACTORS))
def test_ownership_checks_match_the_owner_policy(actor: Actor, name: str) -> None:
    """Own, foreign and ownerless content get the policy's verdict."""
    policy = OwnerAccessPolicy()
    guard = RoleAccessGuard(_Authorisation(), policy)
    for owner in (actor.id, MEMBER.id, None):
        try:
            getattr(policy, name)(actor, owner)
        except NotFoundError:
            with pytest.raises(NotFoundError):
                getattr(guard, name)(actor, owner)
        else:
            getattr(guard, name)(actor, owner)


def test_get_access_guard_is_process_wide() -> None:
    """The same guard instance is returned each time."""
    assert get_access_guard() is get_access_guard()


async def test_an_unknown_stance_is_an_error_not_a_silent_gap() -> None:
    """A stance the guard has no rule for fails loudly, never as an unbound name."""
    guard = RoleAccessGuard(_Authorisation(), OwnerAccessPolicy())
    with pytest.raises(AssertionError):
        await guard.check(MEMBER, object())  # type: ignore[arg-type]


async def test_token_actor_is_refused_own_account_but_not_public() -> None:
    """Account management is session-only; public routes stay open."""
    token_actor = Actor(
        id=uuid.uuid4(), roles=frozenset({"member"}), grants=frozenset({"x:y:z"})
    )
    guard = RoleAccessGuard(_Authorisation(), OwnerAccessPolicy())
    with pytest.raises(ForbiddenError, match="do not have permission"):
        await guard.check(token_actor, OwnAccount())
    with pytest.raises(ForbiddenError):
        await guard.check(token_actor, System())
    await guard.check(token_actor, Public())


async def test_token_actor_content_check_goes_to_the_authorisation_port() -> None:
    """Content stances still reach the port, where the intersection happens."""
    token_actor = Actor(
        id=uuid.uuid4(),
        roles=frozenset({"member"}),
        grants=frozenset({"media:item:read"}),
    )
    guard = RoleAccessGuard(RoleAuthorisationAdapter(), OwnerAccessPolicy())
    await guard.check(token_actor, Content(MediaPermission.ITEM_READ))
    with pytest.raises(ForbiddenError):
        await guard.check(token_actor, Content(MediaPermission.ITEM_WRITE))
