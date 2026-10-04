"""seed_builtin_presets

Seeds the built-in saved lists, fields and field groups in one step, using each
preset's final shape. Ids are fixed (uuid5), so a re-run inserts nothing new.

Revision ID: e6f7a8b9c0d1
Revises: e5f6a7b8c9d0
Create Date: 2026-10-04 09:00:00.000000

"""

import json
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.platform.shared_data import shared_data_path

# revision identifiers, used by Alembic.
revision: str = "e6f7a8b9c0d1"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NAMESPACE = uuid.UUID("6f1d2a7e-3c4b-4e5f-8a9b-0c1d2e3f4a5b")
_ISO_DATA = "iso-data.json"
_GRADES = [
    "Mint",
    "Near Mint",
    "Excellent",
    "Very Good",
    "Good",
    "Fair",
    "Poor",
]
_FORMATS = ["LP", "EP", "Single", "Box set"]
_MONEY: dict[str, Any] = {
    "type": "object",
    "properties": {
        "value": {"title": "Value", "type": "number"},
        "currency": {"title": "Currency", "type": "string"},
    },
}
_QUANTITY: dict[str, Any] = {
    "type": "object",
    "properties": {
        "value": {"title": "Value", "type": "number"},
        "unit": {"title": "Unit", "type": "string"},
    },
}

# Recipe ingredients: a table (`group` field) with an amount per row.
_INGREDIENTS: dict[str, Any] = {
    "title": "Ingredients",
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "ingredient": {
                "title": "Ingredient",
                "type": "string",
                "x-menagerist": {"kind": "text"},
            },
            "amount": {
                "title": "Amount",
                **_QUANTITY,
                "x-menagerist": {"kind": "quantity"},
            },
            "notes": {
                "title": "Notes",
                "type": "string",
                "x-menagerist": {"kind": "text"},
            },
        },
    },
    "x-menagerist": {
        "kind": "group",
        "columns": ["ingredient", "amount", "notes"],
    },
}

