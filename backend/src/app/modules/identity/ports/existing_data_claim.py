from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import uuid


@dataclass(kw_only=True, frozen=True)
class ClaimReport:
    """How many rows of each kind the first administrator took ownership of."""

    counts: dict[str, int] = field(default_factory=dict)


class ExistingDataClaim(Protocol):
    """Hands content that predates accounts to its first owner."""

    async def claim(self, owner_id: uuid.UUID) -> ClaimReport:
        """Make `owner_id` the owner of all unowned content."""
        ...
