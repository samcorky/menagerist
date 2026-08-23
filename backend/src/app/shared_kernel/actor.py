import uuid
from dataclasses import dataclass, field


@dataclass(frozen=True, kw_only=True)
class Actor:
    """Whoever - or whatever - is driving a use case.

    Carried alongside a unit of work through every command/query, the same
    way a request carries an authenticated identity. `roles` is opaque to
    this type - what a role permits is decided by whatever
    `AuthorizationPort` adapter is wired in, not by `Actor` itself.
    """

    id: uuid.UUID
    roles: frozenset[str] = field(default_factory=frozenset)


SYSTEM_ACTOR = Actor(id=uuid.UUID(int=0), roles=frozenset({"system"}))
"""Sentinel actor for background jobs and other internal, user-less callers."""
