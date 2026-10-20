from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Mapping


class UserImportValidator(Protocol):
    """Validate incoming content through the owning bounded contexts."""

    async def validate(self, table: str, row: Mapping[str, object]) -> None:
        """Reject rows that violate the owning context's domain invariants."""
        ...
