"""Progress reporting for long operations: backups, restores and scheduled jobs.

A use case describes its work as a plan of weighted phases and reports against it
through a `ProgressReporter`. Where the report goes (a terminal, a file, a table
row) is a `ProgressSink`'s concern, so a use case never knows who is watching.
Progress is ephemeral and best effort: a sink that fails must never fail or slow
the operation it reports on.
"""

from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Literal, Protocol, get_args

from app.shared_kernel.errors import DomainError, ValidationError

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

type PhaseStatus = Literal["waiting", "running", "done"]
type Outcome = Literal["running", "succeeded", "failed"]
type Unit = Literal["count", "bytes"]

# Throttle between routine flushes; phase changes and the end always flush.
DEFAULT_FLUSH_INTERVAL = timedelta(seconds=1)

_PERCENT_SCALE = 10_000
_PHASE_STATES = get_args(PhaseStatus.__value__)
_OUTCOMES = get_args(Outcome.__value__)
_UNITS = get_args(Unit.__value__)


def _one_of[T](value: object, allowed: tuple[T, ...]) -> T:
    """Return the member of `allowed` equal to `value`, else raise `ValueError`."""
    for option in allowed:
        if value == option:
            return option
    raise ValueError(f"Unexpected progress value {value!r}")


@dataclass(frozen=True, kw_only=True)
class Phase:
    """One planned stage of an operation.

    Attributes:
        key: Stable identifier a reporter starts the phase by.
        label: Collector-facing wording, shown in the interface.
        weight: Share of the whole operation, relative to the other phases.
        unit: What `done` and `total` count. A viewer shows "1,240 of 2,000" for
            `count` and only a percentage for `bytes`.
    """

    key: str
    label: str
    weight: int = 1
    unit: Unit = "count"

    def __post_init__(self) -> None:
        """Reject phases a reporter could not address or weigh."""
        if not self.key.strip():
            raise ValidationError("A progress phase needs a key")
        if self.weight < 1:
            raise ValidationError("A progress phase weight must be at least 1")


@dataclass(frozen=True, kw_only=True)
class PhaseState:
    """A phase together with how far it has got."""

    key: str
    label: str
    state: PhaseStatus
    done: int
    total: int | None
    unit: Unit = "count"


@dataclass(frozen=True, kw_only=True)
class ProgressSnapshot:
    """Everything a viewer needs to draw the operation's progress."""

    phases: tuple[PhaseState, ...]
    message: str | None
    percent: int
    outcome: Outcome

    def to_dict(self) -> dict[str, object]:
        """Plain data for JSON storage: lists and scalars, as read back."""
        payload = asdict(self)
        payload["phases"] = list(payload["phases"])
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ProgressSnapshot:
        """Rebuild a snapshot from `to_dict` output.

        `payload` comes from stored JSON, hence `Any`; anything that is not a
        snapshot this code wrote raises `ValueError`, `KeyError` or `TypeError`.
        """
        phases = tuple(
            PhaseState(
                key=phase["key"],
                label=phase["label"],
                state=_one_of(phase["state"], _PHASE_STATES),
                done=phase["done"],
                total=phase["total"],
                unit=_one_of(phase["unit"], _UNITS),
            )
            for phase in payload["phases"]
        )
        return cls(
            phases=phases,
            message=payload["message"],
            percent=payload["percent"],
            outcome=_one_of(payload["outcome"], _OUTCOMES),
        )


class ProgressReporter(Protocol):
    """What a use case calls to say how far it has got."""

    async def begin(self, plan: Sequence[Phase]) -> None:
        """Declare the phases of the operation, all waiting."""
        ...

    async def start(self, key: str, total: int | None = None) -> None:
        """Move to a phase, finishing the previous one; `total` is its unit count."""
        ...

    async def advance(self, n: int = 1) -> None:
        """Record `n` more units of the running phase."""
        ...

    async def message(self, text: str) -> None:
        """Say what is happening now, in collector-facing wording."""
        ...

    async def done(self) -> None:
        """End the whole operation as succeeded."""
        ...

    async def fail(self, reason: str) -> None:
        """End the whole operation as failed, keeping where it stopped."""
        ...


