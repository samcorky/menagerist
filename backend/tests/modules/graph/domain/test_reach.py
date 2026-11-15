"""The reach depth limit."""

import pytest

from app.modules.graph.domain.reach import (
    MAX_REACH_DEPTH,
    InvalidReachDepthError,
    check_depth,
)


@pytest.mark.parametrize("depth", [1, 2, MAX_REACH_DEPTH])
def test_a_depth_within_the_limit_is_returned(depth: int) -> None:
    """One hop up to the maximum is allowed."""
    assert check_depth(depth) == depth


@pytest.mark.parametrize("depth", [0, -1, MAX_REACH_DEPTH + 1])
def test_a_depth_outside_the_limit_is_refused(depth: int) -> None:
    """Zero, negative and over-maximum depths are validation errors."""
    with pytest.raises(InvalidReachDepthError):
        check_depth(depth)


def test_the_maximum_depth_is_25() -> None:
    """The spec pins the cap at 25 hops."""
    assert MAX_REACH_DEPTH == 25
