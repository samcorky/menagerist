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
    """Weak ETag derived from entity ID and last-modified timestamp.

    Weak (`W/"..."`) rather than strong: nginx gzip-compresses `/api/` JSON
    responses, and a compressing proxy is entitled to rewrite a strong ETag to
    weak on the way out (the compressed bytes aren't byte-identical to what
    produced the tag). Emitting it weak ourselves means that rewrite - if it
    happens - is a no-op, so the value a client caches from a GET always
    matches what a later PATCH's conditional check compares against. See
    `docs/DECISIONS.md` ("weak ETags to survive a compressing proxy").
    """
    digest = hashlib.sha256(
        f"{entity.id}:{entity.updated_at.isoformat()}".encode()
    ).hexdigest()[:16]
    return f'W/"{digest}"'