class ProgressSink(Protocol):
    """Where snapshots go. Implementations may raise; the reporter swallows it."""

    async def write(self, snapshot: ProgressSnapshot) -> None:
        """Store or show the latest snapshot."""
        ...


class CompositeProgressSink:
    """Writes each snapshot to several sinks, so one failing never starves another.

    A sink's error goes to `on_error` (the shared kernel carries no logging) and
    the remaining sinks still receive the write.
    """

    def __init__(
        self, *sinks: ProgressSink, on_error: Callable[[Exception], None] | None = None
    ) -> None:
        self._sinks = sinks
        self._on_error = on_error

    async def write(self, snapshot: ProgressSnapshot) -> None:
        """Write to every sink in turn, reporting any that fail."""
        for sink in self._sinks:
            try:
                await sink.write(snapshot)
            except Exception as error:
                if self._on_error is not None:
                    self._on_error(error)


GENERIC_FAILURE = "The operation failed unexpectedly."


def failure_reason(error: Exception) -> str:
    """Wording for a failed snapshot: curated domain messages only.

    A domain error's message is written for people; anything else may carry paths
    or internals, so it is replaced.
    """
    return str(error) if isinstance(error, DomainError) else GENERIC_FAILURE


class NullProgress:
    """Reports nothing, so existing callers and tests need no reporter."""

    async def begin(self, plan: Sequence[Phase]) -> None:
        """Ignore the plan."""

    async def start(self, key: str, total: int | None = None) -> None:
        """Ignore the phase change."""

    async def advance(self, n: int = 1) -> None:
        """Ignore the progress."""

    async def message(self, text: str) -> None:
        """Ignore the message."""

    async def done(self) -> None:
        """Ignore completion."""

    async def fail(self, reason: str) -> None:
        """Ignore failure."""


NULL_PROGRESS = NullProgress()


@dataclass(kw_only=True, eq=False)
class RecordingProgress:
    """Keeps every call as a tuple, for tests to assert on.

    Each entry is the method name followed by its arguments, for example
    `("start", "media", 12)` or `("advance", 3)`.
    """

    calls: list[tuple[object, ...]] = field(default_factory=list)

    async def begin(self, plan: Sequence[Phase]) -> None:
        """Record the plan."""
        self.calls.append(("begin", tuple(plan)))

    async def start(self, key: str, total: int | None = None) -> None:
        """Record the phase change."""
        self.calls.append(("start", key, total))

    async def advance(self, n: int = 1) -> None:
        """Record the progress."""
        self.calls.append(("advance", n))

    async def message(self, text: str) -> None:
        """Record the message."""
        self.calls.append(("message", text))

    async def done(self) -> None:
        """Record completion."""
        self.calls.append(("done",))

    async def fail(self, reason: str) -> None:
        """Record failure."""
        self.calls.append(("fail", reason))


