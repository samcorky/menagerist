import json
from typing import TYPE_CHECKING

import pytest

from app.modules.catalogue.adapters.platform.file_entry_catalogue import (
    FileEntryCatalogue,
)
from app.modules.catalogue.adapters.platform.in_memory_entry_catalogue import (
    InMemoryEntryCatalogue,
)
from app.modules.catalogue.domain.errors import InvalidEntryError

if TYPE_CHECKING:
    from pathlib import Path


async def test_the_shipped_entries_load_and_can_be_found() -> None:
    """The shipped entries load and can be found."""
    catalogue = FileEntryCatalogue()
    entries = await catalogue.list_entries()
    assert len(entries) == 14
    assert (await catalogue.get("countries")) is not None
    assert await catalogue.get("missing") is None
    assert await catalogue.get("../etc") is None


async def test_a_malformed_file_is_reported(tmp_path: Path) -> None:
    """A malformed file is reported."""
    (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(InvalidEntryError):
        await FileEntryCatalogue(tmp_path).list_entries()


async def test_an_id_that_differs_from_the_file_name_is_reported(
    tmp_path: Path,
) -> None:
    """An id that differs from the file name is reported."""
    data = {
        "id": "other",
        "title": "T",
        "description": "d",
        "section": "starter_types",
        "itemTypes": [{"slug": "a", "label": "A"}],
    }
    (tmp_path / "named.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(InvalidEntryError):
        await FileEntryCatalogue(tmp_path).list_entries()


async def test_the_in_memory_catalogue_serves_what_it_was_given() -> None:
    """The in memory catalogue serves what it was given."""
    shipped = await FileEntryCatalogue().list_entries()
    memory = InMemoryEntryCatalogue(shipped[:2])
    assert await memory.list_entries() == shipped[:2]
    assert await memory.get(shipped[0].id) is shipped[0]
    assert await memory.get("nope") is None
