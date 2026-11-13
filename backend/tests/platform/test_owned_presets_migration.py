import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from app.modules.examples.application.content_hash import content_hash
from app.platform import alembic_runner
from app.platform.config import get_database_settings

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy import Connection
    from testcontainers.postgres import PostgresContainer

pytestmark = pytest.mark.integration

BEFORE = "a7b3c2d1e4f5"
AFTER = "b8e2d4f6a1c3"
NOW = datetime(2026, 11, 13, tzinfo=UTC)
ALICE = uuid.UUID(int=1)
BOB = uuid.UUID(int=2)
CAROL = uuid.UUID(int=3)
DAVE = uuid.UUID(int=4)
SYSTEM = uuid.UUID(int=0)


@pytest.fixture
def old_schema(
    postgres_container: PostgresContainer, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Connection]:
    """A scratch database upgraded to the revision before preset ownership."""
    sync_url = make_url(postgres_container.get_connection_url(driver="psycopg"))
    name = f"owned_presets_{uuid.uuid4().hex[:8]}"
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
        # The seeded built-ins are covered by their own test; start the rest clean.
        conn.execute(text("DELETE FROM presets"))
        conn.commit()
        yield conn
    engine.dispose()
    get_database_settings.cache_clear()
    with admin_engine.connect() as conn:
        conn.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
    admin_engine.dispose()


def _user(
    conn: Connection,
    user_id: uuid.UUID,
    name: str,
    role: str,
    created_at: datetime = NOW,
) -> None:
    conn.execute(
        text(
            """INSERT INTO users (id, username, display_name, password_hash, role,
            password_expired, disabled, created_at, updated_at) VALUES (:id, :n,
            :n, 'x', :role, false, false, :at, :at)"""
        ),
        {"id": user_id, "n": name, "role": role, "at": created_at},
    )


def _schema(list_id: uuid.UUID) -> dict[str, Any]:
    """An attribute schema with one choice field drawing on the list `list_id`."""
    return {
        "type": "object",
        "properties": {
            "grade": {
                "title": "Grade",
                "type": "string",
                "x-menagerist": {"kind": "choice", "list": str(list_id)},
            }
        },
    }


def _list_ids(schema: object) -> list[str]:
    """Every `x-menagerist.list` id named anywhere in `schema`."""
    if isinstance(schema, list):
        return [found for child in schema for found in _list_ids(child)]
    if not isinstance(schema, dict):
        return []
    found = [f for child in schema.values() for f in _list_ids(child)]
    metadata = schema.get("x-menagerist")
    if isinstance(metadata, dict) and isinstance(metadata.get("list"), str):
        found.append(metadata["list"])
    return found


def _preset(
    conn: Connection,
    label: str,
    *,
    kind: str = "list",
    builtin: bool = False,
    definition: dict[str, Any] | None = None,
) -> uuid.UUID:
    preset_id = uuid.uuid7()
    conn.execute(
        text(
            """INSERT INTO presets (id, kind, label, definition, version, builtin,
            created_at, updated_at) VALUES (:id, :kind, :label, CAST(:d AS jsonb),
            1, :builtin, :now, :now)"""
        ),
        {
            "id": preset_id,
            "kind": kind,
            "label": label,
            "d": json.dumps(definition or {"options": ["A", "B"]}),
            "builtin": builtin,
            "now": NOW,
        },
    )
    return preset_id


def _type(
    conn: Connection,
    table: str,
    owner: uuid.UUID | None,
    slug: str,
    schema: dict[str, Any],
) -> uuid.UUID:
    type_id = uuid.uuid7()
    extra = ", directional" if table == "edge_types" else ""
    value = ", true" if table == "edge_types" else ""
    conn.execute(
        text(
            f"""INSERT INTO {table} (id, owner_id, slug, label, attributes_schema,
            created_at, updated_at{extra}) VALUES (:id, :owner, :slug, :slug,
            CAST(:s AS jsonb), :now, :now{value})"""
        ),
        {
            "id": type_id,
            "owner": owner,
            "slug": slug,
            "s": json.dumps(schema),
            "now": NOW,
        },
    )
    return type_id


