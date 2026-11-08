"""Progress types, the null and recording reporters, and `SnapshotReporter`."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
import time_machine

from app.shared_kernel.errors import NotFoundError, ValidationError
from app.shared_kernel.progress import (
    GENERIC_FAILURE,
    NULL_PROGRESS,
    CompositeProgressSink,
    NullProgress,
    Phase,
    PhaseState,
    ProgressSnapshot,
    RecordingProgress,
    SnapshotReporter,
    failure_reason,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

PLAN = (
    Phase(key="verify", label="Checking the backup", weight=2),
    Phase(key="database", label="Restoring your collection", weight=3),
    Phase(key="media", label="Restoring photos and files", weight=5),
)


class ListSink:
    """Collects every snapshot written to it."""

    def __init__(self) -> None:
        self.written: list[ProgressSnapshot] = []

    async def write(self, snapshot: ProgressSnapshot) -> None:
        """Write."""
        self.written.append(snapshot)


class BrokenSink:
    """A sink whose every write fails."""

    async def write(self, snapshot: ProgressSnapshot) -> None:
        """Write."""
        raise OSError("disk full")


NOW = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def frozen_clock() -> Iterator[time_machine.Traveller]:
    """Freeze time so flush throttling depends only on explicit shifts."""
    with time_machine.travel(NOW, tick=False) as clock:
        yield clock


def make(sink: ListSink | None = None) -> tuple[SnapshotReporter, ListSink]:
    """A reporter on the frozen wall clock, writing to `sink`."""
    sink = sink or ListSink()
    return SnapshotReporter(sink), sink


# --- Phase -----------------------------------------------------------------


def test_a_phase_needs_a_key() -> None:
    """A phase needs a key."""
    with pytest.raises(ValidationError):
        Phase(key=" ", label="Nothing")


def test_a_phase_weight_must_be_positive() -> None:
    """A phase weight must be positive."""
    with pytest.raises(ValidationError):
        Phase(key="a", label="A", weight=0)


# --- NullProgress and RecordingProgress ------------------------------------


async def test_null_progress_accepts_every_call() -> None:
    """Null progress accepts every call."""
    null = NullProgress()
    await null.begin(PLAN)
    await null.start("verify", 3)
    await null.advance()
    await null.message("hello")
    await null.done()
    await null.fail("nope")
    assert NULL_PROGRESS is not None


async def test_recording_progress_keeps_each_call_in_order() -> None:
    """Recording progress keeps each call in order."""
    recording = RecordingProgress()
    await recording.begin(PLAN)
    await recording.start("verify", 10)
    await recording.advance(4)
    await recording.advance()
    await recording.message("Checking")
    await recording.done()
    await recording.fail("boom")
    assert recording.calls == [
        ("begin", PLAN),
        ("start", "verify", 10),
        ("advance", 4),
        ("advance", 1),
        ("message", "Checking"),
        ("done",),
        ("fail", "boom"),
    ]


# --- SnapshotReporter: plan and phases --------------------------------------


async def test_begin_writes_every_phase_waiting_at_zero_percent() -> None:
    """Begin writes every phase waiting at zero percent."""
    reporter, sink = make()
    await reporter.begin(PLAN)
    [snapshot] = sink.written
    assert [p.state for p in snapshot.phases] == ["waiting"] * 3
    assert snapshot.percent == 0
    assert snapshot.outcome == "running"
    assert snapshot.message is None


@pytest.mark.parametrize(
    "plan",
    [(), (Phase(key="a", label="A"), Phase(key="a", label="Again"))],
)
async def test_begin_rejects_an_empty_or_duplicated_plan(
    plan: tuple[Phase, ...],
) -> None:
    """Begin rejects an empty or duplicated plan."""
    reporter, _ = make()
    with pytest.raises(ValidationError):
        await reporter.begin(plan)


async def test_start_runs_a_phase_and_finishes_the_previous_one() -> None:
    """Start runs a phase and finishes the previous one."""
    reporter, sink = make()
    await reporter.begin(PLAN)
    await reporter.start("verify", 10)
    await reporter.advance(4)
    await reporter.start("database", 100)
    snapshot = sink.written[-1]
    verify, database, media = snapshot.phases
    assert (verify.state, verify.done, verify.total) == ("done", 10, 10)
    assert (database.state, database.done, database.total) == ("running", 0, 100)
    assert media.state == "waiting"


async def test_start_keeps_the_count_of_a_finished_phase_with_unknown_total() -> None:
    """Start keeps the count of a finished phase with unknown total."""
    reporter, sink = make()
    await reporter.begin(PLAN)
    await reporter.start("verify")
    await reporter.advance(7)
    await reporter.start("database")
    assert sink.written[-1].phases[0].done == 7
    assert sink.written[-1].phases[0].state == "done"


async def test_start_rejects_an_unknown_phase() -> None:
    """Start rejects an unknown phase."""
    reporter, _ = make()
    await reporter.begin(PLAN)
    with pytest.raises(RuntimeError, match="Unknown progress phase"):
        await reporter.start("nope")


async def test_advance_before_any_phase_is_a_bug() -> None:
    """Advance before any phase is a bug."""
    reporter, _ = make()
    await reporter.begin(PLAN)
    with pytest.raises(RuntimeError, match="No progress phase is running"):
        await reporter.advance()


async def test_advance_never_passes_a_known_total() -> None:
    """Advance never passes a known total."""
    reporter, _ = make()
    await reporter.begin(PLAN)
    await reporter.start("verify", 5)
    await reporter.advance(99)
    assert reporter.snapshot().phases[0].done == 5


# --- SnapshotReporter: percent ----------------------------------------------


async def test_percent_is_weighted_across_phases() -> None:
    """Percent is weighted across phases."""
    reporter, _ = make()
    await reporter.begin(PLAN)
    await reporter.start("verify", 10)
    await reporter.advance(10)
    assert reporter.snapshot().percent == 20  # 2 of 10
    await reporter.start("database", 4)
    await reporter.advance(2)
    assert reporter.snapshot().percent == 35  # 2 + 1.5 of 10
    await reporter.start("media", 4)
    await reporter.advance(1)
    assert reporter.snapshot().percent == 62  # 5 + 1.25 of 10, floored


async def test_percent_counts_an_unknown_total_as_nothing() -> None:
    """Percent counts an unknown total as nothing."""
    reporter, _ = make()
    await reporter.begin(PLAN)
    await reporter.start("verify")
    await reporter.advance(50)
    assert reporter.snapshot().percent == 0


async def test_percent_counts_an_empty_phase_as_complete() -> None:
    """Percent counts an empty phase as complete."""
    reporter, _ = make()
    await reporter.begin(PLAN)
    await reporter.start("verify", 0)
    assert reporter.snapshot().percent == 20


async def test_percent_is_zero_before_a_plan_exists() -> None:
    """Percent is zero before a plan exists."""
    reporter, _ = make()
    assert reporter.snapshot().percent == 0
    assert reporter.snapshot().phases == ()


# --- SnapshotReporter: flushing ----------------------------------------------


async def test_routine_updates_flush_at_most_once_per_interval(
    frozen_clock: time_machine.Traveller,
) -> None:
    """Routine updates flush at most once per interval."""
    reporter, sink = make()
    await reporter.begin(PLAN)
    await reporter.start("verify", 100)
    written = len(sink.written)  # the phase change flushed at t=0
    await reporter.advance(1)
    frozen_clock.shift(0.5)
    await reporter.advance(1)
    await reporter.message("Still checking")
    assert len(sink.written) == written
    frozen_clock.shift(0.5)
    await reporter.advance(1)
    assert len(sink.written) == written + 1
    assert sink.written[-1].phases[0].done == 3
    assert sink.written[-1].message == "Still checking"


async def test_a_clock_stepping_backwards_does_not_stall_updates(
    frozen_clock: time_machine.Traveller,
) -> None:
    """A routine update is due again if the wall clock jumps back."""
    reporter, sink = make()
    await reporter.begin(PLAN)
    await reporter.start("verify", 100)
    written = len(sink.written)
    frozen_clock.shift(-3600)
    await reporter.advance(1)
    assert len(sink.written) == written + 1


async def test_a_phase_change_always_flushes() -> None:
    """A phase change always flushes."""
    reporter, sink = make()
    await reporter.begin(PLAN)
    await reporter.start("verify", 1)
    await reporter.start("database", 1)
    assert len(sink.written) == 3


async def test_done_finishes_every_phase_and_always_flushes() -> None:
    """Done finishes every phase and always flushes."""
    reporter, sink = make()
    await reporter.begin(PLAN)
    await reporter.start("verify", 10)
    await reporter.message("Almost")
    await reporter.done()
    snapshot = sink.written[-1]
    assert snapshot.outcome == "succeeded"
    assert snapshot.percent == 100
    assert snapshot.message is None
    assert {p.state for p in snapshot.phases} == {"done"}
    assert snapshot.phases[0].done == 10


async def test_done_leaves_an_already_finished_phase_alone() -> None:
    """Done leaves an already finished phase alone."""
    reporter, sink = make()
    await reporter.begin(PLAN)
    await reporter.start("verify", 10)
    await reporter.start("database", 10)
    await reporter.done()
    assert [p.done for p in sink.written[-1].phases] == [10, 10, 0]
    assert {p.state for p in sink.written[-1].phases} == {"done"}


async def test_done_keeps_the_count_of_a_phase_with_unknown_total() -> None:
    """Done keeps the count of a phase with unknown total."""
    reporter, sink = make()
    await reporter.begin(PLAN)
    await reporter.start("verify")
    await reporter.advance(3)
    await reporter.done()
    assert sink.written[-1].phases[0].done == 3


async def test_fail_keeps_where_it_stopped_and_always_flushes() -> None:
    """Fail keeps where it stopped and always flushes."""
    reporter, sink = make()
    await reporter.begin(PLAN)
    await reporter.start("verify", 10)
    await reporter.advance(10)
    await reporter.start("database", 100)
    await reporter.advance(40)
    await reporter.fail("The archive is damaged")
    snapshot = sink.written[-1]
    assert snapshot.outcome == "failed"
    assert snapshot.message == "The archive is damaged"
    assert snapshot.phases[1].state == "running"
    assert snapshot.phases[1].done == 40
    assert snapshot.percent == 32  # 2 + 1.2 of 10


async def test_nothing_changes_once_the_operation_has_ended() -> None:
    """Nothing changes once the operation has ended."""
    reporter, sink = make()
    await reporter.begin(PLAN)
    await reporter.start("verify", 1)
    await reporter.fail("boom")
    written = len(sink.written)
    await reporter.start("database", 1)
    await reporter.advance()
    await reporter.message("later")
    await reporter.done()
    await reporter.fail("again")
    assert len(sink.written) == written
    assert reporter.snapshot().message == "boom"
    assert reporter.snapshot().outcome == "failed"


async def test_begin_restarts_a_finished_reporter() -> None:
    """Begin restarts a finished reporter."""
    reporter, sink = make()
    await reporter.begin(PLAN)
    await reporter.done()
    await reporter.begin(PLAN)
    assert sink.written[-1].outcome == "running"
    assert sink.written[-1].percent == 0


# --- SnapshotReporter: sink failures -----------------------------------------


async def test_a_failing_sink_never_fails_the_operation() -> None:
    """A failing sink never fails the operation."""
    reporter = SnapshotReporter(BrokenSink())
    await reporter.begin(PLAN)
    await reporter.start("verify", 2)
    await reporter.advance()
    await reporter.done()
    assert reporter.snapshot().outcome == "succeeded"


async def test_a_sink_error_is_passed_to_the_error_hook() -> None:
    """A sink error is passed to the error hook."""
    errors: list[Exception] = []
    reporter = SnapshotReporter(BrokenSink(), on_error=errors.append)
    await reporter.begin(PLAN)
    assert [str(e) for e in errors] == ["disk full"]


# --- units and failure wording ------------------------------------------------


async def test_a_phase_unit_reaches_every_snapshot() -> None:
    """A phase's unit survives starting, advancing and finishing."""
    reporter, sink = make()
    await reporter.begin(
        (Phase(key="a", label="A", unit="bytes"), Phase(key="b", label="B"))
    )
    await reporter.start("a", 10)
    await reporter.advance(4)
    await reporter.start("b", 2)
    await reporter.done()
    assert [p.unit for p in sink.written[0].phases] == ["bytes", "count"]
    assert [p.unit for p in sink.written[-1].phases] == ["bytes", "count"]


