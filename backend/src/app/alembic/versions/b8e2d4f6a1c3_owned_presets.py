"""owned_presets

Gives presets (choice lists, fields and field groups) an owner and drops
`builtin`. Presets were shared by everyone, so a preset that several people use
becomes one copy per person, and every link to it is repointed at its user's
copy: types' and items' schemas, other presets' definitions and example
installation records. A built-in nobody uses is deleted (the catalogue offers it
again), and a used one is copied for each person who uses it, so a fresh install
ends with no presets although the seed revision still runs. Any other preset
nobody uses goes to the earliest administrator, or stays ownerless until the
first administrator claims existing data.

Revision ID: b8e2d4f6a1c3
Revises: a7b3c2d1e4f5
Create Date: 2026-11-13 10:00:00.000000

"""

import hashlib
import json
import uuid
from collections.abc import Callable, Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "b8e2d4f6a1c3"
down_revision: str | None = "a7b3c2d1e4f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Owners that predate accounts: the first-admin claim gives their content to the
# first administrator, so here they all count as that person. The system actor's
# id is uuid(int=0), written out so the migration needs no app code.
_LEGACY_OWNERS = frozenset({None, uuid.UUID(int=0)})

# (table, column) for content whose schema names a list by preset id.
_SCHEMAS = (
    ("node_types", "attributes_schema"),
    ("edge_types", "attributes_schema"),
    ("nodes", "extra_schema"),
)

type Owner = uuid.UUID | None


def _first_admin(conn: sa.Connection) -> Owner:
    """The earliest-created administrator, or `None` before accounts exist."""
    return conn.execute(
        sa.text(
            "SELECT id FROM users WHERE role = 'admin' ORDER BY created_at, id LIMIT 1"
        )
    ).scalar_one_or_none()


def _as_id(value: object) -> uuid.UUID | None:
    if not isinstance(value, str):
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


def _list_refs(schema: object) -> set[uuid.UUID]:
    """Preset ids named by `x-menagerist.list` anywhere in `schema`."""
    found: set[uuid.UUID] = set()
    if isinstance(schema, list):
        for child in schema:
            found |= _list_refs(child)
    elif isinstance(schema, dict):
        for child in schema.values():
            found |= _list_refs(child)
        metadata = schema.get("x-menagerist")
        if isinstance(metadata, dict) and (ref := _as_id(metadata.get("list"))):
            found.add(ref)
    return found


def _rewrite(schema: object, target: Callable[[uuid.UUID], uuid.UUID]) -> object:
    """Return `schema` with each `x-menagerist.list` id replaced by `target(id)`.

    A field's `x-menagerist.origin.preset` (the preset it was copied from, which
    "Update options" reads) moves with it.
    """
    if isinstance(schema, list):
        return [_rewrite(child, target) for child in schema]
    if not isinstance(schema, dict):
        return schema
    result = {key: _rewrite(child, target) for key, child in schema.items()}
    metadata = result.get("x-menagerist")
    if isinstance(metadata, dict) and (ref := _as_id(metadata.get("list"))):
        metadata["list"] = str(target(ref))
    origin = metadata.get("origin") if isinstance(metadata, dict) else None
    if isinstance(origin, dict) and (source := _as_id(origin.get("preset"))):
        origin["preset"] = str(target(source))
    return result


def _schema_rows(
    conn: sa.Connection, table: str, column: str
) -> list[tuple[uuid.UUID, Owner, object]]:
    """Every row of `table` with a `column`, as `(id, owner, value)`."""
    rows = conn.execute(
        sa.text(
            f"""SELECT id, owner_id, {column} FROM {table}
            WHERE {column} IS NOT NULL"""
        )
    )
    return [(row[0], row[1], row[2]) for row in rows]


def _preset_records(entities: list[dict[str, str]] | None) -> list[dict[str, str]]:
    """The records of an installation that name a preset by a valid id."""
    return [
        record
        for record in entities or []
        if record.get("kind") == "preset" and _as_id(record.get("entity_id"))
    ]


