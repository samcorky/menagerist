"""The in-memory job queue records what a module asked for."""

from uuid import uuid7

from app.shared_kernel.job_queue import InMemoryJobQueue, JobQueue


async def test_records_each_request_in_order() -> None:
    """A test can assert which jobs a use case queued, and for whom."""
    first, second = uuid7(), uuid7()
    queue: JobQueue = InMemoryJobQueue()
    await queue.request("transfer.item_imports", requested_by=first)
    await queue.request("transfer.item_imports", requested_by=second)
    assert isinstance(queue, InMemoryJobQueue)
    assert queue.requests == [
        ("transfer.item_imports", first),
        ("transfer.item_imports", second),
    ]
