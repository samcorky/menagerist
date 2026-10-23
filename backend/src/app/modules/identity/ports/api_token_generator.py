import uuid
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class NewApiToken:
    """A freshly generated token; `plaintext` is shown once and never stored."""

    token_id: uuid.UUID
    secret: str
    plaintext: str


@dataclass(frozen=True)
class ParsedApiToken:
    """The id and secret recovered from a presented token."""

    token_id: uuid.UUID
    secret: str


class ApiTokenGenerator(Protocol):
    """Makes, parses and hashes personal access tokens."""

    def new_token(self) -> NewApiToken:
        """Return a new token with a fresh id and secret."""
        ...

    def parse(self, value: str) -> ParsedApiToken | None:
        """Return the id and secret in `value`, or `None` if it is malformed."""
        ...

    def hash(self, secret: str) -> str:
        """Return the SHA-256 hex digest stored for `secret`."""
        ...

    def matches(self, secret: str, stored_hash: str) -> bool:
        """Whether `secret` hashes to `stored_hash`, in constant time."""
        ...
