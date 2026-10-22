from typing import Self

from app.shared_kernel.permission import PermissionEnum


class _Plain(PermissionEnum):
    ONE = "test:plain:one"


class _Chained(PermissionEnum):
    WIDE = "test:chained:wide"
    NARROW = "test:chained:narrow"

    def implied(self) -> frozenset[Self]:
        if self is type(self).WIDE:
            return frozenset({_Chained.NARROW})
        return frozenset()


def test_implied_defaults_to_nothing() -> None:
    """A member that does not override `implied` implies nothing."""
    assert _Plain.ONE.implied() == frozenset()


def test_subclass_overrides_implied() -> None:
    """A subclass declares its own implications."""
    assert _Chained.WIDE.implied() == frozenset({_Chained.NARROW})
    assert _Chained.NARROW.implied() == frozenset()
