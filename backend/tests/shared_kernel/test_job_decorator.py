"""`@job` attaches a job's policy to its handler; `from_handlers` reads it back."""

import pytest

from app.shared_kernel.actor import SYSTEM_ACTOR, Actor
from app.shared_kernel.errors import ValidationError
from app.shared_kernel.jobs import JobContribution, JobDefinition, job

DEFINITION = JobDefinition(job_key="demo.tidy", title="Tidy", description="Tidies.")


@job(DEFINITION)
async def tidy(actor: Actor) -> None:
    """A decorated handler."""


async def undecorated(actor: Actor) -> None:
    """A handler that forgot `@job`."""


def test_the_decorator_returns_the_same_callable() -> None:
    """Decoration registers nothing and does not wrap the handler."""
    assert tidy.__name__ == "tidy"


def test_from_handlers_binds_each_definition_to_its_handler() -> None:
    """The definition travels with the function it was written above."""
    [binding] = JobContribution.from_handlers(tidy).bindings()
    assert binding.definition is DEFINITION
    assert binding.handler is tidy


def test_from_handlers_keeps_the_schedules_it_is_given() -> None:
    """Schedules stay lazy because they depend on settings read at build time."""
    contribution = JobContribution.from_handlers(
        tidy, schedules=lambda: {"demo.schedule": "0 1 * * *"}
    )
    assert contribution.schedules() == {"demo.schedule": "0 1 * * *"}


def test_an_undecorated_handler_is_refused_clearly() -> None:
    """The mistake is named, not left to an AttributeError."""
    contribution = JobContribution.from_handlers(undecorated)
    with pytest.raises(ValidationError, match=r"undecorated.*@job"):
        contribution.bindings()


async def test_the_handler_still_runs() -> None:
    """A decorated handler is an ordinary coroutine function."""
    await tidy(SYSTEM_ACTOR)
