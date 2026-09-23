from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.modules.system.adapters.api.dependencies import get_get_health_ready_use_case
from app.modules.system.adapters.platform.checks import database_pool_utilization_check
from app.modules.system.adapters.platform.in_memory_health_check_adapter import (
    InMemoryHealthCheckAdapter,
)
from app.modules.system.application.get_health_ready import GetHealthReady
from app.modules.system.domain.readiness import (
    CheckObservation,
    CheckStatus,
    ReadinessReport,
)
from app.platform.database import get_session_factory

if TYPE_CHECKING:
    from collections.abc import Iterator
    from types import TracebackType

    from fastapi import FastAPI

_PATCH_GET_ENGINE = f"{database_pool_utilization_check.__name__}.get_engine"


class _FakeAsyncCM:
    """Async context manager that raises OSError on entry (simulates unreachable DB)."""

    async def __aenter__(self) -> None:
        raise OSError("connection refused")

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        pass


class _FailingSessionFactory:
    """Session factory that raises on every use, mimicking an unreachable Postgres."""

    def __call__(self) -> _FakeAsyncCM:
        return _FakeAsyncCM()


def _make_mock_engine(*, checkedout: int, pool_size: int) -> MagicMock:
    pool = MagicMock()
    pool.checkedout.return_value = checkedout
    pool.size.return_value = pool_size
    engine = MagicMock()
    engine.pool = pool
    return engine


def _app_with_failing_db() -> FastAPI:
    app = create_app()
    app.dependency_overrides[get_session_factory] = lambda: _FailingSessionFactory()
    return app


# ---------------------------------------------------------------------------
# Unit tests — no Docker / real database required
# ---------------------------------------------------------------------------


def test_liveness_passes_when_db_is_unreachable() -> None:
    """GET /health must return 200 regardless of database state."""
    engine = _make_mock_engine(checkedout=0, pool_size=5)
    with patch(_PATCH_GET_ENGINE, return_value=engine):
        client = TestClient(_app_with_failing_db())
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "pass"
    assert response.headers["content-type"].startswith("application/health+json")


def test_readiness_503_when_db_unreachable() -> None:
    """GET /health/ready returns 503, status fail, and populates output on DB checks."""
    engine = _make_mock_engine(checkedout=0, pool_size=5)
    with patch(_PATCH_GET_ENGINE, return_value=engine):
        client = TestClient(_app_with_failing_db())
        response = client.get("/api/health/ready")

    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/health+json")

    data = response.json()
    assert data["status"] == "fail"

    for key in (
        "database:responseTime",
        "database:version",
        "database:migrationRevision",
    ):
        check = data["checks"][key][0]
        assert check["status"] == "fail", f"{key} should be fail"
        assert "output" in check, f"{key} should have output populated"
        assert check["output"], f"{key} output should be non-empty"


def test_readiness_output_absent_on_passing_checks() -> None:
    """Passing checks must omit output entirely — not serialize it as null."""
    engine = _make_mock_engine(checkedout=0, pool_size=5)
    with patch(_PATCH_GET_ENGINE, return_value=engine):
        client = TestClient(_app_with_failing_db())
        response = client.get("/api/health/ready")

    data = response.json()
    pool_check = data["checks"]["database:poolUtilization"][0]
    # Pool is healthy (0/5): status is pass and output must not appear in the payload.
    assert pool_check["status"] == "pass"
    assert "output" not in pool_check


def test_pool_saturated_reports_fail_with_output() -> None:
    """database:poolUtilization is fail with output when pool is fully checked out."""
    engine = _make_mock_engine(checkedout=5, pool_size=5)
    with patch(_PATCH_GET_ENGINE, return_value=engine):
        client = TestClient(_app_with_failing_db())
        response = client.get("/api/health/ready")

    data = response.json()
    pool_check = data["checks"]["database:poolUtilization"][0]
    assert pool_check["status"] == "fail"
    assert "output" in pool_check
    assert "5/5" in pool_check["output"]


def test_pool_healthy_omits_output() -> None:
    """database:poolUtilization output is absent when the pool has free connections."""
    engine = _make_mock_engine(checkedout=1, pool_size=5)
    with patch(_PATCH_GET_ENGINE, return_value=engine):
        client = TestClient(_app_with_failing_db())
        response = client.get("/api/health/ready")

    data = response.json()
    pool_check = data["checks"]["database:poolUtilization"][0]
    assert pool_check["status"] == "pass"
    assert "output" not in pool_check


def test_readiness_reports_warn_status_without_503() -> None:
    """A warn-status check is reflected in the payload but does not trigger 503."""
    report = ReadinessReport(
        status=CheckStatus.WARN,
        checks={
            "database:poolUtilization": [
                CheckObservation(
                    component_type="datastore",
                    observed_value=80.0,
                    observed_unit="percent",
                    status=CheckStatus.WARN,
                    time=datetime.now(UTC),
                    output="4/5 connections checked out, 1 available",
                )
            ]
        },
    )
    app = create_app()
    app.dependency_overrides[get_get_health_ready_use_case] = lambda: GetHealthReady(
        InMemoryHealthCheckAdapter(report)
    )
    client = TestClient(app)

    response = client.get("/api/health/ready")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "warn"
    assert data["checks"]["database:poolUtilization"][0]["status"] == "warn"


# ---------------------------------------------------------------------------
# Integration tests — require a real Postgres (testcontainers)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ready_client(postgres_url: str) -> Iterator[TestClient]:
    """TestClient wired to a real migrated Postgres for readiness integration tests."""
    engine = create_async_engine(postgres_url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine, expire_on_commit=False
    )
    app = create_app()
    app.dependency_overrides[get_session_factory] = lambda: factory
    with patch(_PATCH_GET_ENGINE, return_value=engine):
        yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.mark.integration
def test_readiness_passes_with_real_db(ready_client: TestClient) -> None:
    """GET /health/ready returns 200 and all checks pass against a live database."""
    response = ready_client.get("/api/health/ready")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/health+json")

    data = response.json()
    assert data["status"] == "pass"

    for key, checks in data["checks"].items():
        for check in checks:
            assert check["status"] == "pass", (
                f"{key} should pass against live migrated DB"
            )
            assert "output" not in check, f"{key} should have no output when passing"
