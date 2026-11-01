from app.modules.system.application.get_health import GetHealth, GetHealthQuery
from app.shared_kernel.access import Public
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import SYSTEM_ACTOR


async def test_get_health_returns_none() -> None:
    """GetHealth succeeds with no result - liveness has nothing to check."""
    guard = InMemoryAccessGuard()
    use_case = GetHealth(guard)

    await use_case.handle(GetHealthQuery(), SYSTEM_ACTOR)

    assert guard.checked == [(SYSTEM_ACTOR, Public())]
