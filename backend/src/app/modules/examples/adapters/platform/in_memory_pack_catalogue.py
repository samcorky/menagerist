from app.modules.examples.domain.pack import ExamplePack, PackSummary


class InMemoryPackCatalogue:
    """A catalogue built in code, for tests."""

    def __init__(self) -> None:
        self._entries: dict[str, tuple[str, str, ExamplePack]] = {}

    def add(self, pack: ExamplePack, *, name: str, description: str) -> None:
        """Add a pack under its id."""
        self._entries[pack.id] = (name, description, pack)

    async def list_packs(self) -> list[PackSummary]:
        """Return every pack's summary, in insertion order."""
        return [
            PackSummary(
                id=pack.id, name=name, description=description, counts=pack.counts
            )
            for name, description, pack in self._entries.values()
        ]

    async def get(self, pack_id: str) -> ExamplePack | None:
        """Return the pack with `pack_id`, or `None`."""
        entry = self._entries.get(pack_id)
        return entry[2] if entry else None
