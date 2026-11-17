import hashlib
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

    from app.modules.transfer.domain.bundle import BundleItem


def content_hash(content: Mapping[str, Any]) -> str:
    """Return a stable SHA-256 of `content`, independent of key order."""
    canonical = json.dumps(
        content, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def preset_key(kind: str, label: str, definition: Mapping[str, Any]) -> str:
    """Return the hash that makes two presets "the same": kind, label, definition."""
    return content_hash({"kind": kind, "label": label, "definition": definition})


def item_field_hashes(item: BundleItem) -> dict[str, str]:
    """Return a hash per field of `item`, as a source link records them."""
    values: dict[str, Any] = {
        "name": item.name,
        "description": item.description,
        "tags": list(item.tags),
    }
    values |= {f"attributes.{key}": value for key, value in item.attributes.items()}
    return {field: content_hash({"value": value}) for field, value in values.items()}
