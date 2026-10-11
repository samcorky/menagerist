"""The anonymous actor never matches content owned by another sentinel."""

import uuid

from app.entrypoints.api.shared.access_policy import OwnerAccessPolicy
from app.shared_kernel.actor import ANONYMOUS_ACTOR, SYSTEM_ACTOR


def test_anonymous_has_its_own_id() -> None:
    """Anonymous shares no id with the system actor."""
    assert ANONYMOUS_ACTOR.id != SYSTEM_ACTOR.id


def test_anonymous_scope_matches_no_sentinel_owned_row() -> None:
    """Content owned by UUID(0) or UUID(1) is invisible to the anonymous actor."""
    scope = OwnerAccessPolicy().scope_for(ANONYMOUS_ACTOR)

    assert not scope.covers(uuid.UUID(int=0))
    assert not scope.covers(uuid.UUID(int=1))
    assert not scope.is_everyone
