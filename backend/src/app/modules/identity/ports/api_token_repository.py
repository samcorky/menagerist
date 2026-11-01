from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import uuid
    from datetime import datetime

    from app.modules.identity.domain.api_token import ApiToken


class ApiTokenRepository(Protocol):
    """Access to personal access tokens, independent of storage backend."""

    async def add(self, token: ApiToken) -> None:
        """Add a new token."""
        ...

    async def save(self, token: ApiToken) -> None:
        """Persist changes to an existing token (e.g. `last_used_at`)."""
        ...

    async def get(self, token_id: uuid.UUID) -> ApiToken | None:
        """Return the token with `token_id`, or `None`."""
        ...

    async def list_for_user(
        self, user_id: uuid.UUID, *, now: datetime
    ) -> list[ApiToken]:
        """Return unexpired tokens for `user_id`, newest `created_at` first."""
        ...

    async def count_active(self, user_id: uuid.UUID, *, now: datetime) -> int:
        """Return how many unexpired tokens `user_id` holds."""
        ...

    async def delete(self, token_id: uuid.UUID) -> None:
        """Remove one token; unknown ids are ignored."""
        ...

    async def delete_for_user(self, user_id: uuid.UUID) -> int:
        """Remove every token belonging to `user_id`, returning how many went."""
        ...

    async def delete_expired(self, now: datetime) -> int:
        """Remove tokens expired at `now`, returning how many went."""
        ...
