"""First-class in-memory setup state for scheduler execution."""


class InMemorySetupState:
    """Allow tests and local composition to change instance setup state."""

    def __init__(self, *, complete: bool = True) -> None:
        self.complete = complete

    async def is_complete(self) -> bool:
        """Return the current setup completion state."""
        return self.complete
