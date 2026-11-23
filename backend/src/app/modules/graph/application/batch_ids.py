from typing import TYPE_CHECKING

from app.shared_kernel.errors import ValidationError

if TYPE_CHECKING:
    import uuid

BATCH_LIMIT = 200


def check_batch_ids(ids: list[uuid.UUID]) -> list[uuid.UUID]:
    """Return `ids` without duplicates, refusing an empty or oversized batch."""
    unique = list(dict.fromkeys(ids))
    if not unique:
        raise ValidationError("Choose at least one item")
    if len(unique) > BATCH_LIMIT:
        raise ValidationError(f"Choose at most {BATCH_LIMIT} items at a time")
    return unique


def unknown_items_error(missing: list[uuid.UUID]) -> ValidationError:
    """The error for a batch naming items that are missing, deleted or hidden."""
    return ValidationError(
        "Unknown or deleted items: " + ", ".join(str(item) for item in missing)
    )
