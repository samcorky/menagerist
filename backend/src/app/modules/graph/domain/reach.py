"""Following one relationship type through several hops."""

import uuid
from dataclasses import dataclass
from typing import Final, Literal

from app.shared_kernel.errors import ValidationError

MAX_REACH_DEPTH: Final = 25
MAX_REACHED: Final = 10_000

type ReachDirection = Literal["out", "in"]


class InvalidReachDepthError(ValidationError):
    """Raised when a depth is below one or above `MAX_REACH_DEPTH`."""


class ReachTooLargeError(ValidationError):
    """Raised when a walk finds more than `MAX_REACHED` items or runs too long."""

    def __init__(self) -> None:
        super().__init__(
            "This reaches too many items to follow. Try fewer steps or narrow it down."
        )


@dataclass(frozen=True, kw_only=True)
class Reached:
    """An item found by following a relationship, and how many hops away it is."""

    node_id: uuid.UUID
    depth: int


def check_depth(depth: int) -> int:
    """Return `depth` if it is between one and `MAX_REACH_DEPTH`, else refuse it."""
    if not 1 <= depth <= MAX_REACH_DEPTH:
        msg = f"Depth must be between 1 and {MAX_REACH_DEPTH}."
        raise InvalidReachDepthError(msg)
    return depth
