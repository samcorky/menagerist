import pytest

from app.shared_kernel.unit_of_work import InMemoryUnitOfWork


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
