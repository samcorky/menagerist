from datetime import UTC, datetime

from app.shared_kernel.mixins import SoftDeletable


def test_restore_clears_the_mark_and_touches_the_row() -> None:
    """A deleted entity is live again, with a fresh `updated_at`."""
    then = datetime(2026, 1, 1, tzinfo=UTC)
    entity = SoftDeletable(created_at=then, updated_at=then)
    entity.soft_delete()

    entity.restore()

    assert not entity.is_deleted
    assert entity.updated_at > then
