from dataclasses import dataclass
from typing import Protocol


@dataclass(kw_only=True, frozen=True)
class PasswordCredentials:
    """A username and password as typed on the sign-in form."""

    username: str
    password: str

    def __repr__(self) -> str:
        """Keep the password out of logs and tracebacks."""
        return f"PasswordCredentials(username={self.username!r})"


@dataclass(kw_only=True, frozen=True)
class VerifiedIdentity:
    """Who a credential check proved the caller to be."""

    subject: str
    display_name: str


class Authenticator(Protocol):
    """Checks credentials and names the person they belong to."""

    async def authenticate(
        self, credentials: PasswordCredentials
    ) -> VerifiedIdentity | None:
        """Return the verified identity, or `None` if the credentials are wrong.

        Raises:
            SignInThrottledError: If too many recent attempts were made.
        """
        ...
