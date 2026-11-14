"""`record_late`: recording after the pack finished installing."""

import uuid

import pytest

from app.modules.transfer.domain.entity_kind import EntityKind
from app.modules.transfer.domain.errors import InvalidRunStateError
from app.modules.transfer.domain.run import Outcome, Run, RunStatus


def _installation(status: RunStatus) -> Run:
    installation = Run.start("music", uuid.uuid7())
    installation.status = status
    return installation


@pytest.mark.parametrize("status", [RunStatus.INSTALLING, RunStatus.INSTALLED])
def test_record_late_works_while_installing_or_installed(
    status: RunStatus,
) -> None:
    """Links are recorded once the pack is installed."""
    installation = _installation(status)

    installation.record_late(
        EntityKind.CONNECTION, "link:movies:0", "A to B", uuid.uuid7(), "h"
    )

    [record] = installation.owned(EntityKind.CONNECTION)
    assert record.ref == "link:movies:0"


@pytest.mark.parametrize("status", [RunStatus.REMOVED, RunStatus.FAILED])
def test_record_late_is_refused_once_finished_with(status: RunStatus) -> None:
    """A removed or failed installation takes no more records."""
    installation = _installation(status)

    with pytest.raises(InvalidRunStateError):
        installation.record_late(
            EntityKind.CONNECTION, "link:movies:0", "A to B", uuid.uuid7(), "h"
        )


def test_record_still_needs_installing() -> None:
    """The ordinary method is unchanged."""
    installation = _installation(RunStatus.INSTALLED)

    with pytest.raises(InvalidRunStateError):
        installation.record(EntityKind.ITEM, "a", "A", uuid.uuid7(), "h")


def test_record_late_replaces_an_older_settled_record_of_the_same_ref() -> None:
    """A link made again after it was removed leaves one record, not two."""
    installation = _installation(RunStatus.INSTALLED)
    first = uuid.uuid7()
    installation.record_late(
        EntityKind.CONNECTION, "link:movies:0", "A to B", first, "h"
    )
    installation.settle(first, Outcome.REMOVED)

    installation.record_late(
        EntityKind.CONNECTION, "link:movies:0", "A to B", uuid.uuid7(), "h"
    )

    [record] = installation.entities
    assert record.outcome is Outcome.OWNED
    assert record.entity_id != first
