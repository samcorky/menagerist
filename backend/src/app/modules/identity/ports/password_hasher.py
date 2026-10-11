from typing import Protocol


class PasswordHasher(Protocol):
    """Turns passwords into storable hashes and checks them later."""

    def hash(self, password: str) -> str:
        """Return a self-describing hash of `password` with a fresh salt."""
        ...

    def verify(self, password: str, hashed: str) -> bool:
        """Whether `password` matches `hashed`; malformed hashes never match."""
        ...

    def needs_rehash(self, hashed: str) -> bool:
        """Whether `hashed` should be rewritten with the current scheme or cost."""
        ...
