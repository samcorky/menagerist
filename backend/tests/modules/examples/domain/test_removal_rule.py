"""Truth-table tests for the removal rule."""

import uuid

import pytest

from app.modules.examples.domain.errors import InvalidInstallationStateError
from app.modules.examples.domain.installation import EntityKind, EntityRecord, Outcome
from app.modules.examples.domain.removal import (
    KEEP_EDITED,
    KEEP_IN_USE,
    KEEP_USER_DATA,
    Action,
    decide_removal,
)


def _record(outcome: Outcome = Outcome.OWNED) -> EntityRecord:
    return EntityRecord(
        kind=EntityKind.ITEM,
        ref="a",
        label="A",
        entity_id=uuid.uuid7(),
        content_hash="h1",
        outcome=outcome,
    )


@pytest.mark.parametrize(
    ("current", "user_data", "in_use", "action", "reason"),
    [
        (None, False, False, Action.ALREADY_GONE, None),
        (None, True, True, Action.ALREADY_GONE, None),
        ("h2", False, False, Action.KEEP, KEEP_EDITED),
        ("h2", True, True, Action.KEEP, KEEP_EDITED),
        ("h1", True, True, Action.KEEP, KEEP_USER_DATA),
        ("h1", True, False, Action.KEEP, KEEP_USER_DATA),
        ("h1", False, True, Action.KEEP, KEEP_IN_USE),
        ("h1", False, False, Action.REMOVE, None),
    ],
)
def test_truth_table(
    current: str | None,
    user_data: bool,
    in_use: bool,
    action: Action,
    reason: str | None,
) -> None:
    """Each combination of facts yields the documented verdict."""
    decision = decide_removal(
        _record(), current, has_user_data=user_data, still_in_use=in_use
    )
    assert (decision.action, decision.reason) == (action, reason)


@pytest.mark.parametrize("outcome", [Outcome.REMOVED, Outcome.KEPT])
def test_a_settled_record_is_never_decided_again(outcome: Outcome) -> None:
    """Only owned records can be decided."""
    with pytest.raises(InvalidInstallationStateError):
        decide_removal(_record(outcome), "h1", has_user_data=False, still_in_use=False)
