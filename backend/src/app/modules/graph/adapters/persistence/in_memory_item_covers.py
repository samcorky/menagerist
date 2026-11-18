from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid
    from collections.abc import Sequence

    from app.shared_kernel.actor import Actor


class InMemoryItemCovers:
    """Dict-backed ItemCovers for tests; `asked` records each lookup."""

    def __init__(self) -> None:
        self._thumbnails: dict[uuid.UUID, str] = {}
        self.asked: list[list[uuid.UUID]] = []

    def set(self, item_id: uuid.UUID, url: str) -> None:
        """Give an item a cover thumbnail at `url`."""
        self._thumbnails[item_id] = url

    async def thumbnails(
        self, item_ids: Sequence[uuid.UUID], actor: Actor
    ) -> dict[uuid.UUID, str]:
        """Return the thumbnail of each listed item that has one."""
        self.asked.append(list(item_ids))
        return {i: self._thumbnails[i] for i in item_ids if i in self._thumbnails}
