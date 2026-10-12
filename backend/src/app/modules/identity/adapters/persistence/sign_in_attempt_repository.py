from typing import TYPE_CHECKING

from sqlalchemy import case, delete, null, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert

from app.modules.identity.adapters.persistence.models import SignInAttemptModel
from app.modules.identity.domain.throttle import (
    AttemptWindow,
    ThrottleKey,
    ThrottleKind,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime, timedelta

    from sqlalchemy.ext.asyncio import AsyncSession


class SqlAlchemySignInAttemptRepository:
    """Postgres-backed `SignInAttemptRepository`, scoped to one session.

    An attempt is one `INSERT ... ON CONFLICT DO UPDATE`, so concurrent attempts
    on a key serialise on its row and none is lost.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def locked_keys(
        self, keys: Sequence[ThrottleKey], *, now: datetime
    ) -> dict[ThrottleKey, datetime]:
        """Return, for each of `keys` that is locked at `now`, when its lock ends."""
        if not keys:
            return {}
        model = SignInAttemptModel
        stmt = select(model.key_type, model.key_hash, model.locked_until).where(
            tuple_(model.key_type, model.key_hash).in_(
                [(key.kind.value, key.digest) for key in keys]
            ),
            model.locked_until > now,
        )
        return {
            ThrottleKey(kind=ThrottleKind(kind), digest=digest): until
            for kind, digest, until in (await self._session.execute(stmt)).all()
        }

    async def record_failure(
        self, key: ThrottleKey, *, limit: int, window: timedelta, now: datetime
    ) -> AttemptWindow:
        """Count one attempt atomically (a fixed window, locking at `limit`)."""
        table = SignInAttemptModel
        first_lock = now + window if limit <= 1 else None
        expired = table.window_start <= now - window
        stmt = insert(table).values(
            key_type=key.kind.value,
            key_hash=key.digest,
            failure_count=1,
            window_start=now,
            locked_until=first_lock,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["key_type", "key_hash"],
            set_={
                "failure_count": case((expired, 1), else_=table.failure_count + 1),
                "window_start": case((expired, now), else_=table.window_start),
                "locked_until": case(
                    (expired, first_lock),
                    (
                        table.failure_count + 1 >= limit,
                        table.window_start + window,
                    ),
                    else_=null(),
                ),
            },
        )
        returning = stmt.returning(
            table.failure_count, table.window_start, table.locked_until
        )
        count, window_start, locked_until = (
            await self._session.execute(returning)
        ).one()
        return AttemptWindow(
            count=count, window_start=window_start, locked_until=locked_until
        )

    async def release_attempt(
        self, key: ThrottleKey, *, window_start: datetime, limit: int
    ) -> None:
        """Give back one attempt of the window `window_start`."""
        table = SignInAttemptModel
        await self._session.execute(
            update(table)
            .where(
                table.key_type == key.kind.value,
                table.key_hash == key.digest,
                table.window_start == window_start,
                table.failure_count > 0,
            )
            .values(
                failure_count=table.failure_count - 1,
                locked_until=case(
                    (table.failure_count - 1 >= limit, table.locked_until),
                    else_=null(),
                ),
            )
        )

    async def clear(self, key: ThrottleKey) -> None:
        """Forget `key`'s failures and lock; a no-op if it has none."""
        model = SignInAttemptModel
        await self._session.execute(
            delete(model).where(
                model.key_type == key.kind.value, model.key_hash == key.digest
            )
        )

    async def delete_stale(self, *, window: timedelta, now: datetime) -> int:
        """Delete counters whose window ended by `now`; return how many."""
        result = await self._session.execute(
            delete(SignInAttemptModel).where(
                SignInAttemptModel.window_start <= now - window
            )
        )
        return result.rowcount  # type: ignore[attr-defined, no-any-return]
