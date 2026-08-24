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
