from dataclasses import replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid
    from datetime import datetime

    from app.modules.identity.domain.api_token import ApiToken


class InMemoryApiTokenRepository:
    """Dict-backed `ApiTokenRepository` for tests."""

    def __init__(self) -> None:
        self._tokens: dict[uuid.UUID, ApiToken] = {}

    async def add(self, token: ApiToken) -> None:
        """Add a new token."""
        self._tokens[token.id] = replace(token)

    async def save(self, token: ApiToken) -> None:
        """Persist changes to an existing token (e.g. `last_used_at`)."""
        self._tokens[token.id] = replace(token)

    async def get(self, token_id: uuid.UUID) -> ApiToken | None:
        """Return the token with `token_id`, or `None`."""
        stored = self._tokens.get(token_id)
        return None if stored is None else replace(stored)

    async def list_for_user(
        self, user_id: uuid.UUID, *, now: datetime
    ) -> list[ApiToken]:
        """Return unexpired tokens for `user_id`, newest `created_at` first."""
        tokens = [
            t
            for t in self._tokens.values()
            if t.user_id == user_id and not t.is_expired(now)
        ]
        tokens.sort(key=lambda t: t.id)
        tokens.sort(key=lambda t: t.created_at, reverse=True)
        return [replace(t) for t in tokens]

    async def count_active(self, user_id: uuid.UUID, *, now: datetime) -> int:
        """Return how many unexpired tokens `user_id` holds."""
        return sum(
            1
            for t in self._tokens.values()
            if t.user_id == user_id and not t.is_expired(now)
        )

    async def delete(self, token_id: uuid.UUID) -> None:
        """Remove one token; unknown ids are ignored."""
        self._tokens.pop(token_id, None)

    async def delete_for_user(self, user_id: uuid.UUID) -> int:
        """Remove every token belonging to `user_id`, returning how many went."""
        kept = {i: t for i, t in self._tokens.items() if t.user_id != user_id}
        removed = len(self._tokens) - len(kept)
        self._tokens = kept
        return removed

    async def delete_expired(self, now: datetime) -> int:
        """Remove tokens expired at `now`, returning how many went."""
        expired = [i for i, t in self._tokens.items() if t.is_expired(now)]
        for token_id in expired:
            del self._tokens[token_id]
        return len(expired)
