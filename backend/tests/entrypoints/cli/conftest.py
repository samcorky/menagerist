import logging
from typing import TYPE_CHECKING

import pytest
import structlog

from app.platform.cli_output import OutputFormat, set_format

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def _no_database_for_serve(monkeypatch: pytest.MonkeyPatch) -> None:
    """`serve` asks Postgres for its connection limit; these tests have no database."""
    from app.platform import connection_budget

    async def unreachable() -> None:
        return None

    monkeypatch.setattr(connection_budget, "fetch_max_connections", unreachable)


@pytest.fixture(autouse=True)
def _plain_text_output() -> Iterator[None]:
    """Each test starts in automatic format, which is plain text under capture.

    `main` configures logging for the command it runs, so the logging set up by the
    application's import is put back afterwards for the tests that follow.
    """
    set_format(OutputFormat.AUTO)
    structlog_config = structlog.get_config()
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield
    set_format(OutputFormat.AUTO)
    structlog.configure(**structlog_config)
    root.handlers[:] = handlers
    root.setLevel(level)
