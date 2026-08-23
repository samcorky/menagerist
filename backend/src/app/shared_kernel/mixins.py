import uuid
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(kw_only=True, eq=False)
class Identifiable:
    """An entity identified by a uuid7 primary key."""

    id: uuid.UUID


@dataclass(kw_only=True, eq=False)
class Timestamped:
    """An entity that tracks its own creation and last-modified times."""

    created_at: datetime
    updated_at: datetime

    def touch(self) -> None:
        """Update `updated_at` to the current time."""
        self.updated_at = datetime.now(UTC)


@dataclass(kw_only=True, eq=False)
class SoftDeletable(Timestamped):
    """A `Timestamped` entity that is deactivated rather than physically removed."""

    deleted_at: datetime | None = None

    @property
    def is_deleted(self) -> bool:
        """Whether this entity has been soft-deleted."""
        return self.deleted_at is not None

    def soft_delete(self) -> None:
        """Mark this entity as deleted, timestamping the lifecycle change."""
        now = datetime.now(UTC)
        self.deleted_at = now
        self.updated_at = now
