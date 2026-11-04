import uuid
from typing import TYPE_CHECKING

import pytest
import sqlalchemy
from pytest_alembic.tests import (
    test_model_definitions_match_ddl,  # noqa: F401
    test_single_head_revision,  # noqa: F401
    test_up_down_consistency,  # noqa: F401
    test_upgrade,  # noqa: F401
)

from app.platform.alembic_runner import build_config

if TYPE_CHECKING:
    from collections.abc import Iterator

    from alembic.config import Config
    from pytest_alembic.runner import MigrationContext

pytestmark = pytest.mark.integration


@pytest.fixture
def alembic_config(postgres_url: str) -> Config:
    """Alembic config pointed at the same migrated testcontainers database."""
    del postgres_url  # ordering dependency only - ensures DATABASE_URL is set first
    return build_config()


@pytest.fixture
def alembic_engine(postgres_sync_url: str) -> Iterator[sqlalchemy.Engine]:
    """A sync engine over the testcontainers database - pytest-alembic runs sync."""
    engine = sqlalchemy.create_engine(postgres_sync_url)
    try:
        yield engine
    finally:
        engine.dispose()


_BEFORE_FAVOURITES = "e6f7a8b9c0d1"
_ALICE = uuid.UUID(int=301)
_BOB = uuid.UUID(int=302)


def test_favourites_move_to_their_owner_and_back(
    alembic_runner: MigrationContext, alembic_engine: sqlalchemy.Engine
) -> None:
    """Upgrading gives a flagged item's star to its owner; downgrading undoes it."""
    starred, plain, ownerless = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    insert = sqlalchemy.text(
        """
        INSERT INTO nodes (id, owner_id, name, attributes, favourite, tags,
                           created_at, updated_at)
        VALUES (:id, :owner, :name, '{}', :favourite, '[]', now(), now())
        """
    )
    alembic_runner.migrate_down_to(_BEFORE_FAVOURITES)
    try:
        with alembic_engine.begin() as connection:
            for node_id, owner, favourite in (
                (starred, _ALICE, True),
                (plain, _BOB, False),
                (ownerless, None, True),
            ):
                connection.execute(
                    insert,
                    {
                        "id": node_id,
                        "owner": owner,
                        "name": str(node_id),
                        "favourite": favourite,
                    },
                )

        alembic_runner.migrate_up_one()

        with alembic_engine.connect() as connection:
            rows = connection.execute(
                sqlalchemy.text("SELECT user_id, node_id FROM node_favourites")
            ).all()
            columns = {
                column["name"]
                for column in sqlalchemy.inspect(connection).get_columns("nodes")
            }
        assert [(row.user_id, row.node_id) for row in rows] == [(_ALICE, starred)]
        assert "favourite" not in columns

        alembic_runner.migrate_down_one()

        with alembic_engine.connect() as connection:
            flags = {
                row.id: row.favourite
                for row in connection.execute(
                    sqlalchemy.text("SELECT id, favourite FROM nodes")
                )
            }
        assert flags == {starred: True, plain: False, ownerless: False}
    finally:
        alembic_runner.migrate_down_to(_BEFORE_FAVOURITES)
        with alembic_engine.begin() as connection:
            connection.execute(sqlalchemy.text("DELETE FROM nodes"))
        alembic_runner.migrate_up_to("heads")
