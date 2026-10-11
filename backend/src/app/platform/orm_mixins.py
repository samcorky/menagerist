"""ORM-side counterparts to `shared_kernel.mixins`.

Every persistence model composes from these the same way its domain entity
composes from `Identifiable`/`Timestamped`/`SoftDeletable` - kept here rather
than in `shared_kernel/` since they're SQLAlchemy-specific, and every module's
persistence layer is expected to reuse them rather than redeclare columns.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar, Protocol

from sqlalchemy import ColumnElement, DateTime, or_, true, update
from sqlalchemy.orm import InstrumentedAttribute, Mapped, mapped_column

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class IdentifiableMixin:
    """A row identified by a uuid7 primary key."""

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)


class OwnedMixin:
    """A row owned by one user; NULL only on legacy rows (pre first-admin claim)."""

    owner_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)


class HasOwnerColumn(Protocol):
    """Any model with an `owner_id` column, nullable or not."""

    owner_id: ClassVar[InstrumentedAttribute[Any]]


def owned_by(
    model: type[HasOwnerColumn], user_id: uuid.UUID | None
) -> ColumnElement[bool]:
    """Predicate for rows owned by `user_id`; `None` means unrestricted.

    Rows with no owner match only the unrestricted case.
    """
    if user_id is None:
        return true()
    return model.owner_id == user_id


async def claim_rows(
    session: AsyncSession,
    model: type[HasOwnerColumn],
    owner_id: uuid.UUID,
    legacy_owner_ids: frozenset[uuid.UUID],
) -> int:
    """Give `owner_id` every row of `model` with no owner or a legacy owner.

    Soft-deleted rows are included. Returns the number of rows changed.
    """
    result = await session.execute(
        update(model)
        .where(or_(model.owner_id.is_(None), model.owner_id.in_(legacy_owner_ids)))
        .values(owner_id=owner_id)
        .execution_options(synchronize_session=False)
    )
    return result.rowcount  # type: ignore[attr-defined, no-any-return]


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
