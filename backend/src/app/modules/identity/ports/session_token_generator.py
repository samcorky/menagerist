from typing import Protocol


class SessionTokenGenerator(Protocol):
    """Makes session secrets and the hashes stored in their place."""

    def new_token(self) -> str:
        """Return a new unguessable session token."""
        ...

    def token_hash(self, token: str) -> str:
        """Return the sha256 hex digest stored for `token`."""
        ...
