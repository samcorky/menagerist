import pytest

from app.entrypoints.api.shared.bridges.backup_user_validator import (
    BackupUserImportValidator,
)
from app.modules.backup.domain.errors import CorruptBackupError


@pytest.mark.parametrize(
    ("table", "row"),
    [
        (
            "presets",
            {"kind": "invalid", "label": "List", "definition": {"options": ["A"]}},
        ),
        (
            "presets",
            {"kind": "choice_list", "label": " ", "definition": {"options": ["A"]}},
        ),
        (
            "presets",
            {"kind": "choice_list", "label": "List", "definition": {"options": [1]}},
        ),
        ("presets", {"kind": "choice_list", "label": "List", "definition": []}),
        ("presets", {"kind": "choice_list", "label": "List"}),
        ("node_types", {"slug": "book", "label": " ", "attributes_schema": None}),
        (
            "node_types",
            {"slug": "Book Name", "label": "Book", "attributes_schema": None},
        ),
        (
            "node_types",
            {"slug": "book", "label": "Book", "attributes_schema": {"type": "invalid"}},
        ),
        ("node_types", {"slug": "book", "label": "Book", "attributes_schema": []}),
        ("node_types", {"slug": "book", "label": "Book", "description": 3}),
        ("node_types", {"slug": "book", "label": "Book", "colour": "purple"}),
        ("node_types", {"slug": "book", "label": "Book", "colour": 3}),
        ("node_types", {"slug": "book", "label": "Book", "icon": "Not An Icon"}),
        ("node_types", {"slug": "book", "label": "Book", "icon": ["book"]}),
        ("edge_types", {"slug": "owns", "label": "Owns", "directional": "yes"}),
        (
            "edge_types",
            {"slug": "owns", "label": "Owns", "directional": True, "reverse_label": 1},
        ),
        ("media_assets", {"status": "../outside", "filename": "missing-original"}),
        ("media_assets", {"status": "attached", "filename": " "}),
        ("media_assets", {"status": 4, "filename": "file"}),
        ("nodes", {"extra_schema": {"type": "invalid"}}),
    ],
)
async def test_rejects_invalid_user_rows(table: str, row: dict[str, object]) -> None:
    """Reject invalid vocabulary and media even when no original file is present."""
    with pytest.raises(CorruptBackupError):
        await BackupUserImportValidator().validate(table, row)


@pytest.mark.parametrize(
    ("table", "row"),
    [
        (
            "presets",
            {"kind": "choice_list", "label": "List", "definition": {"options": ["A"]}},
        ),
        (
            "node_types",
            {"slug": "book", "label": "Book", "attributes_schema": {"type": "object"}},
        ),
        (
            "node_types",
            {"slug": "book", "label": "Book", "icon": "book-open", "colour": "teal"},
        ),
        ("node_types", {"slug": "book", "label": "Book", "icon": None, "colour": None}),
        ("edge_types", {"slug": "owns", "label": "Owns", "directional": True}),
        ("media_assets", {"status": "orphaned", "filename": "original.pdf"}),
        ("nodes", {"extra_schema": None}),
        ("collections", {}),
    ],
)
async def test_accepts_valid_user_rows(table: str, row: dict[str, object]) -> None:
    """Valid portable rows pass without invoking write use cases."""
    await BackupUserImportValidator().validate(table, row)


async def test_rejects_invalid_schema_metadata() -> None:
    """Apply graph metadata rules as well as standard JSON Schema validation."""
    with pytest.raises(CorruptBackupError):
        await BackupUserImportValidator().validate(
            "node_types",
            {
                "slug": "book",
                "label": "Book",
                "attributes_schema": {
                    "type": "object",
                    "x-menagerist": {"required": "wrong-type"},
                },
            },
        )
