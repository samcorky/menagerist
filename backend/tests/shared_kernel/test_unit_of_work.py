from typing import TypeVar

import pytest

from app.shared_kernel.unit_of_work import InMemoryUnitOfWork, JoinedUnitOfWork

_T = TypeVar("_T")


async def test_in_memory_unit_of_work_yields_the_wrapped_repos() -> None:
    """Entering the context manager returns the exact repos object it was built with."""
    repos = object()
    uow = InMemoryUnitOfWork(repos)

    async with uow as entered:
        assert entered is repos


async def test_in_memory_unit_of_work_commit_sets_committed_flag() -> None:
    """Calling commit() records that the unit of work was committed."""
    uow = InMemoryUnitOfWork(repos=object())

    async with uow:
        await uow.commit()

    assert uow.committed is True
    assert uow.rolled_back is False


async def test_in_memory_unit_of_work_records_rollback_on_exception() -> None:
    """An exception inside the `async with` block marks the unit of work rolled back."""
    uow = InMemoryUnitOfWork(repos=object())

    with pytest.raises(ValueError, match="boom"):
        async with uow:
            raise ValueError("boom")

    assert uow.rolled_back is True
    assert uow.committed is False


# ── on_commit ─────────────────────────────────────────────────────────────────


async def test_on_commit_callback_fires_after_commit() -> None:
    """A callback registered with on_commit runs when commit() is called."""
    fired: list[str] = []
    uow = InMemoryUnitOfWork(repos=object())

    async with uow:
        uow.on_commit(lambda: _append(fired, "cb"))
        await uow.commit()

    assert fired == ["cb"]


async def test_on_commit_callbacks_fire_in_registration_order() -> None:
    """Multiple callbacks run in the order they were registered."""
    order: list[int] = []
    uow = InMemoryUnitOfWork(repos=object())

    async with uow:
        uow.on_commit(lambda: _append(order, 1))
        uow.on_commit(lambda: _append(order, 2))
        uow.on_commit(lambda: _append(order, 3))
        await uow.commit()

    assert order == [1, 2, 3]


async def test_on_commit_callback_not_fired_without_commit() -> None:
    """Callbacks are not run if the block exits without calling commit()."""
    fired: list[str] = []
    uow = InMemoryUnitOfWork(repos=object())

    async with uow:
        uow.on_commit(lambda: _append(fired, "cb"))

    assert fired == []


async def test_on_commit_callback_not_fired_on_rollback() -> None:
    """Callbacks registered before a rollback are silently dropped."""
    fired: list[str] = []
    uow = InMemoryUnitOfWork(repos=object())

    async def _run() -> None:
        async with uow:
            uow.on_commit(lambda: _append(fired, "cb"))
            raise RuntimeError("rollback")

    with pytest.raises(RuntimeError, match="rollback"):
        await _run()

    assert fired == []


async def test_on_commit_callbacks_cleared_after_commit() -> None:
    """Callback queue is drained after commit; a second commit does not re-run them."""
    fired: list[str] = []
    uow = InMemoryUnitOfWork(repos=object())

    async with uow:
        uow.on_commit(lambda: _append(fired, "first"))
        await uow.commit()

    # Re-enter and commit without registering new callbacks.
    async with uow:
        await uow.commit()

    assert fired == ["first"]  # not ["first", "first"]


# ── JoinedUnitOfWork ──────────────────────────────────────────────────────────


async def test_joined_uow_yields_existing_repos() -> None:
    """JoinedUnitOfWork.__aenter__ returns the repos it was constructed with."""
    repos = object()
    owner = InMemoryUnitOfWork(repos)

    async with owner:
        joined = JoinedUnitOfWork(repos, owner=owner)
        async with joined as entered:
            assert entered is repos


async def test_joined_uow_commit_is_noop() -> None:
    """JoinedUnitOfWork.commit() does not commit the owner or set committed flag."""
    repos = object()
    owner = InMemoryUnitOfWork(repos)

    async with owner as _:
        joined = JoinedUnitOfWork(repos, owner=owner)
        async with joined:
            await joined.commit()

    # owner.commit() was never called
    assert owner.committed is False


async def test_joined_uow_exit_does_not_rollback_owner() -> None:
    """JoinedUnitOfWork exit with exception does not mark the owner as rolled back."""
    repos = object()
    owner = InMemoryUnitOfWork(repos)

    async with owner:
        joined = JoinedUnitOfWork(repos, owner=owner)
        with pytest.raises(ValueError, match="sub-error"):
            async with joined:
                raise ValueError("sub-error")
        # owner is still open; check it can still commit
        await owner.commit()

    assert owner.committed is True
    assert owner.rolled_back is False


async def test_joined_uow_on_commit_forwarded_to_owner() -> None:
    """Callbacks registered on a JoinedUnitOfWork run when the owner commits."""
    fired: list[str] = []
    repos = object()
    owner = InMemoryUnitOfWork(repos)

    async with owner:
        joined = JoinedUnitOfWork(repos, owner=owner)
        async with joined:
            joined.on_commit(lambda: _append(fired, "from-joined"))
            await joined.commit()  # no-op

        assert fired == []  # owner not committed yet
        await owner.commit()

    assert fired == ["from-joined"]


async def test_joined_uow_on_commit_not_fired_if_owner_rolls_back() -> None:
    """on_commit callbacks from JoinedUnitOfWork are dropped if owner rolls back."""
    fired: list[str] = []
    repos = object()
    owner = InMemoryUnitOfWork(repos)

    async def _run() -> None:
        async with owner:
            joined = JoinedUnitOfWork(repos, owner=owner)
            async with joined:
                joined.on_commit(lambda: _append(fired, "cb"))
            raise RuntimeError("outer failure")

    with pytest.raises(RuntimeError, match="outer failure"):
        await _run()

    assert fired == []


# ── helpers ───────────────────────────────────────────────────────────────────


async def _append[T](lst: list[T], value: T) -> None:
    """Async helper that appends a value — usable as an on_commit callback."""
    lst.append(value)
