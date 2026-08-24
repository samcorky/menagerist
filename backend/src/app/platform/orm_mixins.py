"""ORM-side counterparts to `shared_kernel.mixins`.

Every persistence model composes from these the same way its domain entity
composes from `Identifiable`/`Timestamped`/`SoftDeletable` - kept here rather
than in `shared_kernel/` since they're SQLAlchemy-specific, and every module's
persistence layer is expected to reuse them rather than redeclare columns.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column


class IdentifiableMixin:
    """A row identified by a uuid7 primary key."""

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)


class TimestampedMixin:
    """A row that tracks its own creation and last-modified times.

    Domain entities set these via `datetime.now(UTC)` - timezone-aware - so the
    columns must be `TIMESTAMP WITH TIME ZONE`, not the SQLAlchemy/Postgres
    default of naive `TIMESTAMP`, or a round trip through the database would
    silently drop the timezone.
    """

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SoftDeletableMixin(TimestampedMixin):
    """A `TimestampedMixin` row that is deactivated rather than physically removed."""

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
