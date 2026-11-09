"""Which person's types an item or connection resolves its type against."""

from typing import TYPE_CHECKING

from app.shared_kernel.content_filter import ContentFilter

if TYPE_CHECKING:
    import uuid


def owner_scope(owner_id: uuid.UUID | None) -> ContentFilter:
    """The types owned by `owner_id`, who owns the item or connection.

    A legacy row with no owner (before the first-admin claim) sees every type,
    since its types have no owner yet either.
    """
    return ContentFilter.everyone() if owner_id is None else ContentFilter.of(owner_id)