def test_a_domain_error_message_is_shown_as_written() -> None:
    """Domain errors are written for people."""
    assert failure_reason(NotFoundError("Backup not found")) == "Backup not found"


def test_any_other_error_is_replaced_by_a_generic_message() -> None:
    """Paths and internals in other exceptions never reach a viewer."""
    assert failure_reason(OSError("/data/backups/x: denied")) == GENERIC_FAILURE


# --- snapshot codec --------------------------------------------------------------


def test_a_snapshot_round_trips_through_plain_data() -> None:
    """`to_dict` output is JSON-safe and rebuilds the same snapshot."""
    snapshot = ProgressSnapshot(
        phases=(
            PhaseState(
                key="a", label="A", state="running", done=2, total=5, unit="bytes"
            ),
            PhaseState(key="b", label="B", state="waiting", done=0, total=None),
        ),
        message="Hold on",
        percent=12,
        outcome="running",
    )
    payload = snapshot.to_dict()
    assert isinstance(payload["phases"], list)
    assert ProgressSnapshot.from_dict(payload) == snapshot


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"phases": [], "message": None, "percent": 0},
        {"phases": [{"key": "a"}], "message": None, "percent": 0, "outcome": "running"},
        {"phases": [], "message": None, "percent": 0, "outcome": "unknown"},
        {
            "phases": [
                {
                    "key": "a",
                    "label": "A",
                    "state": "paused",
                    "done": 0,
                    "total": None,
                    "unit": "count",
                }
            ],
            "message": None,
            "percent": 0,
            "outcome": "running",
        },
        {
            "phases": [
                {
                    "key": "a",
                    "label": "A",
                    "state": "done",
                    "done": 0,
                    "total": None,
                    "unit": "furlongs",
                }
            ],
            "message": None,
            "percent": 0,
            "outcome": "running",
        },
    ],
)
def test_anything_that_is_not_a_snapshot_is_refused(payload: dict[str, object]) -> None:
    """Stored data that this code did not write never becomes a snapshot."""
    with pytest.raises((ValueError, KeyError, TypeError)):
        ProgressSnapshot.from_dict(payload)


# --- CompositeProgressSink -----------------------------------------------------


async def test_the_composite_writes_to_every_sink() -> None:
    """Fan-out hands the same snapshot to each sink."""
    first, second = ListSink(), ListSink()
    reporter = SnapshotReporter(CompositeProgressSink(first, second))
    await reporter.begin(PLAN)
    assert len(first.written) == len(second.written) == 1
    assert first.written[0] is second.written[0]


async def test_a_failing_sink_does_not_starve_the_others() -> None:
    """The error is reported and the later sinks still get the write."""
    errors: list[Exception] = []
    healthy = ListSink()
    composite = CompositeProgressSink(BrokenSink(), healthy, on_error=errors.append)
    await SnapshotReporter(composite).begin(PLAN)
    assert len(healthy.written) == 1
    assert [str(e) for e in errors] == ["disk full"]


async def test_the_composite_swallows_errors_without_a_hook() -> None:
    """With no hook a failing sink is simply skipped."""
    healthy = ListSink()
    await SnapshotReporter(CompositeProgressSink(BrokenSink(), healthy)).begin(PLAN)
    assert len(healthy.written) == 1
