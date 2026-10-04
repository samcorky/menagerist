"""Pack envelope for export and import, and the content hash that spots repeats."""

import hashlib
import json
from typing import Any

from app.modules.presets.domain.errors import InvalidPresetDefinitionError
from app.modules.presets.domain.preset import VALID_KINDS

PACK_FORMAT = "menagerist-presets"
PACK_VERSION = 1
MAX_PACK_ITEMS = 200
MAX_LABEL_LENGTH = 200
MAX_DESCRIPTION_LENGTH = 2000
MAX_DEFINITION_BYTES = 64 * 1024


def content_hash(kind: str, label: str, definition: dict[str, Any]) -> str:
    """Return a stable hash of a preset's kind, label and definition.

    Two presets with the same content hash are treated as the same preset on import.
    """
    canonical = json.dumps(
        {"kind": kind, "label": label, "definition": definition},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def check_pack_envelope(
    pack_format: str, pack_version: int, items: list[dict[str, Any]]
) -> None:
    """Reject a pack whose envelope or size is not one this server accepts.

    :raises InvalidPresetDefinitionError: unknown format or version, or too many items.
    """
    if pack_format != PACK_FORMAT:
        raise InvalidPresetDefinitionError(f"format must be '{PACK_FORMAT}'")
    if pack_version != PACK_VERSION:
        raise InvalidPresetDefinitionError(f"unsupported pack version {pack_version}")
    if len(items) > MAX_PACK_ITEMS:
        raise InvalidPresetDefinitionError(
            f"a pack may hold at most {MAX_PACK_ITEMS} presets"
        )


def check_pack_item(item: dict[str, Any]) -> None:
    """Check one pack item's kind, label, description and size limits.

    The definition's shape is checked separately by `check_definition`.

    :raises InvalidPresetDefinitionError: when the item is malformed or oversized.
    """
    kind = item.get("kind")
    if kind not in VALID_KINDS:
        raise InvalidPresetDefinitionError(f"unknown preset kind {kind!r}")
    label = item.get("label")
    if not isinstance(label, str) or label.strip() == "":
        raise InvalidPresetDefinitionError("every preset needs a non-blank label")
    if len(label) > MAX_LABEL_LENGTH:
        raise InvalidPresetDefinitionError(
            f"labels are limited to {MAX_LABEL_LENGTH} characters"
        )
    description = item.get("description")
    if description is not None and (
        not isinstance(description, str) or len(description) > MAX_DESCRIPTION_LENGTH
    ):
        raise InvalidPresetDefinitionError(
            f"descriptions are limited to {MAX_DESCRIPTION_LENGTH} characters"
        )
    definition = item.get("definition")
    if not isinstance(definition, dict):
        raise InvalidPresetDefinitionError("every preset needs a 'definition' object")
    if len(json.dumps(definition).encode("utf-8")) > MAX_DEFINITION_BYTES:
        raise InvalidPresetDefinitionError("a definition is limited to 64 KiB")
