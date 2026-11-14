import json
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING

from app.modules.catalogue.adapters.platform.entry_parser import parse_entry
from app.modules.catalogue.domain.errors import InvalidEntryError

if TYPE_CHECKING:
    from app.modules.catalogue.domain.entry import CatalogueEntry


class FileEntryCatalogue:
    """Reads the entries shipped in `app/modules/catalogue/entries/`.

    Entries never change at runtime, so they are parsed once on first use.
    """

    def __init__(self, root: Path | None = None) -> None:
        self._root = root
        self._entries: dict[str, CatalogueEntry] | None = None

    def _load(self) -> dict[str, CatalogueEntry]:
        if self._entries is None:
            root = self._root or Path(str(files("app.modules.catalogue") / "entries"))
            entries: dict[str, CatalogueEntry] = {}
            for path in sorted(root.glob("*.json")):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError, RecursionError) as exc:
                    raise InvalidEntryError(f"cannot read {path.name}: {exc}") from exc
                entry = parse_entry(data)
                if entry.id != path.stem:
                    raise InvalidEntryError(f"{path.name} declares id '{entry.id}'")
                entries[entry.id] = entry
            self._entries = entries
        return self._entries

    async def list_entries(self) -> list[CatalogueEntry]:
        """Return every entry, ordered by file name."""
        return list(self._load().values())

    async def get(self, entry_id: str) -> CatalogueEntry | None:
        """Return the entry with `entry_id`, or `None`."""
        return self._load().get(entry_id)