# (kind, label, definition). Lists are keyed by label alone; others by kind and label.
_BUILTIN_FIELDS: list[tuple[str, str, dict[str, Any]]] = [
    (
        "field",
        "Condition",
        {
            "property": {
                "title": "Condition",
                "type": "string",
                "enum": _GRADES,
                "x-menagerist": {"kind": "choice"},
            }
        },
    ),
    (
        "field",
        "Purchase price",
        {
            "property": {
                "title": "Purchase price",
                **_MONEY,
                "x-menagerist": {"kind": "money"},
            }
        },
    ),
    (
        "field",
        "Released",
        {
            "property": {
                "title": "Released",
                "type": "string",
                "format": "date",
                "x-menagerist": {"kind": "date"},
            }
        },
    ),
    (
        "field",
        "Rating",
        {
            "property": {
                "title": "Rating",
                "type": "number",
                "minimum": 1,
                "maximum": 5,
                "multipleOf": 1,
                "x-menagerist": {"kind": "rating"},
            }
        },
    ),
    (
        "field",
        "Website",
        {
            "property": {
                "title": "Website",
                "type": "string",
                "format": "uri",
                "x-menagerist": {"kind": "url"},
            }
        },
    ),
    (
        "field_set",
        "Purchase details",
        {
            "section": "Purchase details",
            "properties": [
                {
                    "title": "Purchase price",
                    **_MONEY,
                    "x-menagerist": {"kind": "money"},
                },
                {
                    "title": "Purchase date",
                    "type": "string",
                    "format": "date",
                    "x-menagerist": {"kind": "date"},
                },
                {
                    "title": "Bought from",
                    "type": "string",
                    "x-menagerist": {"kind": "text"},
                },
            ],
        },
    ),
    (
        "field_set",
        "Film details",
        {
            "section": "Film details",
            "properties": [
                {
                    "title": "Director",
                    "type": "string",
                    "x-menagerist": {"kind": "text"},
                },
                {"title": "Runtime", **_QUANTITY, "x-menagerist": {"kind": "quantity"}},
            ],
        },
    ),
    (
        "field_set",
        "Book details",
        {
            "section": "Book details",
            "properties": [
                {"title": "Author", "type": "string", "x-menagerist": {"kind": "text"}},
                {
                    "title": "Pages",
                    "type": "number",
                    "x-menagerist": {"kind": "number"},
                },
            ],
        },
    ),
    (
        "field_set",
        "Vinyl details",
        {
            "section": "Vinyl details",
            "properties": [
                {"title": "Artist", "type": "string", "x-menagerist": {"kind": "text"}},
                {"title": "Label", "type": "string", "x-menagerist": {"kind": "text"}},
                {
                    "title": "Catalogue number",
                    "type": "string",
                    "x-menagerist": {"kind": "text"},
                },
                {
                    "title": "Format",
                    "type": "string",
                    "enum": _FORMATS,
                    "x-menagerist": {"kind": "choice", "display": "radio"},
                },
            ],
        },
    ),
    (
        "field_set",
        "Review",
        {
            "section": "Review",
            "properties": [
                {
                    "title": "Rating",
                    "type": "number",
                    "minimum": 1,
                    "maximum": 5,
                    "multipleOf": 1,
                    "x-menagerist": {"kind": "rating"},
                },
                {
                    "title": "Review",
                    "type": "string",
                    "x-menagerist": {"kind": "longtext"},
                },
            ],
        },
    ),
    (
        "field_set",
        "Recipe",
        {
            "section": "Recipe",
            "properties": [
                {
                    "title": "Serves",
                    "type": "number",
                    "x-menagerist": {"kind": "number"},
                },
                {
                    "title": "Prep time",
                    **_QUANTITY,
                    "x-menagerist": {"kind": "quantity"},
                },
                _INGREDIENTS,
                {
                    "title": "Instructions",
                    "type": "array",
                    "items": {"type": "string"},
                    "x-menagerist": {"kind": "list", "display": "numbered"},
                },
            ],
        },
    ),
]

_presets = sa.table(
    "presets",
    sa.column("id", sa.Uuid()),
    sa.column("kind", sa.String()),
    sa.column("label", sa.String()),
    sa.column("definition", postgresql.JSONB()),
    sa.column("version", sa.Integer()),
    sa.column("builtin", sa.Boolean()),
    sa.column("created_at", sa.DateTime(timezone=True)),
    sa.column("updated_at", sa.DateTime(timezone=True)),
)


def _builtin_lists() -> list[tuple[str, str, dict[str, Any]]]:
    """Return the built-in choice lists as (kind, label, definition) triples."""
    with shared_data_path(_ISO_DATA).open(encoding="utf-8") as f:
        countries = json.load(f)["countries"]
    return [
        ("choice_list", "Condition grades", {"options": list(_GRADES)}),
        ("choice_list", "Countries", {"options": [c["name"] for c in countries]}),
    ]


def _id(kind: str, label: str) -> uuid.UUID:
    if kind == "choice_list":
        return uuid.uuid5(_NAMESPACE, f"builtin:{label}")
    return uuid.uuid5(_NAMESPACE, f"builtin:{kind}:{label}")


def _all() -> list[tuple[str, str, dict[str, Any]]]:
    return _builtin_lists() + _BUILTIN_FIELDS


def upgrade() -> None:
    now = datetime.now(UTC)
    rows = [
        {
            "id": _id(kind, label),
            "kind": kind,
            "label": label,
            "definition": definition,
            "version": 1,
            "builtin": True,
            "created_at": now,
            "updated_at": now,
        }
        for kind, label, definition in _all()
    ]
    stmt = postgresql.insert(_presets).values(rows)
    op.get_bind().execute(stmt.on_conflict_do_nothing(index_elements=["id"]))


def downgrade() -> None:
    ids = [_id(kind, label) for kind, label, _ in _all()]
    op.get_bind().execute(_presets.delete().where(_presets.c.id.in_(ids)))