def _item(
    conn: Connection, owner: uuid.UUID | None, schema: dict[str, Any] | None = None
) -> uuid.UUID:
    item_id = uuid.uuid7()
    conn.execute(
        text(
            """INSERT INTO nodes (id, owner_id, name, attributes, tags, extra_schema,
            created_at, updated_at) VALUES (:id, :owner, 'n', '{}', '[]',
            CAST(:s AS jsonb), :now, :now)"""
        ),
        {
            "id": item_id,
            "owner": owner,
            "s": None if schema is None else json.dumps(schema),
            "now": NOW,
        },
    )
    return item_id


def _installation(
    conn: Connection, owner: uuid.UUID | None, pack: str, preset_id: uuid.UUID
) -> uuid.UUID:
    row_id = uuid.uuid7()
    entities = [
        {
            "kind": "preset",
            "ref": "grades",
            "label": "Grades",
            "entity_id": str(preset_id),
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


def _copies(conn: Connection, label: str) -> dict[uuid.UUID | None, uuid.UUID]:
    """The presets labelled `label`, as `owner -> id`; fails on two per owner."""
    rows = conn.execute(
        text("SELECT owner_id, id FROM presets WHERE label = :l"), {"l": label}
    ).all()
    copies = {row.owner_id: row.id for row in rows}
    assert len(copies) == len(rows)
    return copies


def _json(conn: Connection, sql: str, row_id: uuid.UUID) -> object:
    return conn.execute(text(sql), {"id": row_id}).scalar_one()


def _installed_id(conn: Connection, pack: uuid.UUID) -> str:
    """The preset id the installation `pack` records."""
    sql = "SELECT entities->0->>'entity_id' FROM example_installations WHERE id = :id"
    return str(conn.execute(text(sql), {"id": pack}).scalar_one())


def test_a_list_used_by_two_people_becomes_one_copy_each(
    old_schema: Connection,
) -> None:
    """Each person's types, items and field groups point at their own copy."""
    conn = old_schema
    _user(conn, ALICE, "alice", "admin")
    _user(conn, BOB, "bob", "member")
    grades = _preset(conn, "Grades")
    group = _preset(
        conn,
        "Condition group",
        kind="field_group",
        definition={"properties": _schema(grades)["properties"]},
    )
    alices_type = _type(conn, "node_types", ALICE, "record", _schema(grades))
    bobs_type = _type(conn, "edge_types", BOB, "graded", _schema(grades))
    alices_item = _item(conn, ALICE, _schema(grades))
    bobs_item = _item(conn, BOB, _schema(grades))
    _installation(conn, ALICE, "demo", group)
    bobs_pack = _installation(conn, BOB, "demo", group)
    conn.commit()

    alembic_runner.upgrade(AFTER)

    with conn.engine.connect() as after:
        lists = _copies(after, "Grades")
        groups = _copies(after, "Condition group")
        assert set(lists) == {ALICE, BOB}
        assert set(groups) == {ALICE, BOB}
        for owner, sql, row_id in (
            (
                ALICE,
                "SELECT attributes_schema FROM node_types WHERE id = :id",
                alices_type,
            ),
            (BOB, "SELECT attributes_schema FROM edge_types WHERE id = :id", bobs_type),
            (ALICE, "SELECT extra_schema FROM nodes WHERE id = :id", alices_item),
            (BOB, "SELECT extra_schema FROM nodes WHERE id = :id", bobs_item),
            (ALICE, "SELECT definition FROM presets WHERE id = :id", groups[ALICE]),
            (BOB, "SELECT definition FROM presets WHERE id = :id", groups[BOB]),
        ):
            assert _list_ids(_json(after, sql, row_id)) == [str(lists[owner])]
        assert _installed_id(after, bobs_pack) == str(groups[BOB])


def test_a_builtin_nothing_references_is_deleted(old_schema: Connection) -> None:
    """Built-ins return through the catalogue, so unused ones are not kept."""
    conn = old_schema
    _user(conn, ALICE, "alice", "admin")
    _preset(conn, "Old grades", builtin=True)
    # A built-in named only by another unused built-in is unused too.
    formats = _preset(conn, "Formats", builtin=True)
    _preset(
        conn,
        "Format field",
        kind="field",
        builtin=True,
        definition={"property": _schema(formats)["properties"]["grade"]},
    )
    conn.commit()

    alembic_runner.upgrade(AFTER)

    with conn.engine.connect() as after:
        assert after.execute(text("SELECT count(*) FROM presets")).scalar_one() == 0


def test_a_referenced_builtin_is_copied_per_person_and_the_original_goes(
    old_schema: Connection,
) -> None:
    """Bob's type and a legacy (system-owned) item both name a built-in list."""
    conn = old_schema
    _user(conn, ALICE, "alice", "admin")
    _user(conn, BOB, "bob", "member")
    shared = _preset(conn, "Shared grades", builtin=True)
    bobs_type = _type(conn, "node_types", BOB, "record", _schema(shared))
    legacy_item = _item(conn, SYSTEM, _schema(shared))
    # A field soft-deleted by Carol still counts as a reference.
    _user(conn, CAROL, "carol", "member")
    field = _preset(
        conn,
        "Carol's field",
        kind="field",
        definition={"property": _schema(shared)["properties"]["grade"]},
    )
    conn.execute(
        text("UPDATE presets SET deleted_at = :now WHERE id = :id"),
        {"now": NOW, "id": field},
    )
    _installation(conn, CAROL, "demo", field)
    conn.commit()

    alembic_runner.upgrade(AFTER)

    with conn.engine.connect() as after:
        copies = _copies(after, "Shared grades")
        assert set(copies) == {ALICE, BOB, CAROL}
        assert shared not in copies.values()
        schema = _json(
            after, "SELECT attributes_schema FROM node_types WHERE id = :id", bobs_type
        )
        assert _list_ids(schema) == [str(copies[BOB])]
        schema = _json(
            after, "SELECT extra_schema FROM nodes WHERE id = :id", legacy_item
        )
        assert _list_ids(schema) == [str(copies[ALICE])]
        definition = _json(
            after, "SELECT definition FROM presets WHERE id = :id", field
        )
        assert _list_ids(definition) == [str(copies[CAROL])]


def test_an_unreferenced_preset_goes_to_the_earliest_admin(
    old_schema: Connection,
) -> None:
    """Nobody uses it, so the first administrator gets it."""
    conn = old_schema
    _user(conn, BOB, "bob", "admin", NOW + timedelta(days=1))
    _user(conn, DAVE, "dave", "admin")
    _user(conn, CAROL, "carol", "member", NOW - timedelta(days=1))
    unused = _preset(conn, "Unused")
    conn.commit()

    alembic_runner.upgrade(AFTER)

    with conn.engine.connect() as after:
        assert _copies(after, "Unused") == {DAVE: unused}


def test_presets_stay_ownerless_before_any_admin(old_schema: Connection) -> None:
    """Legacy owners must not split a preset, and nobody can claim it yet."""
    conn = old_schema
    unused = _preset(conn, "Unused")
    used = _preset(conn, "Used built-in", builtin=True)
    _item(conn, SYSTEM, _schema(used))
    _item(conn, None, _schema(used))
    _type(conn, "node_types", None, "record", _schema(used))
    conn.commit()

    alembic_runner.upgrade(AFTER)

    with conn.engine.connect() as after:
        assert _copies(after, "Unused") == {None: unused}
        assert set(_copies(after, "Used built-in")) == {None}


def test_installations_point_at_the_installers_own_copy(
    old_schema: Connection,
) -> None:
    """Bob and Carol both installed a pack that recorded the same preset."""
    conn = old_schema
    _user(conn, ALICE, "alice", "admin")
    _user(conn, BOB, "bob", "member")
    _user(conn, CAROL, "carol", "member")
    grades = _preset(conn, "Grades")
    legacy_pack = _installation(conn, None, "demo", grades)
    bobs_pack = _installation(conn, BOB, "demo", grades)
    carols_pack = _installation(conn, CAROL, "demo", grades)
    conn.commit()

    alembic_runner.upgrade(AFTER)

    with conn.engine.connect() as after:
        copies = _copies(after, "Grades")
        assert set(copies) == {ALICE, BOB, CAROL}
        for pack, owner in (
            (legacy_pack, ALICE),
            (bobs_pack, BOB),
            (carols_pack, CAROL),
        ):
            assert _installed_id(after, pack) == str(copies[owner])


def test_downgrade_restores_builtin_and_drops_the_owner(
    old_schema: Connection,
) -> None:
    """Every preset comes back as an ordinary, non-built-in one."""
    conn = old_schema
    _user(conn, ALICE, "alice", "admin")
    _preset(conn, "Unused")
    conn.commit()
    alembic_runner.upgrade(AFTER)
    with conn.engine.connect() as after:
        columns = {c["name"] for c in inspect(after).get_columns("presets")}
        indexes = {i["name"] for i in inspect(after).get_indexes("presets")}
        assert "owner_id" in columns
        assert "builtin" not in columns
        assert "ix_presets_owner_id_id" in indexes

    alembic_runner.downgrade(BEFORE)

    with conn.engine.connect() as before:
        columns = {c["name"] for c in inspect(before).get_columns("presets")}
        assert "owner_id" not in columns
        rows = before.execute(text("SELECT label, builtin FROM presets")).all()
        assert [tuple(row) for row in rows] == [("Unused", False)]


def test_a_fresh_install_ends_with_no_presets(
    postgres_container: PostgresContainer, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The seed revision still runs, but nothing survives the new one."""
    sync_url = make_url(postgres_container.get_connection_url(driver="psycopg"))
    name = f"fresh_presets_{uuid.uuid4().hex[:8]}"
    admin_engine = create_engine(sync_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    async_url = make_url(postgres_container.get_connection_url(driver="asyncpg")).set(
        database=name
    )
    monkeypatch.setenv("MENAGERIST_DATABASE_URL", async_url.render_as_string(False))
    get_database_settings.cache_clear()
    engine = create_engine(sync_url.set(database=name))
    try:
        alembic_runner.upgrade(BEFORE)
        with engine.connect() as conn:
            seeded = conn.execute(text("SELECT count(*) FROM presets")).scalar_one()
            assert seeded > 0
        alembic_runner.upgrade(AFTER)
        with engine.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM presets")).scalar_one() == 0
    finally:
        engine.dispose()
        get_database_settings.cache_clear()
        with admin_engine.connect() as conn:
            conn.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin_engine.dispose()


def _record(kind: str, entity_id: uuid.UUID, content: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": kind,
        "ref": str(entity_id)[-6:],
        "label": "x",
        "entity_id": str(entity_id),
        "outcome": "owned",
        "content_hash": content_hash(content),
    }


def _pack(
    conn: Connection, owner: uuid.UUID, records: list[dict[str, Any]]
) -> uuid.UUID:
    row_id = uuid.uuid7()
    conn.execute(
        text(
            """INSERT INTO example_installations (id, owner_id, pack_id, status,
            entities, created_at, updated_at) VALUES (:id, :owner, 'demo',
            'installed', CAST(:e AS jsonb), :now, :now)"""
        ),
        {"id": row_id, "owner": owner, "e": json.dumps(records), "now": NOW},
    )
    return row_id


def _type_content(slug: str, schema: dict[str, Any]) -> dict[str, Any]:
    """What the installer hashes for a type made by `_type`."""
    return {
        "slug": slug,
        "label": slug,
        "description": None,
        "attributes_schema": schema,
    }


def _hashes(conn: Connection, pack: uuid.UUID) -> dict[str, str]:
    """The pack's recorded content hashes by ref."""
    entities = _json(
        conn, "SELECT entities FROM example_installations WHERE id = :id", pack
    )
    assert isinstance(entities, list)
    return {record["ref"]: record["content_hash"] for record in entities}


def test_unedited_types_and_items_keep_matching_hashes_after_a_split(
    old_schema: Connection,
) -> None:
    """Whoever got a copy of the list still reads an untouched pack as unedited."""
    conn = old_schema
    _user(conn, ALICE, "alice", "admin")
    _user(conn, BOB, "bob", "member")
    grades = _preset(conn, "Grades")
    schema = _schema(grades)
    alices_type = _type(conn, "node_types", ALICE, "record", schema)
    bobs_type = _type(conn, "node_types", BOB, "record", schema)
    bobs_edge = _type(conn, "edge_types", BOB, "graded", schema)
    bobs_item = _item(conn, BOB, schema)
    bobs_edited = _type(conn, "node_types", BOB, "edited", schema)
    item_content: dict[str, Any] = {
        "name": "n",
        "type": None,
        "description": None,
        "attributes": {},
        "tags": [],
        "extra_schema": schema,
    }
    edge_content: dict[str, Any] = {
        "slug": "graded",
        "label": "graded",
        "reverse_label": None,
        "description": None,
        "directional": True,
        "attributes_schema": schema,
    }
    edited = _record("item_type", bobs_edited, _type_content("edited", schema))
    edited["content_hash"] = "e" * 64  # edited since install: never matched
    alices_pack = _pack(
        conn,
        ALICE,
        [_record("item_type", alices_type, _type_content("record", schema))],
    )
    bobs_pack = _pack(
        conn,
        BOB,
        [
            _record("item_type", bobs_type, _type_content("record", schema)),
            _record("relationship_type", bobs_edge, edge_content),
            _record("item", bobs_item, item_content),
            edited,
        ],
    )
    conn.commit()
    alices_before = _hashes(conn, alices_pack)

    alembic_runner.upgrade(AFTER)

    with conn.engine.connect() as after:
        bobs_list = _copies(after, "Grades")[BOB]
        moved = _schema(bobs_list)
        types = {
            "node_types": ("record", bobs_type, _type_content("record", moved)),
        }
        expected = {
            str(bobs_type)[-6:]: content_hash(types["node_types"][2]),
            str(bobs_edge)[-6:]: content_hash(
                edge_content | {"attributes_schema": moved}
            ),
            str(bobs_item)[-6:]: content_hash(item_content | {"extra_schema": moved}),
            str(bobs_edited)[-6:]: "e" * 64,
        }
        assert _hashes(after, bobs_pack) == expected
        assert _hashes(after, alices_pack) == alices_before


def test_a_copied_field_keeps_pointing_at_the_list_it_came_from(
    old_schema: Connection,
) -> None:
    """`origin.preset` moves to the person's copy, so "Update options" still works."""
    conn = old_schema
    _user(conn, ALICE, "alice", "admin")
    _user(conn, BOB, "bob", "member")
    grades = _preset(conn, "Grades")
    schema = _schema(grades)
    schema["properties"]["grade"]["x-menagerist"]["origin"] = {
        "preset": str(grades),
        "version": 1,
    }
    _type(conn, "node_types", ALICE, "record", schema)
    bobs_type = _type(conn, "node_types", BOB, "record", schema)
    conn.commit()

    alembic_runner.upgrade(AFTER)

    with conn.engine.connect() as after:
        migrated = _json(
            after, "SELECT attributes_schema FROM node_types WHERE id = :id", bobs_type
        )
        assert isinstance(migrated, dict)
        metadata = migrated["properties"]["grade"]["x-menagerist"]
        assert metadata["list"] == str(_copies(after, "Grades")[BOB])
        assert metadata["origin"] == {
            "preset": metadata["list"],
            "version": 1,
        }
