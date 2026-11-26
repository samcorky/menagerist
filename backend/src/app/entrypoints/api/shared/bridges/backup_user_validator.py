"""Validate portable rows with the modules that own their domain rules."""

from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Mapping

    from app.modules.graph.domain.edge_type import Holder

import jsonschema

from app.modules.backup.domain.errors import CorruptBackupError
from app.modules.graph.application.schema_meta import check_meta_shape
from app.modules.graph.domain.edge_type import EdgeType
from app.modules.graph.domain.node_type import NodeType
from app.modules.media.domain.media_asset import MediaStatus
from app.modules.presets.application.preset_definitions import check_definition
from app.modules.presets.domain.preset import Preset
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.errors import ValidationError


def _text(row: Mapping[str, object], key: str) -> str:
    value = row[key]
    if not isinstance(value, str):
        raise ValueError(f"{key} must be text")
    return value


def _optional_text(row: Mapping[str, object], key: str) -> str | None:
    value = row.get(key)
    if value is not None and not isinstance(value, str):
        raise ValueError(f"{key} must be text or null")
    return value


def _text_list(row: Mapping[str, object], key: str) -> tuple[str, ...]:
    # A backup from before the limits existed has no such column.
    value = row.get(key) or []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValueError(f"{key} must be a list of text")
    return tuple(value)


def _object(row: Mapping[str, object], key: str) -> dict[str, Any]:
    value = row[key]
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError(f"{key} must be an object")
    return value


def _schema(row: Mapping[str, object], key: str) -> dict[str, Any] | None:
    if row.get(key) is None:
        return None
    schema = _object(row, key)
    jsonschema.validators.validator_for(schema).check_schema(schema)
    check_meta_shape(schema)
    return schema


def _validate_type(table: str, row: Mapping[str, object]) -> None:
    slug, label = _text(row, "slug"), _text(row, "label")
    schema = _schema(row, "attributes_schema")
    description = _optional_text(row, "description")
    if table == "node_types":
        # A backup from before parent types has no such column.
        parent = _optional_text(row, "parent")
        node_type = NodeType.create(
            owner_id=SYSTEM_ACTOR.id,
            slug=slug,
            label=label,
            description=description,
            attributes_schema=schema,
            icon=_optional_text(row, "icon"),
            colour=_optional_text(row, "colour"),
            parent=parent,
        )
        if node_type.parent != parent:
            raise ValueError("parent must be normalised")
        entity: NodeType | EdgeType = node_type
    else:
        directional = row["directional"]
        if not isinstance(directional, bool):
            raise ValueError("directional must be a boolean")
        entity = EdgeType.create(
            owner_id=SYSTEM_ACTOR.id,
            slug=slug,
            label=label,
            description=description,
            attributes_schema=schema,
            directional=directional,
            reverse_label=_optional_text(row, "reverse_label"),
            # A backup from before `holder` existed has no such column.
            holder=cast("Holder", row.get("holder", "none")),
            source_types=_text_list(row, "source_types"),
            target_types=_text_list(row, "target_types"),
        )
    if str(entity.slug) != slug:
        raise ValueError("slug must be normalised")


class BackupUserImportValidator:
    """Check preset, type and media values before importing untrusted rows."""

    async def validate(self, table: str, row: Mapping[str, object]) -> None:
        """Reject invalid domain values without invoking persistence use cases."""
        try:
            if table == "presets":
                kind, label = _text(row, "kind"), _text(row, "label")
                definition = _object(row, "definition")
                check_definition(kind, definition)
                Preset.create(
                    owner_id=SYSTEM_ACTOR.id,
                    kind=kind,
                    label=label,
                    definition=definition,
                    description=_optional_text(row, "description"),
                )
            elif table in {"node_types", "edge_types"}:
                _validate_type(table, row)
            elif table == "media_assets":
                MediaStatus(_text(row, "status"))
                if not _text(row, "filename").strip():
                    raise ValueError("filename must be provided")
            elif table == "nodes":
                _schema(row, "extra_schema")
        except (
            ValidationError,
            jsonschema.SchemaError,
            ValueError,
            TypeError,
            KeyError,
        ) as error:
            raise CorruptBackupError(f"Invalid {table} row: {error}") from error
