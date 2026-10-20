from typing import TYPE_CHECKING

from app.modules.backup.adapters.persistence.row_codec import encode_row
from app.modules.backup.adapters.persistence.user_transfer_rows import (
    OWNED_TABLES,
    USER_TABLES,
    installation_vocabulary,
    preset_ids,
)
from app.modules.backup.adapters.storage.in_memory_backup_reader import (
    InMemoryBackupReader,
)
from app.modules.backup.domain.errors import CorruptBackupError

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from app.modules.backup.ports.archive_member import ArchiveMember
    from app.shared_kernel.access_scope import AccessScope


class InMemoryUserDatabaseSnapshot:
    """Owner-filtered content with only its referenced types and choice lists."""

    def __init__(
        self, revision: str, tables: dict[str, list[dict[str, object]]]
    ) -> None:
        self.revision, self.tables = revision, tables

    async def schema_revision(self) -> str:
        """Return the configured source revision."""
        return self.revision

    def export(self, *, scope: AccessScope) -> AsyncGenerator[ArchiveMember]:
        """Filter child rows through both their owner and content targets."""
        if scope.user_id is None:
            raise CorruptBackupError("User export requires one owner.")
        selected = {
            name: [
                row
                for row in self.tables.get(name, [])
                if str(row.get("owner_id")) == str(scope.user_id)
            ]
            for name in OWNED_TABLES
        }
        nodes = {str(row["id"]) for row in selected["nodes"]}
        collections = {str(row["id"]) for row in selected["collections"]}
        assets = {str(row["id"]) for row in selected["media_assets"]}
        selected["edges"] = [
            row
            for row in selected["edges"]
            if str(row.get("source_id")) in nodes and str(row.get("target_id")) in nodes
        ]
        selected["collection_members"] = [
            row
            for row in self.tables.get("collection_members", [])
            if str(row.get("collection_id")) in collections
            and str(row.get("item_id")) in nodes
        ]
        selected["media_attachments"] = [
            row
            for row in self.tables.get("media_attachments", [])
            if str(row.get("asset_id")) in assets
            and row.get("target_type") == "node"
            and str(row.get("target_id")) in nodes
        ]
        installation_refs: dict[str, set[str]] = {
            name: set() for name in ("presets", "node_types", "edge_types")
        }
        for row in selected["example_installations"]:
            for name, ids in installation_vocabulary(row.get("entities")).items():
                installation_refs[name].update(ids)
        for vocabulary, content in (("node_types", "nodes"), ("edge_types", "edges")):
            slugs = {row.get("type") for row in selected[content]}
            selected[vocabulary] = [
                row
                for row in self.tables.get(vocabulary, [])
                if (row.get("slug") in slugs and row.get("deleted_at") is None)
                or str(row.get("id")) in installation_refs[vocabulary]
            ]
        refs = set().union(
            *(
                preset_ids(row)
                for name in ("node_types", "edge_types", "nodes")
                for row in selected[name]
            )
        )
        refs.update(installation_refs["presets"])
        selected["presets"] = [
            row for row in self.tables.get("presets", []) if str(row["id"]) in refs
        ]
        return InMemoryBackupReader(
            {
                f"data/{name}.ndjson": b"".join(
                    encode_row(row) for row in selected[name]
                )
                for name in USER_TABLES
            }
        ).members()