class _Plan:
    """Who uses each preset, and where each one went for each owner."""

    def __init__(self, conn: sa.Connection) -> None:
        self.admin = _first_admin(conn)
        rows = conn.execute(sa.text("SELECT id, builtin FROM presets"))
        self.builtin: dict[uuid.UUID, bool] = {row.id: row.builtin for row in rows}
        # preset id -> the presets whose definitions name it
        self.named_by: dict[uuid.UUID, set[uuid.UUID]] = {}
        for preset_id, _owner, definition in _schema_rows(
            conn, "presets", "definition"
        ):
            for ref in _list_refs(definition):
                self.named_by.setdefault(ref, set()).add(preset_id)
        self.direct: dict[uuid.UUID, set[Owner]] = {}
        for table, column in _SCHEMAS:
            for _id, owner, schema in _schema_rows(conn, table, column):
                for ref in _list_refs(schema):
                    self._use(ref, owner)
        self._use_installations(conn)
        self.placed: dict[uuid.UUID, dict[Owner, uuid.UUID]] = {}
        self._owners: dict[uuid.UUID, set[Owner]] = {}
        self._visiting: set[uuid.UUID] = set()

    def _use_installations(self, conn: sa.Connection) -> None:
        rows = conn.execute(
            sa.text("SELECT owner_id, entities FROM example_installations")
        )
        for owner, entities in rows:
            for record in _preset_records(entities):
                self._use(uuid.UUID(record["entity_id"]), owner)

    def fold(self, owner: Owner) -> Owner:
        """Content nobody has claimed yet will go to the first administrator."""
        return self.admin if owner in _LEGACY_OWNERS else owner

    def _use(self, preset_id: uuid.UUID, owner: Owner) -> None:
        self.direct.setdefault(preset_id, set()).add(self.fold(owner))

    def owners(self, preset_id: uuid.UUID) -> set[Owner]:
        """Everyone who needs a copy of `preset_id`; empty means delete it.

        A preset named by another preset is needed by whoever keeps that one.
        """
        if preset_id in self._owners:
            return self._owners[preset_id]
        if preset_id in self._visiting:
            return set()
        self._visiting.add(preset_id)
        found = set(self.direct.get(preset_id, set()))
        for referrer in self.named_by.get(preset_id, set()):
            found |= self.owners(referrer)
        if not found and not self.builtin[preset_id]:
            found = {self.admin}
        self._visiting.discard(preset_id)
        self._owners[preset_id] = found
        return found

    def target(self, owner: Owner) -> Callable[[uuid.UUID], uuid.UUID]:
        """Map a preset id to `owner`'s copy of it; unknown ids are kept."""
        owner = self.fold(owner)
        return lambda ref: self.placed.get(ref, {}).get(owner, ref)


def _copy_preset(
    conn: sa.Connection, columns: list[str], source: uuid.UUID, owner: Owner
) -> uuid.UUID:
    """Insert a copy of the preset `source` for `owner` and return its new id."""
    new_id = uuid.uuid7()
    names = ", ".join(columns)
    conn.execute(
        sa.text(
            f"""INSERT INTO presets (id, owner_id, {names})
            SELECT :new_id, :owner, {names} FROM presets WHERE id = :source"""
        ),
        {"new_id": new_id, "owner": owner, "source": source},
    )
    return new_id


def _assign_owners(conn: sa.Connection) -> _Plan:
    """Give every preset its owners, copying it per extra owner."""
    plan = _Plan(conn)
    columns = [
        c["name"]
        for c in sa.inspect(conn).get_columns("presets")
        if c["name"] not in {"id", "owner_id"}
    ]
    for preset_id in sorted(plan.builtin):
        ordered = sorted(plan.owners(preset_id), key=lambda o: (o is None, str(o)))
        if plan.builtin[preset_id]:
            # Built-ins have the same fixed id on every instance, so nobody
            # keeps the original: each user gets a fresh copy.
            plan.placed[preset_id] = {
                owner: _copy_preset(conn, columns, preset_id, owner)
                for owner in ordered
            }
            continue
        keeper, *others = ordered
        conn.execute(
            sa.text("UPDATE presets SET owner_id = :owner WHERE id = :id"),
            {"owner": keeper, "id": preset_id},
        )
        plan.placed[preset_id] = {keeper: preset_id} | {
            owner: _copy_preset(conn, columns, preset_id, owner) for owner in others
        }
    originals = [p for p, builtin in plan.builtin.items() if builtin]
    if originals:
        conn.execute(
            sa.text("DELETE FROM presets WHERE id IN :ids").bindparams(
                sa.bindparam("ids", expanding=True)
            ),
            {"ids": originals},
        )
    return plan


_JSON_VALUE = sa.bindparam("value", type_=JSONB)


def _repoint_schemas(conn: sa.Connection, plan: _Plan) -> None:
    """Point every schema's list ids at its owner's copy."""
    for table, column in (*_SCHEMAS, ("presets", "definition")):
        for row_id, owner, schema in _schema_rows(conn, table, column):
            rewritten = _rewrite(schema, plan.target(owner))
            if rewritten != schema:
                conn.execute(
                    sa.text(
                        f"UPDATE {table} SET {column} = :value WHERE id = :id"
                    ).bindparams(_JSON_VALUE),
                    {"value": rewritten, "id": row_id},
                )


