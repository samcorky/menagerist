from typing import TYPE_CHECKING
from uuid import uuid7

import pytest
from sqlalchemy import create_engine, make_url, text

from app.platform import alembic_runner
from app.platform.config import get_database_settings

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def snapshot_database(
    postgres_url: str, postgres_sync_url: str, monkeypatch: pytest.MonkeyPatch
) -> Iterator[str]:
    """Migrate a scratch database without changing the shared test schema."""
    name = f"backup_{uuid7().hex}"
    engine = create_engine(postgres_sync_url, isolation_level="AUTOCOMMIT")
    with engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    url = (
        make_url(postgres_url).set(database=name).render_as_string(hide_password=False)
    )
    try:
        with monkeypatch.context() as patch:
            patch.setenv("MENAGERIST_DATABASE_URL", url)
            get_database_settings.cache_clear()
            alembic_runner.upgrade()
        get_database_settings.cache_clear()
        yield url
    finally:
        get_database_settings.cache_clear()
        with engine.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        engine.dispose()
