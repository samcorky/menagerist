import hmac

SCHEME = "fake"


class InMemoryPasswordHasher:
    """Cheap, insecure `PasswordHasher` for tests (`fake$<password>`)."""

    def hash(self, password: str) -> str:
        """Return a reversible stand-in for a hash."""
        return f"{SCHEME}${password}"

    def verify(self, password: str, hashed: str) -> bool:
        """Whether `hashed` was made from `password`."""
        return hmac.compare_digest(hashed.encode(), f"{SCHEME}${password}".encode())

    def needs_rehash(self, hashed: str) -> bool:
        """Never: the scheme has no cost parameters."""
        return False
