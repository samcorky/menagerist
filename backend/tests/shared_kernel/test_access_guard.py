import uuid

import pytest

from app.shared_kernel.access import (
    Access,
    Content,
    OwnAccount,
    Public,
    Requires,
    Shared,
    System,
)
from app.shared_kernel.access_guard import DenyAllAccessGuard, InMemoryAccessGuard
from app.shared_kernel.actor import SYSTEM_ACTOR, Actor
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.errors import ForbiddenError, NotFoundError

ALICE = Actor(id=uuid.uuid4(), roles=frozenset({"member"}))
BOB = Actor(id=uuid.uuid4(), roles=frozenset({"member"}))


async def test_check_records_the_pair() -> None:
    """Every check is recorded in order."""
    guard = InMemoryAccessGuard()
    await guard.check(ALICE, Public())
    await guard.check(BOB, Content())
    assert guard.checked == [(ALICE, Public()), (BOB, Content())]


async def test_a_denying_guard_raises_forbidden() -> None:
    """A guard told to deny refuses, and still records the check."""
    guard = InMemoryAccessGuard(deny=True)
    with pytest.raises(ForbiddenError):
        await guard.check(ALICE, Public())
    assert guard.checked == [(ALICE, Public())]


def test_scope_for_is_own_content_or_everyone_for_system() -> None:
    """Members see their own content; the system actor sees everything."""
    guard = InMemoryAccessGuard()
    assert guard.scope_for(ALICE) == ContentFilter.of(ALICE.id)
    assert guard.scope_for(SYSTEM_ACTOR).is_everyone


@pytest.mark.parametrize(
    "method", ["assert_can_view", "assert_can_modify", "assert_can_delete"]
)
def test_ownership_asserts(method: str) -> None:
    """Own and system pass; foreign and ownerless content is not found."""
    check = getattr(InMemoryAccessGuard(), method)
    check(ALICE, ALICE.id)
    check(SYSTEM_ACTOR, BOB.id)
    check(SYSTEM_ACTOR, None)
    with pytest.raises(NotFoundError):
        check(ALICE, BOB.id)
    with pytest.raises(NotFoundError):
        check(ALICE, None)


class _Permission:
    value = "demo:thing:read"


async def test_deny_all_guard_lets_only_public_use_cases_run() -> None:
    """Unwired, the guard admits `Public` and refuses every other stance."""
    guard = DenyAllAccessGuard()
    await guard.check(SYSTEM_ACTOR, Public())
    refused: tuple[Access, ...] = (
        System(),
        OwnAccount(),
        Shared(),
        Content(),
        Requires(_Permission),  # type: ignore[arg-type]
    )
    for access in refused:
        with pytest.raises(ForbiddenError):
            await guard.check(SYSTEM_ACTOR, access)


def test_deny_all_guard_refuses_every_ownership_question() -> None:
    """With nothing wired, no content is visible or changeable."""
    guard = DenyAllAccessGuard()
    with pytest.raises(ForbiddenError):
        guard.scope_for(ALICE)
    for check in (
        guard.assert_can_view,
        guard.assert_can_modify,
        guard.assert_can_delete,
    ):
        with pytest.raises(ForbiddenError):
            check(ALICE, ALICE.id)
