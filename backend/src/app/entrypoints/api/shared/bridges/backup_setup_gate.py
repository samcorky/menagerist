"""Bridge restoration to identity's setup check and existing attempt counters."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends
from sqlalchemy import func, select

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.modules.backup.domain.errors import RestoreTargetNotEmptyError
from app.modules.identity.adapters.api.dependencies import get_client_ip
from app.modules.identity.adapters.persistence.sign_in_attempt_repository import (
    SqlAlchemySignInAttemptRepository,
)
from app.modules.identity.adapters.persistence.unit_of_work import build_identity_repos
from app.modules.identity.application.get_setup_status import (
    GetSetupStatus,
    GetSetupStatusQuery,
)
from app.modules.identity.application.sign_in_throttle import SignInThrottle, ip_key
from app.modules.identity.domain.throttle import ThrottlePolicy
from app.platform.advisory_locks import BACKUP_RESTORE_LOCK_KEY
from app.platform.database import get_session_factory
from app.shared_kernel.actor import ANONYMOUS_ACTOR
from app.shared_kernel.errors import TooManyRequestsError

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.modules.identity.ports.sign_in_attempt_repository import (
        SignInAttemptRepository,
    )
    from app.modules.identity.ports.unit_of_work import IdentityRepos


class BackupSetupGate:
    """Expose the existing setup-status query through the backup port."""

    def __init__(self, repos: IdentityRepos) -> None:
        self._status = GetSetupStatus(repos, get_access_guard())

    async def is_open(self) -> bool:
        """Use the same condition as the existing first-run account setup."""
        return await self._status.handle(GetSetupStatusQuery(), ANONYMOUS_ACTOR)


async def get_setup_gate(
    factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
) -> AsyncIterator[BackupSetupGate]:
    """Yield the existing identity setup-status bridge."""
    async with factory() as session:
        yield BackupSetupGate(build_identity_repos(session))


async def reserve_restore_attempt(
    attempts: SignInAttemptRepository, client_ip: str
) -> None:
    """Reuse atomic identity counters under a distinct restore namespace."""
    now = datetime.now(UTC)
    throttle = SignInThrottle(ThrottlePolicy(ip_limit=3))
    reservation = await throttle.reserve(
        attempts, [ip_key(f"backup-restore:{client_ip}")], now
    )
    if reservation.locked_until is not None:
        refusal = throttle.throttled(reservation.locked_until, now)
        raise TooManyRequestsError(
            "Too many restore attempts. Try again later.",
            retry_after=refusal.retry_after,
        )


async def first_run_restore_slot(
    factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
    client_ip: Annotated[str | None, Depends(get_client_ip)],
) -> AsyncIterator[None]:
    """Permit one anonymous upload at a time across all server processes."""
    async with factory() as session:
        if not await BackupSetupGate(build_identity_repos(session)).is_open():
            raise RestoreTargetNotEmptyError("Setup has already been completed.")
        try:
            await reserve_restore_attempt(
                SqlAlchemySignInAttemptRepository(session), client_ip or "unknown"
            )
        finally:
            await session.commit()
    async with factory() as session, session.begin():
        acquired = await session.scalar(
            select(func.pg_try_advisory_xact_lock(BACKUP_RESTORE_LOCK_KEY))
        )
        if not acquired:
            raise TooManyRequestsError(
                "Another restore is in progress. Try again shortly.", retry_after=30
            )
        yield
