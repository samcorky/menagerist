import uuid
from dataclasses import dataclass, field


@dataclass(frozen=True, kw_only=True)
class Actor:
    """Entity or caller driving a use case."""

    id: uuid.UUID
    roles: frozenset[str] = field(default_factory=frozenset)
    grants: frozenset[str] | None = None
    """Permission ceiling of a token request; `None` for a session (no ceiling)."""

    @property
    def is_admin(self) -> bool:
        """Whether the actor holds the administrator role."""
        return "admin" in self.roles

    @property
    def is_system(self) -> bool:
        """Whether this is the system actor."""
        return "system" in self.roles

    @property
    def is_anonymous(self) -> bool:
        """Whether this is the anonymous actor."""
        return "anonymous" in self.roles


SYSTEM_ACTOR = Actor(id=uuid.UUID(int=0), roles=frozenset({"system"}))
"""Sentinel actor for background jobs and internal callers."""

ANONYMOUS_ACTOR = Actor(id=uuid.UUID(int=2), roles=frozenset({"anonymous"}))
"""Stand-in actor for flows that run before anyone is signed in.

Its id differs from every other sentinel so it can never match their content.
"""
