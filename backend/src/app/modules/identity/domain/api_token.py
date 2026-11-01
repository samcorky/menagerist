import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from app.modules.identity.domain.errors import InvalidApiTokenRequestError
from app.shared_kernel.mixins import Identifiable

if TYPE_CHECKING:
    from collections.abc import Iterable

MAX_TOKEN_NAME_LENGTH = 64


@dataclass(kw_only=True, eq=False)
class ApiToken(Identifiable):
    """A personal access token, identified by the hash of its secret."""

    user_id: uuid.UUID
    name: str
    secret_hash: str
    grants: frozenset[str]
    created_at: datetime
    expires_at: datetime
    last_used_at: datetime | None = None

    @classmethod
    def create(
        cls,
        *,
        token_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str,
        secret_hash: str,
        grants: Iterable[str],
        now: datetime,
        expires_at: datetime,
    ) -> ApiToken:
        """Create a token, validating its name, grants and expiry."""
        cleaned = name.strip()
        if not 1 <= len(cleaned) <= MAX_TOKEN_NAME_LENGTH:
            msg = f"A token name must be 1 to {MAX_TOKEN_NAME_LENGTH} characters."
            raise InvalidApiTokenRequestError(msg)
        granted = frozenset(grants)
        if not granted:
            msg = "A token needs at least one permission."
            raise InvalidApiTokenRequestError(msg)
        if expires_at <= now:
            msg = "A token must expire in the future."
            raise InvalidApiTokenRequestError(msg)
        return cls(
            id=token_id,
            user_id=user_id,
            name=cleaned,
            secret_hash=secret_hash,
            grants=granted,
            created_at=now,
            expires_at=expires_at,
        )

    def is_expired(self, now: datetime) -> bool:
        """Whether `now` is at or past the expiry instant."""
        return now >= self.expires_at

    def used(self, now: datetime) -> None:
        """Record use at `now`."""
        self.last_used_at = now
