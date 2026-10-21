import dataclasses
import uuid

import pytest

from app.shared_kernel.content_filter import ContentFilter


def test_of_restricts_to_one_user() -> None:
    """Of restricts to one user."""
    user_id = uuid.uuid4()
    scope = ContentFilter.of(user_id)
    assert scope.user_id == user_id
    assert not scope.is_everyone


def test_everyone_has_no_user() -> None:
    """Everyone has no user."""
    scope = ContentFilter.everyone()
    assert scope.user_id is None
    assert scope.is_everyone


def test_scopes_compare_by_value() -> None:
    """Scopes compare by value."""
    user_id = uuid.uuid4()
    assert ContentFilter.of(user_id) == ContentFilter.of(user_id)
    assert ContentFilter.of(user_id) != ContentFilter.of(uuid.uuid4())
    assert ContentFilter.everyone() == ContentFilter.everyone()
    assert ContentFilter.everyone() != ContentFilter.of(user_id)
    assert len({ContentFilter.of(user_id), ContentFilter.of(user_id)}) == 1


def test_scope_is_immutable() -> None:
    """Scope is immutable."""
    with pytest.raises(dataclasses.FrozenInstanceError):
        ContentFilter.everyone().user_id = uuid.uuid4()  # type: ignore[misc]


def test_covers_matches_owner_and_hides_ownerless_content_from_a_user() -> None:
    """A user scope covers only their own content; everyone covers all of it."""
    me, other = uuid.uuid4(), uuid.uuid4()
    assert ContentFilter.of(me).covers(me)
    assert not ContentFilter.of(me).covers(other)
    assert not ContentFilter.of(me).covers(None)
    assert ContentFilter.everyone().covers(other)
    assert ContentFilter.everyone().covers(None)
