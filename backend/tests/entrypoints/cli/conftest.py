from typing import TYPE_CHECKING

import pytest

from app.platform.cli_output import OutputFormat, set_format

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def _plain_text_output() -> Iterator[None]:
    """Each test starts in automatic format, which is plain text under capture."""
    set_format(OutputFormat.AUTO)
    yield
    set_format(OutputFormat.AUTO)
