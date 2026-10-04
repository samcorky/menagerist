from typing import Protocol


class ChoiceListSource(Protocol):
    """Read the options of a saved choice list, owned by another module."""

    async def options(self, list_id: str) -> list[str] | None:
        """Return the options, or `None` if the list is missing or not a choice list."""
        ...
