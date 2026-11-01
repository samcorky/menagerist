"""Explicit user-transfer tables and vocabulary reference handling."""

import json
from typing import TYPE_CHECKING

from app.modules.backup.domain.errors import CorruptBackupError

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from uuid import UUID

OWNED_TABLES = frozenset(
    {"nodes", "edges", "collections", "media_assets", "example_installations"}
)
# Content tables whose soft-deleted rows an export leaves out and an import skips.
SOFT_DELETABLE = frozenset({"nodes", "edges", "collections"})
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
)
VOCABULARY = frozenset({"presets", "node_types", "edge_types"})
ENTITY_TABLES = {
    "preset": "presets",
    "item_type": "node_types",
    "relationship_type": "edge_types",
}
MAX_ROW_BYTES = 16 * 1024 * 1024


def installation_vocabulary(records: object) -> dict[str, set[str]]:
    """Keep shared structure still referenced by example installation records."""
    result: dict[str, set[str]] = {name: set() for name in VOCABULARY}
    if isinstance(records, list):
        for record in records:
            if isinstance(record, dict) and record.get("outcome") != "removed":
                name = ENTITY_TABLES.get(str(record.get("kind")))
                if name is not None:
                    result[name].add(str(record.get("entity_id")))
    return result


_PARENTS = {
    "edges": (("source_id", "nodes"), ("target_id", "nodes")),
    "collection_members": (("collection_id", "collections"), ("item_id", "nodes")),
    "media_attachments": (("target_id", "nodes"),),
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


def preset_ids(value: object) -> set[str]:
    """Find choice-list references in schema metadata."""
    result: set[str] = set()
    if isinstance(value, dict):
        metadata = value.get("x-menagerist")
        if isinstance(metadata, dict) and isinstance(metadata.get("list"), str):
            result.add(metadata["list"])
        for child in value.values():
            result.update(preset_ids(child))
    elif isinstance(value, list):
        for child in value:
            result.update(preset_ids(child))
    return result


def remap_schema(value: object, remap: dict[str, str]) -> object:
    """Rewrite only schema list references, retaining ordinary attribute values."""
    if isinstance(value, list):
        return [remap_schema(child, remap) for child in value]
    if not isinstance(value, dict):
        return value
    result = {key: remap_schema(child, remap) for key, child in value.items()}
    metadata = result.get("x-menagerist")
    if isinstance(metadata, dict) and isinstance(metadata.get("list"), str):
        metadata["list"] = remap.get(f"presets:{metadata['list']}", metadata["list"])
    return result


def _remap_entities(records: list[object], remap: dict[str, str]) -> list[object]:
    entities: list[object] = []
    for entity in records:
        if isinstance(entity, dict):
            entity = dict(entity)
            table = ENTITY_TABLES.get(str(entity.get("kind")))
            for key in ("id", "entity_id"):
                if isinstance(entity.get(key), str):
                    entity[key] = remap.get(f"{table}:{entity[key]}", entity[key])
        entities.append(entity)
    return entities


def prepare_row(
    name: str, row: dict[str, object], owner_id: UUID, remap: dict[str, str]
) -> dict[str, object]:
    """Stamp ownership and remap structural references after vocabulary reuse."""
    row = dict(row)
    if name in OWNED_TABLES:
        row["owner_id"] = owner_id
    for key in ("attributes_schema", "extra_schema", "definition"):
        if key in row:
            row[key] = remap_schema(row[key], remap)
    records = row.get("entities")
    if name == "example_installations" and isinstance(records, list):
        row["entities"] = _remap_entities(records, remap)
    if name == "media_assets":
        row["has_thumbnail"] = False
        row["thumbnail_sha256"] = None
    if name == "presets":
        row["builtin"] = False
    return row


def compatible(
    name: str, incoming: dict[str, object], existing: dict[str, object]
) -> bool:
    """Only reuse shared vocabulary with the same behaviour and schema."""
    keys = (
        ("kind", "definition")
        if name == "presets"
        else ("attributes_schema", "directional")
    )
    return all(incoming.get(key) == existing.get(key) for key in keys) and (
        incoming.get("deleted_at") is None
    ) == (existing.get("deleted_at") is None)
