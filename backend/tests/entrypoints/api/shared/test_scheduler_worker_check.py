"""Worker diagnostics must never remove the API from rotation."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
import time_machine

from app.entrypoints.api.shared.bridges.scheduler_worker_check import (
    SchedulerWorkerCheck,
)
from app.modules.system.adapters.platform.readiness_check_registry import (
    ReadinessCheckRegistry,
)
from app.modules.system.domain.readiness import CheckStatus

NOW = datetime(2026, 10, 27, tzinfo=UTC)


@pytest.mark.parametrize("alive", [True, False])
@pytest.mark.parametrize("timeout", [120, 300])
@time_machine.travel(NOW, tick=False)
async def test_worker_check_uses_configured_window(
    alive: bool,
    timeout: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A healthy worker passes; a missing or stale one only warns."""
    factory = MagicMock()
    from app.platform.config.scheduler import get_scheduler_settings

    monkeypatch.setenv(
        "MENAGERIST_SCHEDULER_WORKER_HEARTBEAT_TIMEOUT_SECONDS", str(timeout)
    )
    get_scheduler_settings.cache_clear()
    factory.return_value.__aenter__.return_value.scalar = AsyncMock(return_value=alive)
    try:
        result = (await SchedulerWorkerCheck(factory).run())[
            "scheduler:workerHeartbeat"
        ]
    finally:
        get_scheduler_settings.cache_clear()
    assert result.status is (CheckStatus.PASS if alive else CheckStatus.WARN)
    assert result.time == NOW
    assert result.observed_value == ("running" if alive else "stale")
    assert result.observed_unit == "state"
    statement = factory.return_value.__aenter__.return_value.scalar.call_args.args[0]
    assert NOW - timedelta(seconds=timeout) in statement.compile().params.values()
    if not alive:
        assert result.output is not None
        assert str(timeout) in result.output


async def test_absent_worker_keeps_public_readiness_healthy() -> None:
    """The public readiness endpoint remains healthy when only the worker is absent."""
    from starlette.testclient import TestClient

    from app.entrypoints.api import create_app
    from app.entrypoints.api.shared.access_guard import get_access_guard
    from app.modules.system.adapters.api.dependencies import (
        get_get_health_ready_use_case,
    )
    from app.modules.system.application.get_health_ready import GetHealthReady

    factory = MagicMock()
    factory.return_value.__aenter__.return_value.scalar = AsyncMock(return_value=False)
    registry = ReadinessCheckRegistry([SchedulerWorkerCheck(factory)])
    report = await registry.check()
    assert report.status is CheckStatus.WARN
    app = create_app()
    app.dependency_overrides[get_get_health_ready_use_case] = lambda: GetHealthReady(
        registry, get_access_guard()
    )
    response = TestClient(app).get("/api/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "pass"}


async def test_worker_check_failure_warns_without_exposing_database_errors() -> None:
    """Diagnostics failures cannot fail readiness or disclose connection details."""
    factory = MagicMock(side_effect=OSError("private connection details"))
    result = (await SchedulerWorkerCheck(factory).run())["scheduler:workerHeartbeat"]
    assert result.status is CheckStatus.WARN
    assert result.observed_value == "unknown"
    assert result.output is not None
    assert "private" not in result.output