# Entity kinds whose installation record hashes content that holds list ids, with
# the table they live in.
_HASHED_KINDS = {
    "item_type": "node_types",
    "relationship_type": "edge_types",
    "item": "nodes",
}


def _content_hash(content: dict[str, Any]) -> str:
    """Same formula as `app.modules.examples.application.content_hash`."""
    canonical = json.dumps(
        content, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _entity_hashes(conn: sa.Connection) -> dict[uuid.UUID, str]:
    """Hash every type and item as the example installer records it.

    The content dicts mirror `_node_type_content`, `_edge_type_content` and
    `_node_content` in `entrypoints/api/shared/bridges/transfer_targets.py`.
    """
    hashes: dict[uuid.UUID, str] = {}
    for row in conn.execute(
        sa.text(
            """SELECT id, slug, label, description, attributes_schema, icon, colour
            FROM node_types"""
        )
    ):
        content: dict[str, Any] = {
            "slug": row.slug,
            "label": row.label,
            "description": row.description,
            "attributes_schema": row.attributes_schema,
        }
        # Only when set, as the installer does.
        if row.icon is not None:
            content["icon"] = row.icon
        if row.colour is not None:
            content["colour"] = row.colour
        hashes[row.id] = _content_hash(content)
    for row in conn.execute(
        sa.text(
            """SELECT id, slug, label, reverse_label, description, directional,
            attributes_schema FROM edge_types"""
        )
    ):
        hashes[row.id] = _content_hash(
            {
                "slug": row.slug,
                "label": row.label,
                "reverse_label": row.reverse_label,
                "description": row.description,
                "directional": row.directional,
                "attributes_schema": row.attributes_schema,
            }
        )
    for row in conn.execute(
        sa.text(
            """SELECT id, name, type, description, attributes, tags, extra_schema
            FROM nodes"""
        )
    ):
        hashes[row.id] = _content_hash(
            {
                "name": row.name,
                "type": row.type,
                "description": row.description,
                "attributes": row.attributes,
                "tags": list(row.tags),
                "extra_schema": row.extra_schema,
            }
        )
    return hashes


def _rehash_installations(conn: sa.Connection, before: dict[uuid.UUID, str]) -> None:
    """Keep unedited types and items matching the hash their record stored.

    Repointing list ids changed their content. A record whose hash matched the
    content beforehand still matches afterwards; an edited one is left alone.
    """
    after = _entity_hashes(conn)
    rows = conn.execute(sa.text("SELECT id, entities FROM example_installations")).all()
    for row_id, entities in rows:
        changed = False
        for record in entities or []:
            entity_id = _as_id(record.get("entity_id"))
            if (
                record.get("kind") in _HASHED_KINDS
                and entity_id in before
                and record.get("content_hash") == before[entity_id]
                and after[entity_id] != before[entity_id]
            ):
                record["content_hash"] = after[entity_id]
                changed = True
        if changed:
            conn.execute(
                sa.text(
                    "UPDATE example_installations SET entities = :value WHERE id = :id"
                ).bindparams(_JSON_VALUE),
                {"value": entities, "id": row_id},
            )


def _repoint_installations(conn: sa.Connection, plan: _Plan) -> None:
    """Point each installation's preset records at its owner's copy."""
    rows = conn.execute(
        sa.text("SELECT id, owner_id, entities FROM example_installations")
    ).all()
    for row_id, owner, entities in rows:
        target = plan.target(owner)
        records = _preset_records(entities)
        for record in records:
            record["entity_id"] = str(target(uuid.UUID(record["entity_id"])))
        if records:
            conn.execute(
                sa.text(
                    "UPDATE example_installations SET entities = :value WHERE id = :id"
                ).bindparams(_JSON_VALUE),
                {"value": entities, "id": row_id},
            )


def upgrade() -> None:
    """Add `owner_id`, split shared presets per owner and drop `builtin`."""
    conn = op.get_bind()
    op.add_column("presets", sa.Column("owner_id", sa.Uuid(), nullable=True))
    plan = _assign_owners(conn)
    hashes_before = _entity_hashes(conn)
    _repoint_schemas(conn, plan)
    _rehash_installations(conn, hashes_before)
    _repoint_installations(conn, plan)
    op.drop_column("presets", "builtin")
    op.create_index("ix_presets_owner_id_id", "presets", ["owner_id", "id"])


def downgrade() -> None:
    """Drop the owner and restore `builtin` as false everywhere.

    Lossy: per-person copies stay as separate presets, and former built-ins are
    not restored.
    """
    op.drop_index("ix_presets_owner_id_id", table_name="presets")
    op.drop_column("presets", "owner_id")
    op.add_column(
        "presets",
        sa.Column("builtin", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