class SnapshotReporter:
    """Turns reporter calls into snapshots and hands them to a sink.

    It holds the state, derives the overall percentage, and flushes at most once
    per `interval` seconds, except on a phase change and at the end. A sink error
    is passed to `on_error` and otherwise swallowed; the hook is injected because the
    shared kernel carries no logging. If the wall clock steps backwards, the next
    routine update is simply due.

    Misuse (an unknown phase, advancing before any phase starts) raises
    `RuntimeError`: it is a bug in the caller, not a runtime condition.
    """

    def __init__(
        self,
        sink: ProgressSink,
        *,
        interval: timedelta = DEFAULT_FLUSH_INTERVAL,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        """Create a reporter writing to `sink`."""
        self._sink = sink
        self._interval = interval
        self._on_error = on_error
        self._phases: list[PhaseState] = []
        self._weights: list[int] = []
        self._current: int | None = None
        self._message: str | None = None
        self._outcome: Outcome = "running"
        self._last_flush: datetime | None = None

    async def begin(self, plan: Sequence[Phase]) -> None:
        """Declare the phases; all start waiting."""
        keys = [phase.key for phase in plan]
        if not keys or len(set(keys)) != len(keys):
            raise ValidationError("A progress plan needs distinct, non-empty phases")
        self._phases = [
            PhaseState(
                key=p.key,
                label=p.label,
                state="waiting",
                done=0,
                total=None,
                unit=p.unit,
            )
            for p in plan
        ]
        self._weights = [phase.weight for phase in plan]
        self._current = None
        self._message = None
        self._outcome = "running"
        await self._flush(force=True)

    async def start(self, key: str, total: int | None = None) -> None:
        """Finish the running phase, if any, and begin `key`."""
        if self._ended():
            return
        index = self._index(key)
        self._finish_current()
        phase = self._phases[index]
        self._phases[index] = replace(phase, state="running", done=0, total=total)
        self._current = index
        await self._flush(force=True)

    async def advance(self, n: int = 1) -> None:
        """Add `n` units to the running phase, never beyond its known total."""
        if self._ended():
            return
        phase = self._running()
        done = phase.done + n
        if phase.total is not None:
            done = min(done, phase.total)
        self._replace(phase, done=done)
        await self._flush(force=False)

    async def message(self, text: str) -> None:
        """Set the line describing what is happening now."""
        if self._ended():
            return
        self._message = text
        await self._flush(force=False)

    async def done(self) -> None:
        """Finish every phase and mark the operation succeeded."""
        if self._ended():
            return
        self._complete_all()
        self._message = None
        self._outcome = "succeeded"
        await self._flush(force=True)

    async def fail(self, reason: str) -> None:
        """Mark the operation failed where it stands, with `reason` as the message."""
        if self._ended():
            return
        self._message = reason
        self._outcome = "failed"
        await self._flush(force=True)

    def snapshot(self) -> ProgressSnapshot:
        """The current state, with the weighted overall percentage."""
        return ProgressSnapshot(
            phases=tuple(self._phases),
            message=self._message,
            percent=self._percent(),
            outcome=self._outcome,
        )

    def _percent(self) -> int:
        weight_total = sum(self._weights)
        if not weight_total:
            return 0
        earned = sum(
            weight * self._basis_points(phase)
            for weight, phase in zip(self._weights, self._phases, strict=True)
        )
        return earned // weight_total // (_PERCENT_SCALE // 100)

    @staticmethod
    def _basis_points(phase: PhaseState) -> int:
        """A phase's completion in 1/10,000ths; an unknown total counts as 0."""
        if phase.state == "done":
            return _PERCENT_SCALE
        if phase.state == "waiting" or phase.total is None:
            return 0
        if phase.total == 0:
            return _PERCENT_SCALE
        return min(phase.done, phase.total) * _PERCENT_SCALE // phase.total

    def _ended(self) -> bool:
        return self._outcome != "running"

    def _index(self, key: str) -> int:
        for index, phase in enumerate(self._phases):
            if phase.key == key:
                return index
        raise RuntimeError(f"Unknown progress phase {key!r}; call begin() first")

    def _running(self) -> PhaseState:
        if self._current is None:
            raise RuntimeError("No progress phase is running; call start() first")
        return self._phases[self._current]

    def _replace(
        self, phase: PhaseState, *, done: int, state: PhaseStatus | None = None
    ) -> None:
        index = self._phases.index(phase)
        self._phases[index] = replace(phase, state=state or phase.state, done=done)

    def _finish_current(self) -> None:
        if self._current is None:
            return
        phase = self._phases[self._current]
        done = phase.done if phase.total is None else phase.total
        self._replace(phase, done=done, state="done")

    def _complete_all(self) -> None:
        for index, phase in enumerate(self._phases):
            if phase.state == "done":
                continue
            done = phase.done if phase.total is None else phase.total
            self._phases[index] = replace(phase, state="done", done=done)

    async def _flush(self, *, force: bool) -> None:
        now = datetime.now(UTC)
        if (
            not force
            and self._last_flush is not None
            and timedelta() <= now - self._last_flush < self._interval
        ):
            return
        self._last_flush = now
        try:
            await self._sink.write(self.snapshot())
        except Exception as error:
            if self._on_error is not None:
                self._on_error(error)
