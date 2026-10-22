import uuid
from typing import ClassVar

import pytest

from app.shared_kernel.access import Access, Content, Public, Requires, Shared
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import Actor
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.errors import ForbiddenError
from app.shared_kernel.guarded import (
    GuardedCommandHandler,
    GuardedQueryHandler,
    GuardedUseCase,
)

ALICE = Actor(id=uuid.uuid4(), roles=frozenset({"member"}))


class _Permission:
    value = "demo.read"


class _Probe(GuardedUseCase[str, str]):
    """Concrete use case that records whether `_handle` ran."""

    access: ClassVar[Access] = Public()

    def __init__(self, guard: InMemoryAccessGuard) -> None:
        self._guard = guard
        self.ran = False

    async def _handle(self, request: str, actor: Actor) -> str:
        self.ran = True
        return request.upper()


def _probe_with(access: Access) -> GuardedUseCase[str, str]:
    probe_type: type[_Probe] = type("_Declared", (_Probe,), {"access": access})
    return probe_type(InMemoryAccessGuard())


async def test_handle_checks_access_before_running() -> None:
    """The guard sees the declared stance, then `_handle` runs."""
    guard = InMemoryAccessGuard()
    probe = _Probe(guard)
    assert await probe.handle("hi", ALICE) == "HI"
    assert guard.checked == [(ALICE, Public())]
    assert probe.ran


async def test_a_denying_guard_stops_the_use_case() -> None:
    """A refused check means `_handle` never runs."""
    probe = _Probe(InMemoryAccessGuard(deny=True))
    with pytest.raises(ForbiddenError):
        await probe.handle("hi", ALICE)
    assert not probe.ran


def test_command_handler_stores_uow_and_guard() -> None:
    """The command base keeps both collaborators."""

    class Command(GuardedCommandHandler[object, str, str]):
        access: ClassVar[Access] = Shared()

        async def _handle(self, request: str, actor: Actor) -> str:
            return request

    uow, guard = object(), InMemoryAccessGuard()
    handler = Command(uow, guard)
    assert handler._uow is uow
    assert handler._guard is guard


def test_query_handler_stores_repos_and_guard() -> None:
    """The query base keeps both collaborators."""

    class Query(GuardedQueryHandler[object, str, str]):
        access: ClassVar[Access] = Shared()

        async def _handle(self, request: str, actor: Actor) -> str:
            return request

    repos, guard = object(), InMemoryAccessGuard()
    handler = Query(repos, guard)
    assert handler._repos is repos
    assert handler._guard is guard


def test_scope_returns_the_guards_filter_for_content() -> None:
    """A `Content` use case gets its caller's content filter."""
    assert _probe_with(Content()).scope(ALICE) == ContentFilter.of(ALICE.id)


@pytest.mark.parametrize(
    "access",
    [Shared(), Public(), Requires(_Permission)],  # type: ignore[arg-type]
)
def test_scope_is_refused_outside_content(access: Access) -> None:
    """Only `Content` use cases may ask for a content filter."""
    with pytest.raises(TypeError):
        _probe_with(access).scope(ALICE)
