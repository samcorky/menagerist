"""Explicit policies for every table in a reflected instance schema."""

from enum import StrEnum

from app.modules.backup.domain.errors import CorruptBackupError


class TableRule(StrEnum):
    """Treatment of a table during instance backup and restore."""

    KEEP = "keep"
    SKIP = "skip"
    IGNORE = "ignore"


TABLE_RULES = {
    **dict.fromkeys(
        (
            "users",
            "nodes",
            "edges",
            "collections",
            "collection_members",
            "media_assets",
            "media_attachments",
            "node_types",
            "edge_types",
            "presets",
            "example_installations",
        ),
        TableRule.KEEP,
    ),
    "api_tokens": TableRule.SKIP,
    "sessions": TableRule.SKIP,
    "sign_in_attempts": TableRule.SKIP,
    "job_runs": TableRule.SKIP,
    "schedule_cursors": TableRule.SKIP,
    "worker_heartbeats": TableRule.SKIP,
    "alembic_version": TableRule.IGNORE,
}


def table_rule(name: str) -> TableRule:
    """Return an explicit policy, refusing unclassified schema additions."""
    if name not in TABLE_RULES:
        raise CorruptBackupError(f"No backup rule for table {name!r}")
    return TABLE_RULES[name]
