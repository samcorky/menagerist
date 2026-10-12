import uuid

import pytest

from app.entrypoints.api.shared.access_policy import OwnerAccessPolicy
from app.shared_kernel.access_scope import AccessScope
from app.shared_kernel.actor import SYSTEM_ACTOR, Actor
from app.shared_kernel.errors import NotFoundError

ALICE = Actor(id=uuid.uuid4(), roles=frozenset({"member"}))
BOB = Actor(id=uuid.uuid4(), roles=frozenset({"member"}))
ADMIN = Actor(id=uuid.uuid4(), roles=frozenset({"admin"}))
policy = OwnerAccessPolicy()


def test_scope_is_the_actors_own_content() -> None:
    """Scope is the actors own content."""
    assert policy.scope_for(ALICE) == AccessScope.of(ALICE.id)
    assert policy.scope_for(ADMIN) == AccessScope.of(ADMIN.id)


def test_system_actor_sees_everyone() -> None:
    """System actor sees everyone."""
    assert policy.scope_for(SYSTEM_ACTOR) == AccessScope.everyone()


def test_owner_may_view_modify_and_delete() -> None:
    """Owner may view modify and delete."""
    policy.assert_can_view(ALICE, ALICE.id)
    policy.assert_can_modify(ALICE, ALICE.id)
    policy.assert_can_delete(ALICE, ALICE.id)


def test_system_actor_may_act_on_anything() -> None:
    """System actor may act on anything."""
    for owner in (ALICE.id, None):
        policy.assert_can_view(SYSTEM_ACTOR, owner)
        policy.assert_can_modify(SYSTEM_ACTOR, owner)
        policy.assert_can_delete(SYSTEM_ACTOR, owner)


@pytest.mark.parametrize("actor", [BOB, ADMIN])
def test_other_peoples_content_does_not_exist_for_anyone_else(actor: Actor) -> None:
    """Other peoples content does not exist for anyone else."""
    for check in (
        policy.assert_can_view,
        policy.assert_can_modify,
        policy.assert_can_delete,
    ):
        with pytest.raises(NotFoundError):
            check(actor, ALICE.id)


def test_content_with_no_owner_is_visible_to_nobody() -> None:
    """Content with no owner is visible to nobody."""
    with pytest.raises(NotFoundError):
        policy.assert_can_view(ALICE, None)
