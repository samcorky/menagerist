import uuid

from app.shared_kernel.actor import ANONYMOUS_ACTOR, SYSTEM_ACTOR, Actor


def test_is_admin_only_for_the_admin_role() -> None:
    """Is admin only for the admin role."""
    assert Actor(id=uuid.uuid4(), roles=frozenset({"admin"})).is_admin
    assert not Actor(id=uuid.uuid4(), roles=frozenset({"member"})).is_admin
    assert not SYSTEM_ACTOR.is_admin
    assert not ANONYMOUS_ACTOR.is_admin


def test_is_system_only_for_the_system_actor() -> None:
    """Is system only for the system actor."""
    assert SYSTEM_ACTOR.is_system
    assert not Actor(id=uuid.uuid4(), roles=frozenset({"admin"})).is_system
    assert not ANONYMOUS_ACTOR.is_system


def test_is_anonymous_only_for_the_anonymous_actor() -> None:
    """Is anonymous only for the anonymous actor."""
    assert ANONYMOUS_ACTOR.is_anonymous
    assert not SYSTEM_ACTOR.is_anonymous
    assert not Actor(id=uuid.uuid4(), roles=frozenset({"member"})).is_anonymous
