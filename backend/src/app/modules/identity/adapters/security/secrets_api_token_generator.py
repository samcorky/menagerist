import hashlib
import hmac
import re
import secrets
import uuid

from app.modules.identity.ports.api_token_generator import NewApiToken, ParsedApiToken

_PREFIX = "mnst"
_PATTERN = re.compile(r"mnst_([0-9a-f]{32})_([0-9a-f]{64})")


class SecretsApiTokenGenerator:
    """`ApiTokenGenerator` producing `mnst_<id>_<secret>` tokens."""

    def new_token(self) -> NewApiToken:
        """Return a token with a uuid7 id and a 64-hex-character secret."""
        token_id = uuid.uuid7()
        secret = secrets.token_hex(32)
        return NewApiToken(
            token_id=token_id,
            secret=secret,
            plaintext=f"{_PREFIX}_{token_id.hex}_{secret}",
        )

    def parse(self, value: str) -> ParsedApiToken | None:
        """Return the id and secret in `value`, or `None` if it is malformed."""
        match = _PATTERN.fullmatch(value)
        if match is None:
            return None
        return ParsedApiToken(token_id=uuid.UUID(match[1]), secret=match[2])

    def hash(self, secret: str) -> str:
        """Return the SHA-256 hex digest of `secret`."""
        return hashlib.sha256(secret.encode()).hexdigest()

    def matches(self, secret: str, stored_hash: str) -> bool:
        """Whether `secret` hashes to `stored_hash`, in constant time."""
        return hmac.compare_digest(self.hash(secret), stored_hash)
