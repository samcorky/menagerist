import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.testclient import TestClient
from structlog.testing import capture_logs

from app.entrypoints.api import create_app
from app.entrypoints.api.shared.authorization import RoleAuthorizationAdapter
from app.entrypoints.api.shared.dependencies import get_current_actor
from app.modules.system.adapters.api.dependencies import (
    get_get_health_ready_detail_use_case,
    get_get_health_ready_use_case,
)
from app.modules.system.adapters.platform.checks import database_pool_utilization_check
from app.modules.system.adapters.platform.in_memory_health_check_adapter import (
    InMemoryHealthCheckAdapter,
)
from app.modules.system.application.get_health_ready import GetHealthReady
from app.modules.system.application.get_health_ready_detail import GetHealthReadyDetail
from app.modules.system.domain.readiness import (
    CheckObservation,
    CheckStatus,
    ReadinessReport,
)
from app.platform.database import get_session_factory
from app.shared_kernel.actor import Actor

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


def as_user(app: FastAPI, user_id: uuid.UUID, role: str) -> None:
    """Run every request to `app` as a user holding `role`."""
    actor = Actor(id=user_id, roles=frozenset({role}))
    app.dependency_overrides[get_current_actor] = lambda: actor


def _app_with_failing_db(role: str = "admin") -> FastAPI:
    app = create_app()
    app.dependency_overrides[get_session_factory] = lambda: _FailingSessionFactory()
    as_user(app, uuid.UUID(int=7), role)
    return app


# ---------------------------------------------------------------------------
# Unit tests - no Docker / real database required
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


def test_public_readiness_is_only_pass_or_fail() -> None:
    """No component names, values or driver errors reach an anonymous caller."""
    engine = _make_mock_engine(checkedout=5, pool_size=5)
    with patch(_PATCH_GET_ENGINE, return_value=engine):
        client = TestClient(_app_with_failing_db("member"))
        response = client.get("/api/health/ready")

    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/health+json")
    assert response.headers["cache-control"] == "max-age=10"
    assert response.json() == {"status": "fail"}
    assert "refused" not in response.text


def test_readiness_detail_needs_the_diagnostics_permission() -> None:
    """A member is refused the detail with 403."""
    engine = _make_mock_engine(checkedout=0, pool_size=5)
    with patch(_PATCH_GET_ENGINE, return_value=engine):
        response = TestClient(_app_with_failing_db("member")).get(
            "/api/health/ready/detail"
        )

    assert response.status_code == 403
    assert "checks" not in response.json()


def test_readiness_check_failure_is_logged_not_returned() -> None:
    """The real error goes to the log with a fixed message in the payload."""
    engine = _make_mock_engine(checkedout=0, pool_size=5)
    with patch(_PATCH_GET_ENGINE, return_value=engine), capture_logs() as logs:
        response = TestClient(_app_with_failing_db()).get("/api/health/ready/detail")

    assert "connection refused" not in response.text
    failures = [e for e in logs if e["event"] == "readiness check failed"]
    assert len(failures) == 3
    assert all(isinstance(e["exc_info"], OSError) for e in failures)


def test_readiness_503_when_db_unreachable() -> None:
    """The detail returns 503, status fail, and a fixed output on DB checks."""
    engine = _make_mock_engine(checkedout=0, pool_size=5)
    with patch(_PATCH_GET_ENGINE, return_value=engine):
        client = TestClient(_app_with_failing_db())
        response = client.get("/api/health/ready/detail")

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
        assert check["output"] == "check failed", "the driver error must not leak"


def test_readiness_output_absent_on_passing_checks() -> None:
    """Passing checks must omit output entirely - not serialize it as null."""
    engine = _make_mock_engine(checkedout=0, pool_size=5)
    with patch(_PATCH_GET_ENGINE, return_value=engine):
        client = TestClient(_app_with_failing_db())
        response = client.get("/api/health/ready/detail")

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
        response = client.get("/api/health/ready/detail")

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
        response = client.get("/api/health/ready/detail")

    data = response.json()
    pool_check = data["checks"]["database:poolUtilization"][0]
    assert pool_check["status"] == "pass"
    assert "output" not in pool_check


def test_readiness_reports_warn_status_without_503() -> None:
    """A warn-status check is reflected in the payload but does not trigger 503."""
    report = ReadinessReport(
        status=CheckStatus.WARN,
        checks={
            "storage:mediaWritable": [
                CheckObservation(
                    component_type="datastore",
                    observed_value="not-writable",
                    observed_unit="state",
                    status=CheckStatus.WARN,
                    time=datetime.now(UTC),
                    output="Use chown 1000:1000 <host directory>.",
                )
            ],
            "storage:mediaFreeSpace": [
                CheckObservation(
                    component_type="datastore",
                    observed_value=41.7,
                    observed_unit="GiB",
                    status=CheckStatus.PASS,
                    time=datetime.now(UTC),
                )
            ],
        },
    )
    app = create_app()
    as_user(app, uuid.UUID(int=7), "admin")
    adapter = InMemoryHealthCheckAdapter(report)
    app.dependency_overrides[get_get_health_ready_use_case] = lambda: GetHealthReady(
        adapter
    )
    app.dependency_overrides[get_get_health_ready_detail_use_case] = lambda: (
        GetHealthReadyDetail(adapter, RoleAuthorizationAdapter())
    )
    client = TestClient(app)

    public = client.get("/api/health/ready")
    response = client.get("/api/health/ready/detail")

    assert public.status_code == 200
    assert public.headers["cache-control"] == "max-age=10"
    assert public.json() == {"status": "pass"}
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "warn"
    assert data["checks"]["storage:mediaWritable"][0]["status"] == "warn"
    assert "chown" in data["checks"]["storage:mediaWritable"][0]["output"]
    assert data["checks"]["storage:mediaFreeSpace"][0]["observedValue"] == 41.7


# ---------------------------------------------------------------------------
# Integration tests - require a real Postgres (testcontainers)
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
    as_user(app, uuid.UUID(int=7), "admin")
    with patch(_PATCH_GET_ENGINE, return_value=engine), TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.mark.integration
def test_readiness_passes_with_real_db(ready_client: TestClient) -> None:
    """GET /health/ready returns 200 and all checks pass against a live database."""
    public = ready_client.get("/api/health/ready")
    response = ready_client.get("/api/health/ready/detail")

    assert public.status_code == 200
    assert public.json() == {"status": "pass"}
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/health+json")

    data = response.json()
    assert data["status"] in {"pass", "warn"}

    for key, checks in data["checks"].items():
        for check in checks:
            if key.startswith("storage:"):
                assert check["status"] in {"pass", "warn"}
            else:
                assert check["status"] == "pass", (
                    f"{key} should pass against live migrated DB"
                )
            if check["status"] == "pass":
                assert "output" not in check, (
                    f"{key} should have no output when passing"
                )


# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------


def test_public_version_has_only_name_and_version() -> None:
    """No commit, branch or migration head for an anonymous caller."""
    data = TestClient(create_app()).get("/api/version").json()

    assert set(data) == {"name", "current_version"}


def test_version_detail_for_admin_has_build_provenance() -> None:
    """Administrators get the full payload."""
    app = create_app()
    as_user(app, uuid.UUID(int=7), "admin")

    data = TestClient(app).get("/api/version/detail").json()

    assert {"name", "current_version", "migration_head"} <= set(data)


def test_version_detail_is_forbidden_for_members() -> None:
    """A member gets 403 and no build metadata."""
    response = TestClient(create_app()).get("/api/version/detail")

    assert response.status_code == 403
    assert "migration_head" not in response.json()
