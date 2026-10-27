"""Inbound handler bindings alongside the metadata-only job registry."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.modules.scheduling.adapters.cli.execution import JobHandler
from app.modules.scheduling.domain.registry import JobRegistry
from app.shared_kernel.jobs import JobDefinition

if TYPE_CHECKING:
    from collections.abc import Iterable


@dataclass(frozen=True, kw_only=True)
class JobBinding:
    """A module-contributed handler and its portable scheduling policy."""

    definition: JobDefinition
    handler: JobHandler


class JobCatalogue:
    """Keep handler resolution on the inbound side of the scheduling ports."""

    def __init__(self, bindings: Iterable[JobBinding]) -> None:
        bindings = tuple(bindings)
        self.registry = JobRegistry(binding.definition for binding in bindings)
        self._handlers = {
            binding.definition.job_key: binding.handler for binding in bindings
        }

    def handler_for(self, job_key: str) -> JobHandler:
        """Resolve a handler using the registry's shared missing-job error."""
        self.registry.get(job_key)
        return self._handlers[job_key]
