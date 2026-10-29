"""Portable job metadata contributed by each owning module."""

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from enum import StrEnum

from app.shared_kernel.actor import Actor
from app.shared_kernel.errors import ValidationError


class Lane(StrEnum):
    """Independent worker capacity for ordinary and resource-heavy jobs."""

    DEFAULT = "default"
    HEAVY = "heavy"


class Overlap(StrEnum):
    """How enqueueing handles already queued or running work."""

    SKIP = "skip"
    COALESCE = "coalesce"
    QUEUE = "queue"


class MissedRun(StrEnum):
    """Whether to catch up the latest missed occurrence."""

    SKIP = "skip"
    RUN_ONCE = "run_once"


@dataclass(frozen=True, slots=True, kw_only=True, eq=False)
class JobDefinition:
    """Job policy without a handler, registry or engine dependency."""

    job_key: str
    lane: Lane = Lane.DEFAULT
    overlap: Overlap = Overlap.COALESCE
    missed_run: MissedRun = MissedRun.SKIP
    max_lateness: timedelta = timedelta(minutes=10)
    schedule_key: str | None = None
    run_now_allowed: bool = True
    needs_setup_complete: bool = True
    # Plain-language copy for administrators; the job key is for developers.
    title: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        """Reject unusable keys and catch-up windows."""
        if not self.job_key.strip():
            raise ValidationError("A job key is required")
        if self.max_lateness < timedelta():
            raise ValidationError("Maximum lateness cannot be negative")


type JobHandler = Callable[[Actor], Awaitable[None]]


@dataclass(frozen=True, kw_only=True)
class JobBinding:
    """A module-contributed handler and its portable scheduling policy."""

    definition: JobDefinition
    handler: JobHandler


_DEFINITION_ATTRIBUTE = "__job_definition__"


def job(definition: JobDefinition) -> Callable[[JobHandler], JobHandler]:
    """Attach a job's policy to its handler without registering it anywhere."""

    def attach(handler: JobHandler) -> JobHandler:
        setattr(handler, _DEFINITION_ATTRIBUTE, definition)
        return handler

    return attach


def _binding_for(handler: JobHandler) -> JobBinding:
    definition = getattr(handler, _DEFINITION_ATTRIBUTE, None)
    if not isinstance(definition, JobDefinition):
        name = getattr(handler, "__name__", repr(handler))
        raise ValidationError(f"{name} is not decorated with @job")
    return JobBinding(definition=definition, handler=handler)


@dataclass(frozen=True, kw_only=True)
class JobContribution:
    """What one module adds to the job catalogue and the schedule source.

    Callables defer reading deployment settings until the catalogue is built.
    """

    bindings: Callable[[], list[JobBinding]]
    schedules: Callable[[], Mapping[str, str]] = field(default=dict)

    @classmethod
    def from_handlers(
        cls,
        *handlers: JobHandler,
        schedules: Callable[[], Mapping[str, str]] = dict,
    ) -> JobContribution:
        """Contribute `@job`-decorated handlers; each carries its own definition."""
        return cls(
            bindings=lambda: [_binding_for(handler) for handler in handlers],
            schedules=schedules,
        )
