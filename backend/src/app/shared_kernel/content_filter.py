import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ContentFilter:
    """Which content a query may return; a criterion only, with no rules.

    The access guard decides which scope an actor gets; repositories only
    apply it.
    """

    user_id: uuid.UUID | None

    @classmethod
    def of(cls, user_id: uuid.UUID) -> ContentFilter:
        """Content owned by `user_id`."""
        return cls(user_id=user_id)

    @classmethod
    def everyone(cls) -> ContentFilter:
        """Content with no restriction."""
        return cls(user_id=None)

    @property
    def is_everyone(self) -> bool:
        """Whether the scope applies no restriction."""
        return self.user_id is None

    def covers(self, owner_id: uuid.UUID | None) -> bool:
        """Whether content owned by `owner_id` is inside this scope."""
        return self.user_id is None or owner_id == self.user_id
