"""Registered job metadata, independent of handler and engine wiring."""

from typing import TYPE_CHECKING

from app.modules.scheduling.domain.errors import DuplicateJobError, UnknownJobError

if TYPE_CHECKING:
    from collections.abc import Iterable

    from app.shared_kernel.jobs import JobDefinition


class JobRegistry:
    """Resolve unique job definitions supplied by the composition root."""

    def __init__(self, definitions: Iterable[JobDefinition]) -> None:
        self._definitions: dict[str, JobDefinition] = {}
        for definition in definitions:
            if definition.job_key in self._definitions:
                raise DuplicateJobError(definition.job_key)
            self._definitions[definition.job_key] = definition

    def get(self, job_key: str) -> JobDefinition:
        """Return the registered definition or raise UnknownJobError."""
        try:
            return self._definitions[job_key]
        except KeyError as exc:
            raise UnknownJobError(job_key) from exc

    def all(self) -> tuple[JobDefinition, ...]:
        """Return definitions in registration order."""
        return tuple(self._definitions.values())

    def scheduled(self) -> tuple[JobDefinition, ...]:
        """Return only definitions with a schedule-source key."""
        return tuple(
            job for job in self._definitions.values() if job.schedule_key is not None
        )
