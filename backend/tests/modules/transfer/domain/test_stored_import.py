"""An uploaded import file and the steps of its life."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.modules.transfer.domain.errors import InvalidImportStateError
from app.modules.transfer.domain.item_import import (
    MAX_FILENAME_LENGTH,
    ImportOptions,
    ImportOutcome,
    ImportStatus,
    ItemImport,
    turn_order,
)
from app.shared_kernel.progress import ProgressSnapshot

OWNER = uuid.UUID(int=0xA1)
BOB = uuid.UUID(int=0xB2)
CAROL = uuid.UUID(int=0xC3)
NOW = datetime(2026, 11, 24, 12, tzinfo=UTC)
OPTIONS = ImportOptions(item_type="autograph")
SNAPSHOT = ProgressSnapshot(phases=(), message=None, percent=40, outcome="running")


def _uploaded(filename: str = "signed.csv") -> ItemImport:
    return ItemImport.upload(
        owner_id=OWNER,
        filename=filename,
        size=1204,
        now=NOW,
        keep_for=timedelta(hours=24),
    )


def _running() -> ItemImport:
    item = _uploaded()
    item.queue(OPTIONS, None, NOW)
    item.start(NOW)
    return item


def test_an_upload_waits_for_options_until_it_expires() -> None:
    """A new file is the owner's, uploaded, and kept for the given time."""
    item = _uploaded()
    assert item.owner_id == OWNER
    assert item.status is ImportStatus.UPLOADED
    assert item.expires_at == NOW + timedelta(hours=24)
    assert (item.created_at, item.updated_at) == (NOW, NOW)
    assert not item.is_finished


@pytest.mark.parametrize(
    ("given", "kept"),
    [
        ("  signed.csv ", "signed.csv"),
        ("   ", "import.csv"),
        ("a" * 300, "a" * MAX_FILENAME_LENGTH),
    ],
)
def test_the_filename_is_tidied(given: str, kept: str) -> None:
    """Spacing goes, a blank name gets one, and a long one is cut."""
    assert _uploaded(given).filename == kept


def test_queueing_keeps_the_options_and_the_token_ceiling() -> None:
    """The worker later runs it with exactly these options and grants."""
    item = _uploaded()
    later = NOW + timedelta(minutes=2)
    item.queue(OPTIONS, frozenset({"transfer:bundle:import"}), later)
    assert item.status is ImportStatus.QUEUED
    assert item.options == OPTIONS
    assert item.grants == frozenset({"transfer:bundle:import"})
    assert item.queued_at == later


def test_a_queued_import_cannot_be_queued_again() -> None:
    """Running the same file twice would add its rows twice."""
    item = _uploaded()
    item.queue(OPTIONS, None, NOW)
    with pytest.raises(InvalidImportStateError, match="queued"):
        item.queue(OPTIONS, None, NOW)


def test_a_run_reports_progress_and_succeeds() -> None:
    """Progress is kept while running, then the outcome once finished."""
    item = _running()
    item.report(SNAPSHOT, NOW)
    item.succeed(ImportOutcome(items_added=3, connections_added=1), NOW)
    assert item.status is ImportStatus.SUCCEEDED
    assert item.progress == SNAPSHOT
    assert item.outcome == ImportOutcome(items_added=3, connections_added=1)
    assert item.finished_at == NOW
    assert item.is_finished


def test_progress_after_the_end_is_ignored() -> None:
    """A reporter's last write may land after the import ended."""
    item = _running()
    item.fail("The worker stopped.", NOW)
    item.report(SNAPSHOT, NOW)
    assert item.progress is None
    assert item.failure == "The worker stopped."


def test_a_queued_import_can_fail_before_it_starts() -> None:
    """Its owner may be disabled by the time its turn comes."""
    item = _uploaded()
    item.queue(OPTIONS, None, NOW)
    item.fail("The account is disabled.", NOW)
    assert item.status is ImportStatus.FAILED


def test_an_upload_cannot_skip_the_queue() -> None:
    """Only a queued import starts, and only a started one ends."""
    item = _uploaded()
    with pytest.raises(InvalidImportStateError):
        item.start(NOW)
    with pytest.raises(InvalidImportStateError):
        item.succeed(ImportOutcome(items_added=0, connections_added=0), NOW)
    with pytest.raises(InvalidImportStateError):
        item.fail("no", NOW)


def _files(*owners: uuid.UUID) -> list[ItemImport]:
    files = []
    for owner in owners:
        item = _uploaded()
        item.owner_id = owner
        files.append(item)
    return files


def test_people_take_turns_and_keep_their_own_order() -> None:
    """Five files from one person do not hold back another's one."""
    a1, a2, a3, b1, a4 = _files(OWNER, OWNER, OWNER, BOB, OWNER)
    assert turn_order([a1, a2, a3, b1, a4], []) == [a1, b1, a2, a3, a4]


def test_whoever_waited_longest_since_their_turn_goes_first() -> None:
    """Someone just served waits for those who were not; never served beats all."""
    a1, b1, c1 = _files(OWNER, BOB, CAROL)
    assert turn_order([a1, b1, c1], [OWNER, BOB, OWNER]) == [c1, b1, a1]
    assert turn_order([a1, b1, c1], [BOB, OWNER]) == [c1, a1, b1]


def test_nobody_waiting_is_an_empty_order() -> None:
    """The drain stops when there is nothing left."""
    assert turn_order([], [OWNER]) == []
