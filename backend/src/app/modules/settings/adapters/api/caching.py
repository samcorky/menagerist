"""ETag handling for the settings schema documents."""

import hashlib
import json

# The schemas change only between releases; clients revalidate cheaply.
REVALIDATE = "private, no-cache"


def etag(schema: dict[str, object]) -> str:
    """A strong ETag for a schema document, stable across key order."""
    body = json.dumps(schema, sort_keys=True, separators=(",", ":")).encode()
    return f'"{hashlib.sha256(body).hexdigest()[:32]}"'


def not_modified(header: str | None, tag: str) -> bool:
    """Whether an `If-None-Match` header already names this version."""
    if not header:
        return False
    candidates = [part.strip() for part in header.split(",")]
    return "*" in candidates or any(c.removeprefix("W/") == tag for c in candidates)
