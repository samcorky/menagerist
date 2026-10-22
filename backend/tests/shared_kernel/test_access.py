import dataclasses

import pytest

from app.modules.graph.application.permissions import GraphPermission
from app.shared_kernel.access import Content, OwnAccount, Public, Requires, System


@pytest.mark.parametrize("stance", [Public, System, OwnAccount])
def test_field_free_stances_are_frozen_and_equal(stance: type) -> None:
    """Field-free stances compare equal and cannot be mutated."""
    assert stance() == stance()
    assert dataclasses.is_dataclass(stance)
    with pytest.raises(dataclasses.FrozenInstanceError):
        stance().x = 1  # type: ignore[attr-defined]


def test_requires_carries_its_permission() -> None:
    """Requires compares by permission."""
    one = Requires(GraphPermission.DELETE_NODE_TYPE)
    assert one.permission is GraphPermission.DELETE_NODE_TYPE
    assert one == Requires(GraphPermission.DELETE_NODE_TYPE)
    assert one != Requires(GraphPermission.PURGE_NODE_TYPE_ATTRIBUTE)


def test_content_requires_a_permission() -> None:
    """A `Content` stance without a permission is a type error."""
    with pytest.raises(TypeError):
        Content()  # type: ignore[call-arg]
