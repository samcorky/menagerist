import hashlib
import secrets


def _sha256_hex(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class SecretsSessionTokenGenerator:
    """`SessionTokenGenerator` backed by `secrets.token_urlsafe`."""

    def new_token(self) -> str:
        """Return 32 random bytes, URL-safe base64 encoded."""
        return secrets.token_urlsafe(32)

    def token_hash(self, token: str) -> str:
        """Return the sha256 hex digest of `token`."""
        return _sha256_hex(token)


class InMemorySessionTokenGenerator:
    """Deterministic `SessionTokenGenerator` for tests (`token-1`, `token-2`, ...)."""

    def __init__(self) -> None:
        self._count = 0

    def new_token(self) -> str:
        """Return the next token in the sequence."""
        self._count += 1
        return f"token-{self._count}"

    def token_hash(self, token: str) -> str:
        """Return the sha256 hex digest of `token`."""
        return _sha256_hex(token)
