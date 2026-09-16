import uuid
from dataclasses import dataclass, field


@dataclass(frozen=True, kw_only=True)
class Actor:
    """Entity or caller driving a use case."""

    id: uuid.UUID
    roles: frozenset[str] = field(default_factory=frozenset)


SYSTEM_ACTOR = Actor(id=uuid.UUID(int=0), roles=frozenset({"system"}))
"""Sentinel actor for background jobs and internal callers."""
