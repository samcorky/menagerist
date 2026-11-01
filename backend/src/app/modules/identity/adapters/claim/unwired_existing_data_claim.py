from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid

    from app.modules.identity.ports.existing_data_claim import ClaimReport


class UnwiredExistingDataClaim:
    """Default `ExistingDataClaim`: refuses, so a missing bridge fails closed.

    The entrypoint must replace it; otherwise setup would succeed while all
    existing content stayed ownerless.
    """

    async def claim(self, owner_id: uuid.UUID) -> ClaimReport:
        """Fail: no real claim has been wired.

        Raises:
            RuntimeError: Always.
        """
        raise RuntimeError(
            "No ExistingDataClaim is wired; first-run setup cannot hand over "
            + "existing content. Wire the entrypoint's claim bridge."
        )
