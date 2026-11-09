import json
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.platform import alembic_runner
from app.platform.config import get_database_settings

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy import Connection
    from testcontainers.postgres import PostgresContainer

pytestmark = pytest.mark.integration

BEFORE = "d4a1b6c8e3f2"
AFTER = "f1a2b3c4d5e6"
NOW = datetime(2026, 11, 9, tzinfo=UTC)
ADMIN = uuid.UUID(int=1)
BOB = uuid.UUID(int=2)
CAROL = uuid.UUID(int=3)
SYSTEM = uuid.UUID(int=0)


@pytest.fixture
def old_schema(
    postgres_container: PostgresContainer, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Connection]:
    """A scratch database upgraded to the revision before ownership."""
    sync_url = make_url(postgres_container.get_connection_url(driver="psycopg"))
    name = f"owned_types_{uuid.uuid4().hex[:8]}"
    admin_engine = create_engine(sync_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    async_url = make_url(postgres_container.get_connection_url(driver="asyncpg")).set(
        database=name
    )
    monkeypatch.setenv("MENAGERIST_DATABASE_URL", async_url.render_as_string(False))
    get_database_settings.cache_clear()
    alembic_runner.upgrade(BEFORE)
    engine = create_engine(sync_url.set(database=name))
    with engine.connect() as conn:
        yield conn
    engine.dispose()
    get_database_settings.cache_clear()
    with admin_engine.connect() as conn:
        conn.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
    admin_engine.dispose()


def _user(conn: Connection, user_id: uuid.UUID, name: str, role: str) -> None:
    conn.execute(
        text(
            """INSERT INTO users (id, username, display_name, password_hash, role,
            password_expired, disabled, created_at, updated_at) VALUES (:id, :n,
            :n, 'x', :role, false, false, :now, :now)"""
        ),
        {"id": user_id, "n": name, "role": role, "now": NOW},
    )


def _type(conn: Connection, table: str, slug: str) -> uuid.UUID:
    type_id = uuid.uuid7()
    conn.execute(
        text(
            f"""INSERT INTO {table} (id, slug, label, created_at, updated_at) VALUES
            (:id, :slug, :slug, :now, :now)"""
        ),
        {"id": type_id, "slug": slug, "now": NOW},
    )
    return type_id


def _item(conn: Connection, owner: uuid.UUID | None, type_slug: str) -> None:
    conn.execute(
        text(
            """INSERT INTO nodes (id, owner_id, name, type, attributes, tags,
            created_at, updated_at) VALUES (:id, :owner, 'n', :t, '{}', '{}',
            :now, :now)"""
        ),
        {"id": uuid.uuid7(), "owner": owner, "t": type_slug, "now": NOW},
    )


def _installation(
    conn: Connection, owner: uuid.UUID, pack: str, type_id: uuid.UUID
) -> uuid.UUID:
    row_id = uuid.uuid7()
    entities = [
        {
            "kind": "item_type",
            "ref": "book",
            "label": "Book",
            "entity_id": str(type_id),
            "outcome": "owned",
        }
    ]
    conn.execute(
        text(
            """INSERT INTO example_installations (id, owner_id, pack_id, status,
            entities, created_at, updated_at) VALUES (:id, :owner, :pack,
            'installed', CAST(:e AS jsonb), :now, :now)"""
        ),
        {
            "id": row_id,
            "owner": owner,
            "pack": pack,
            "e": json.dumps(entities),
            "now": NOW,
        },
    )
    return row_id


def _owners(conn: Connection, table: str, slug: str) -> set[uuid.UUID | None]:
    rows = conn.execute(
        text(f"SELECT owner_id FROM {table} WHERE slug = :s"),
        {"s": slug},
    )
    return {owner for (owner,) in rows}


def test_a_type_used_by_several_people_becomes_one_copy_each(
    old_schema: Connection,
) -> None:
    """Alice and Bob both use `book`; Carol only installed a pack that names it."""
    conn = old_schema
    _user(conn, ADMIN, "alice", "admin")
    _user(conn, BOB, "bob", "member")
    _user(conn, CAROL, "carol", "member")
    book = _type(conn, "node_types", "book")
    _type(conn, "node_types", "unused")
    _item(conn, ADMIN, "book")
    _item(conn, BOB, "book")
    _item(conn, None, "book")
    bobs_pack = _installation(conn, BOB, "demo", book)
    carols_pack = _installation(conn, CAROL, "demo", book)
    conn.commit()

    alembic_runner.upgrade(AFTER)

    with conn.engine.connect() as after:
        assert _owners(after, "node_types", "book") == {ADMIN, BOB, CAROL}
        assert _owners(after, "node_types", "unused") == {ADMIN}
        for pack, owner in ((bobs_pack, BOB), (carols_pack, CAROL)):
            entities = after.execute(
                text("SELECT entities FROM example_installations WHERE id = :i"),
                {"i": pack},
            ).scalar_one()
            owned = after.execute(
                text("SELECT id FROM node_types WHERE slug = 'book' AND owner_id = :o"),
                {"o": owner},
            ).scalar_one()
            assert entities[0]["entity_id"] == str(owned)


def _insert_edge_type(conn: Connection, owner: uuid.UUID) -> None:
    columns = "id, owner_id, slug, label, directional, created_at, updated_at"
    values = ":id, :o, 'by', 'By', true, :now, :now"
    conn.execute(
        text(f"INSERT INTO edge_types ({columns}) VALUES ({values})"),
        {"id": uuid.uuid7(), "o": owner, "now": NOW},
    )


def test_a_slug_is_unique_per_owner_among_live_types(old_schema: Connection) -> None:
    """Two people may share a slug; one person may not hold it twice live."""
    conn = old_schema
    _user(conn, ADMIN, "alice", "admin")
    conn.commit()
    alembic_runner.upgrade(AFTER)

    with conn.engine.begin() as after:
        for owner in (ADMIN, BOB):
            _insert_edge_type(after, owner)
    with (
        pytest.raises(Exception, match="uq_edge_types_owner_slug_live"),
        conn.engine.begin() as after,
    ):
        _insert_edge_type(after, ADMIN)


def test_system_owned_and_ownerless_items_share_one_type_before_any_account(
    old_schema: Connection,
) -> None:
    """With no accounts yet, legacy owners must not split a type in two."""
    conn = old_schema
    _type(conn, "node_types", "book")
    _item(conn, SYSTEM, "book")
    _item(conn, None, "book")
    conn.commit()

    alembic_runner.upgrade(AFTER)

    with conn.engine.connect() as after:
        assert _owners(after, "node_types", "book") == {None}


def test_legacy_owners_fold_into_the_first_admin(old_schema: Connection) -> None:
    """System-owned and ownerless items count as the admin's, who gets one copy."""
    conn = old_schema
    _user(conn, ADMIN, "alice", "admin")
    _user(conn, BOB, "bob", "member")
    _type(conn, "node_types", "book")
    _type(conn, "node_types", "gone")
    conn.execute(
        text("UPDATE node_types SET deleted_at = :now WHERE slug = 'gone'"),
        {"now": NOW},
    )
    _item(conn, SYSTEM, "book")
    _item(conn, None, "book")
    _item(conn, BOB, "book")
    conn.commit()

    alembic_runner.upgrade(AFTER)

    with conn.engine.connect() as after:
        assert _owners(after, "node_types", "book") == {ADMIN, BOB}
        live = after.execute(
            text("SELECT count(*) FROM node_types WHERE slug = 'book'")
        ).scalar_one()
        assert live == 2
        # A deleted type nobody uses still gets an owner.
        assert _owners(after, "node_types", "gone") == {ADMIN}
