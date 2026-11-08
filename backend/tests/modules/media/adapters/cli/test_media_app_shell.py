"""Two database commands in one process, as the interactive shell runs them."""

import pytest

from app.modules.media.adapters.cli.media_app import cleanup

pytestmark = pytest.mark.integration


def test_a_database_command_can_run_twice_in_one_process(postgres_url: str) -> None:
    """The second run reuses the cached engine on a new event loop.

    Before commands released their pooled connections this failed with
    "Event loop is closed" on the second call (#294).
    """
    del postgres_url

    assert cleanup()["deleted"] == 0
    assert cleanup()["deleted"] == 0
