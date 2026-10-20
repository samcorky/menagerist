class InMemorySetupGate:
    """Configurable first-run gate without an identity database."""

    def __init__(self, *, open: bool = True) -> None:
        self.open = open

    async def is_open(self) -> bool:
        """Return the configured setup state."""
        return self.open
