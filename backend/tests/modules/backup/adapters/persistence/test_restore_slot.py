from datetime import UTC, datetime

import pytest
import time_machine
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.entrypoints.api.shared.bridges.backup_setup_gate import (
    BackupSetupGate,
    first_run_restore_slot,
    get_setup_gate,
    reserve_restore_attempt,
)
from app.modules.backup.domain.errors import RestoreTargetNotEmptyError
from app.modules.identity.adapters.persistence import (
    in_memory_sign_in_attempt_repository as attempts_adapter,
)
from app.modules.identity.adapters.persistence.in_memory_session_repository import (
    InMemorySessionRepository,
)
from app.modules.identity.adapters.persistence.in_memory_user_repository import (
    InMemoryUserRepository,
)
from app.modules.identity.adapters.persistence.user_repository import (
    SqlAlchemyUserRepository,
)
from app.modules.identity.application.sign_in_throttle import ip_key
from app.modules.identity.domain.user import Role, User
from app.modules.identity.ports.unit_of_work import IdentityRepos
from app.shared_kernel.errors import TooManyRequestsError

NOW = datetime(2026, 10, 19, 12, tzinfo=UTC)


def _user() -> User:
    return User.create(
        username="admin",
        display_name="Administrator",
        password_hash="hash",
        role=Role.ADMIN,
        now=NOW,
    )


async def test_in_memory_gate_uses_identity_setup_condition() -> None:
    """Any existing identity account closes the backup setup gate."""
    users = InMemoryUserRepository()
    gate = BackupSetupGate(
        IdentityRepos(
            users=users,
            sessions=InMemorySessionRepository(),
            attempts=attempts_adapter.InMemorySignInAttemptRepository(),
        )
    )
    assert await gate.is_open()
    await users.add(_user())
    assert not await gate.is_open()


@time_machine.travel(NOW, tick=False)
async def test_restore_attempts_have_distinct_ip_namespace_and_fixed_window() -> None:
    """Three attempts pass, the fourth waits, and sign-in counters stay separate."""
    attempts = attempts_adapter.InMemorySignInAttemptRepository()
    for _ in range(3):
        await reserve_restore_attempt(attempts, "127.0.0.1")
    assert ip_key("127.0.0.1") not in attempts.windows
    assert attempts.windows[ip_key("backup-restore:127.0.0.1")].count == 3
    with pytest.raises(TooManyRequestsError) as caught:
        await reserve_restore_attempt(attempts, "127.0.0.1")
    assert caught.value.retry_after == 900
    await reserve_restore_attempt(attempts, "127.0.0.2")
    with time_machine.travel("2026-10-19 12:15:00+00:00", tick=False):
        await reserve_restore_attempt(attempts, "127.0.0.1")
    assert attempts.windows[ip_key("backup-restore:127.0.0.1")].count == 1


@pytest.mark.integration
async def test_restore_slot_serialises_uploads_and_releases_lock(
    snapshot_database: str,
) -> None:
    """Separate connections cannot hold the anonymous upload slot together."""
    engine = create_async_engine(snapshot_database)
    factory = async_sessionmaker(engine)
    try:
        first = first_run_restore_slot(factory, "first")
        await anext(first)
        blocked = first_run_restore_slot(factory, "second")
        with pytest.raises(TooManyRequestsError, match="in progress") as caught:
            await anext(blocked)
        assert caught.value.retry_after == 30
        await anext(first, None)
        next_slot = first_run_restore_slot(factory, "third")
        await anext(next_slot)
        await anext(next_slot, None)
    finally:
        await engine.dispose()


@pytest.mark.integration
@time_machine.travel(NOW, tick=False)
async def test_restore_slot_persists_rate_limit_and_refuses_existing_setup(
    snapshot_database: str,
) -> None:
    """Counters survive released slots; closed setup rejects before reservation."""
    engine = create_async_engine(snapshot_database)
    factory = async_sessionmaker(engine)
    try:
        for _ in range(3):
            slot = first_run_restore_slot(factory, None)
            await anext(slot)
            await anext(slot, None)
        refused = first_run_restore_slot(factory, None)
        with pytest.raises(TooManyRequestsError) as caught:
            await anext(refused)
        assert caught.value.retry_after == 900
        async with factory.begin() as session:
            await SqlAlchemyUserRepository(session).add(_user())
        gate_stream = get_setup_gate(factory)
        gate = await anext(gate_stream)
        assert not await gate.is_open()
        await anext(gate_stream, None)
        closed = first_run_restore_slot(factory, "unused")
        with pytest.raises(RestoreTargetNotEmptyError):
            await anext(closed)
        async with engine.connect() as connection:
            assert (
                await connection.scalar(text("SELECT count(*) FROM sign_in_attempts"))
                == 1
            )
    finally:
        await engine.dispose()
