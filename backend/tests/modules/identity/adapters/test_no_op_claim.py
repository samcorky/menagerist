import uuid

import pytest

from app.modules.identity.adapters.claim.no_op_existing_data_claim import (
    NoOpExistingDataClaim,
)
from app.modules.identity.adapters.claim.unwired_existing_data_claim import (
    UnwiredExistingDataClaim,
)


async def test_no_op_claim_reports_nothing_claimed() -> None:
    """Until the real bridge is wired, nothing is claimed."""
    report = await NoOpExistingDataClaim().claim(uuid.uuid7())
    assert report.counts == {}


async def test_unwired_claim_fails_closed() -> None:
    """The default refuses, so a lost wiring cannot leave content ownerless."""
    with pytest.raises(RuntimeError, match="No ExistingDataClaim is wired"):
        await UnwiredExistingDataClaim().claim(uuid.uuid7())
