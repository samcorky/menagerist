from typing import TYPE_CHECKING

from app.modules.identity.ports.existing_data_claim import ClaimReport

if TYPE_CHECKING:
    import uuid


class NoOpExistingDataClaim:
    """`ExistingDataClaim` that claims nothing, until the real bridge is wired."""

    async def claim(self, owner_id: uuid.UUID) -> ClaimReport:
        """Report that nothing was claimed."""
        return ClaimReport()
