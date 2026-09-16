from app.modules.system.application.get_health import GetHealth, GetHealthQuery
from app.shared_kernel.actor import SYSTEM_ACTOR


async def test_get_health_returns_none() -> None:
    """GetHealth succeeds with no result - liveness has nothing to check."""
    use_case = GetHealth()

    await use_case.handle(GetHealthQuery(), SYSTEM_ACTOR)
