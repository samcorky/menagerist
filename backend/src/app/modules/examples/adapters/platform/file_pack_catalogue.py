import json
from importlib.resources import files
from pathlib import Path
from typing import Any

from app.modules.examples.adapters.platform.pack_parser import (
    PACK_ID,
    IndexEntry,
    parse_index,
    parse_pack,
)
from app.modules.examples.domain.errors import InvalidPackError
from app.modules.examples.domain.pack import ExamplePack, PackSummary


class FilePackCatalogue:
    """Reads the packs shipped in `app/modules/examples/packs/`.

    Packs never change at runtime, so each file is parsed once and kept. File reads
    block the event loop, which is acceptable for small, cached files.
    """

    def __init__(self, root: Path | None = None) -> None:
        self._root = root
        self._index: list[IndexEntry] | None = None
        self._packs: dict[str, ExamplePack] = {}

    def _dir(self) -> Path:
        if self._root is not None:
            return self._root
        return Path(str(files("app.modules.examples") / "packs"))

    def _read(self, name: str) -> Any:  # noqa: ANN401
        path = self._dir() / name
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, RecursionError) as exc:
            raise InvalidPackError(f"cannot read {name}: {exc}") from exc

    def _entries(self) -> list[IndexEntry]:
        if self._index is None:
            self._index = parse_index(self._read("index.json"))
        return self._index

    def _load(self, pack_id: str) -> ExamplePack:
        if pack_id not in self._packs:
            name = f"{pack_id}.json"
            resolved = (self._dir() / name).resolve()
            if not PACK_ID.match(pack_id) or resolved.parent != self._dir().resolve():
                raise InvalidPackError(f"{name} is outside the examples directory")
            pack = parse_pack(self._read(name))
            if pack.id != pack_id:
                raise InvalidPackError(f"{pack_id}.json declares id '{pack.id}'")
            self._packs[pack_id] = pack
        return self._packs[pack_id]

    async def list_packs(self) -> list[PackSummary]:
        """Return a summary of every pack in the index."""
        return [
            PackSummary(
                id=e.id,
                name=e.name,
                description=e.description,
                counts=self._load(e.id).counts,
            )
            for e in self._entries()
        ]

    async def get(self, pack_id: str) -> ExamplePack | None:
        """Return the pack, or `None` if the index does not list it."""
        if all(e.id != pack_id for e in self._entries()):
            return None
        return self._load(pack_id)
