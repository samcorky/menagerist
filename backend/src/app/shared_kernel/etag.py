import hashlib
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import uuid
    from datetime import datetime


class ETaggable(Protocol):
    """Protocol: any entity with id and updated_at fields for ETag generation."""

    id: uuid.UUID
    updated_at: datetime


def etag_from_entity(entity: ETaggable) -> str:
    """Strong ETag derived from entity ID and last-modified timestamp."""
    digest = hashlib.sha256(
        f"{entity.id}:{entity.updated_at.isoformat()}".encode()
    ).hexdigest()[:16]
    return f'"{digest}"'
