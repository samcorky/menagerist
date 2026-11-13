"""Explicit user-transfer tables and ownership stamping."""

import json
from typing import TYPE_CHECKING

from app.modules.backup.domain.errors import CorruptBackupError

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from uuid import UUID

OWNED_TABLES = frozenset(
    {
        "presets",
        "node_types",
        "edge_types",
        "nodes",
        "edges",
        "collections",
        "media_assets",
        "example_installations",
    }
)
# Content tables whose soft-deleted rows an export leaves out and an import skips.
SOFT_DELETABLE = frozenset(
    {"presets", "node_types", "edge_types", "nodes", "edges", "collections"}
)
USER_TABLES = (
    "presets",
    "node_types",
    "edge_types",
    "nodes",
    "media_assets",
    "collections",
    "example_installations",
    "edges",
    "collection_members",
    "media_attachments",
    "node_favourites",
)
MAX_ROW_BYTES = 16 * 1024 * 1024


_PARENTS = {
    "edges": (("source_id", "nodes"), ("target_id", "nodes")),
    "collection_members": (("collection_id", "collections"), ("item_id", "nodes")),
    "media_attachments": (("target_id", "nodes"),),
    "node_favourites": (("node_id", "nodes"),),
}


def skip_row(name: str, row: dict[str, object], skipped: dict[str, set[str]]) -> bool:
    """Whether an incoming row is soft-deleted or hangs off a skipped one.

    Records the id of a skipped soft-deletable row, so its dependants follow.
    """
    if name in SOFT_DELETABLE and row.get("deleted_at") is not None:
        skipped[name].add(str(row.get("id")))
        return True
    return any(
        str(row.get(key)) in skipped[parent] for key, parent in _PARENTS.get(name, ())
    )


def import_table_name(member_name: str, seen: set[str]) -> str:
    """Require the complete deterministic user-table dependency order."""
    expected = (
        f"data/{USER_TABLES[len(seen)]}.ndjson"
        if len(seen) < len(USER_TABLES)
        else None
    )
    if member_name != expected:
        raise CorruptBackupError("Unexpected or out-of-order user import table.")
    name = USER_TABLES[len(seen)]
    seen.add(name)
    return name


async def read_rows(chunks: AsyncIterator[bytes]) -> AsyncIterator[dict[str, object]]:
    """Decode one bounded row at a time without buffering a table."""
    pending = bytearray()
    async for chunk in chunks:
        pending.extend(chunk)
        while (end := pending.find(b"\n")) != -1:
            if end > MAX_ROW_BYTES:
                raise CorruptBackupError("User archive row exceeds the size limit.")
            line = bytes(pending[:end])
            del pending[: end + 1]
            try:
                value: object = json.loads(line)
            except (ValueError, UnicodeError) as exc:
                raise CorruptBackupError("Invalid user archive row.") from exc
            if not isinstance(value, dict):
                raise CorruptBackupError("User archive rows must be objects.")
            yield value
        if len(pending) > MAX_ROW_BYTES:
            raise CorruptBackupError("User archive row exceeds the size limit.")
    if pending:
        raise CorruptBackupError("Unterminated user archive row.")


def prepare_row(name: str, row: dict[str, object], owner_id: UUID) -> dict[str, object]:
    """Stamp ownership on owned rows and regenerate derived media fields."""
    row = dict(row)
    if name in OWNED_TABLES:
        row["owner_id"] = owner_id
    if name == "node_favourites":
        row["user_id"] = owner_id
    if name == "media_assets":
        row["has_thumbnail"] = False
        row["thumbnail_sha256"] = None
    return row
