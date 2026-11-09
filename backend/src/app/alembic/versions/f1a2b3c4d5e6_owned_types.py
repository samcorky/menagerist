"""owned_types

Gives item types and relationship types an owner and makes a slug unique per
owner. Types were shared by everyone, so a type that several people's items (or
example installations) use becomes one copy per person: no one is left with a
slug they cannot see. A type nobody uses goes to the earliest administrator, or
stays ownerless until the first administrator claims existing data.

Revision ID: f1a2b3c4d5e6
Revises: d4a1b6c8e3f2
Create Date: 2026-11-09 00:30:00.000000

"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: str | None = "d4a1b6c8e3f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Owners that predate accounts: the first-admin claim gives their content (and so
# their types) to the first administrator, so here they all count as that person.
# The system actor's id is uuid(int=0), written out so the migration needs no app code.
_LEGACY_OWNERS = frozenset({None, uuid.UUID(int=0)})

# (type table, content table that names a type by slug, installation record kind)
_VOCABULARIES = (
    ("node_types", "nodes", "item_type"),
    ("edge_types", "edges", "relationship_type"),
)


def _first_admin(conn: sa.Connection) -> uuid.UUID | None:
    """The earliest-created administrator, or `None` before accounts exist."""
    return conn.execute(
        sa.text(
            "SELECT id FROM users WHERE role = 'admin' ORDER BY created_at, id LIMIT 1"
        )
    ).scalar_one_or_none()


def _installations_by_type(
    conn: sa.Connection, kind: str
) -> dict[uuid.UUID, list[tuple[uuid.UUID, uuid.UUID | None]]]:
    """Installation rows that record each type, as `type id -> [(row id, owner)]`."""
    found: dict[uuid.UUID, list[tuple[uuid.UUID, uuid.UUID | None]]] = {}
    rows = conn.execute(
        sa.text("SELECT id, owner_id, entities FROM example_installations")
    )
    for row_id, owner_id, entities in rows:
        for record in entities or []:
            if record.get("kind") == kind:
                found.setdefault(uuid.UUID(record["entity_id"]), []).append(
                    (row_id, owner_id)
                )
    return found


def _copy_type(
    conn: sa.Connection,
    table: str,
    columns: list[str],
    source: uuid.UUID,
    owner: uuid.UUID | None,
) -> uuid.UUID:
    """Insert a copy of the type `source` for `owner` and return its new id."""
    new_id = uuid.uuid7()
    names = ", ".join(columns)
    conn.execute(
        sa.text(
            f"""INSERT INTO {table} (id, owner_id, {names})
            SELECT :new_id, :owner, {names} FROM {table} WHERE id = :source"""
        ),
        {"new_id": new_id, "owner": owner, "source": source},
    )
    return new_id


def _repoint_installations(
    conn: sa.Connection,
    kind: str,
    moves: dict[uuid.UUID, dict[uuid.UUID, uuid.UUID]],
) -> None:
    """Point each installation's records at its owner's copy of a type.

    `moves` maps an installation row id to `{old type id: new type id}`.
    """
    for row_id, mapping in moves.items():
        entities = conn.execute(
            sa.text("SELECT entities FROM example_installations WHERE id = :id"),
            {"id": row_id},
        ).scalar_one()
        for record in entities:
            old = uuid.UUID(record["entity_id"])
            if record.get("kind") == kind and old in mapping:
                record["entity_id"] = str(mapping[old])
        conn.execute(
            sa.text(
                "UPDATE example_installations SET entities = :e WHERE id = :id"
            ).bindparams(sa.bindparam("e", type_=JSONB)),
            {"e": entities, "id": row_id},
        )


def _assign_owners(conn: sa.Connection, table: str, content: str, kind: str) -> None:
    """Give every type of `table` an owner, copying it per extra owner."""
    admin = _first_admin(conn)
    columns = [
        c["name"]
        for c in sa.inspect(conn).get_columns(table)
        if c["name"] not in {"id", "owner_id"}
    ]
    installations = _installations_by_type(conn, kind)
    moves: dict[uuid.UUID, dict[uuid.UUID, uuid.UUID]] = {}
    types = conn.execute(sa.text(f"SELECT id, slug FROM {table} ORDER BY id")).all()
    for type_id, slug in types:
        owners = {
            owner
            for (owner,) in conn.execute(
                sa.text(f"SELECT DISTINCT owner_id FROM {content} WHERE type = :slug"),
                {"slug": slug},
            )
        }
        owners |= {owner for _, owner in installations.get(type_id, [])}
        # Content nobody has claimed yet will go to the first administrator.
        owners = {admin if owner in _LEGACY_OWNERS else owner for owner in owners}
        ordered = sorted(owners, key=lambda o: (o is None, str(o)))
        if not ordered:
            ordered = [admin]
        keeper, *others = ordered
        conn.execute(
            sa.text(f"UPDATE {table} SET owner_id = :owner WHERE id = :id"),
            {"owner": keeper, "id": type_id},
        )
        copies = {
            owner: _copy_type(conn, table, columns, type_id, owner) for owner in others
        }
        for row_id, owner in installations.get(type_id, []):
            owner = admin if owner in _LEGACY_OWNERS else owner
            if owner in copies:
                moves.setdefault(row_id, {})[type_id] = copies[owner]
    _repoint_installations(conn, kind, moves)


def upgrade() -> None:
    """Add `owner_id`, split shared types per owner, index slugs per owner."""
    conn = op.get_bind()
    for table, content, kind in _VOCABULARIES:
        op.add_column(table, sa.Column("owner_id", sa.Uuid(), nullable=True))
        op.drop_index(f"uq_{table}_slug_live", table_name=table)
        _assign_owners(conn, table, content, kind)
        op.create_index(
            f"uq_{table}_owner_slug_live",
            table,
            ["owner_id", "slug"],
            unique=True,
            postgresql_where=sa.text("deleted_at IS NULL"),
        )


def downgrade() -> None:
    """Drop the owner and restore instance-wide slugs.

    Lossy where several owners hold a copy of the same slug: the earliest copy
    is kept live and the others are soft-deleted.
    """
    conn = op.get_bind()
    for table, _content, _kind in _VOCABULARIES:
        op.drop_index(f"uq_{table}_owner_slug_live", table_name=table)
        conn.execute(
            sa.text(
                f"""UPDATE {table} SET deleted_at = now() WHERE deleted_at IS NULL
                AND id NOT IN (SELECT DISTINCT ON (slug) id FROM {table}
                WHERE deleted_at IS NULL ORDER BY slug, id)"""
            )
        )
        op.drop_column(table, "owner_id")
        op.create_index(
            f"uq_{table}_slug_live",
            table,
            ["slug"],
            unique=True,
            postgresql_where=sa.text("deleted_at IS NULL"),
        )
