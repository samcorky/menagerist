import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.testclient import TestClient
from structlog.testing import capture_logs

from app.entrypoints.api import create_app
from app.entrypoints.api.shared.access_guard import RoleAccessGuard, get_access_guard
from app.entrypoints.api.shared.access_policy import OwnerAccessPolicy
from app.entrypoints.api.shared.authorisation import RoleAuthorisationAdapter
from app.entrypoints.api.shared.dependencies import get_current_actor
from app.modules.system.adapters.api import dependencies
from app.modules.system.adapters.api.dependencies import (
    get_check_for_updates_use_case,
    get_get_health_ready_detail_use_case,
    get_get_health_ready_use_case,
    get_get_version_detail_use_case,
    get_release_channel,
)
from app.modules.system.adapters.persistence.in_memory_update_check_store import (
    InMemoryUpdateCheckStore,
)
from app.modules.system.adapters.persistence.unit_of_work import (
    create_in_memory_system_uow,
)
from app.modules.system.adapters.platform.checks import database_pool_utilization_check
from app.modules.system.adapters.platform.in_memory_app_info_adapter import (
    InMemoryAppInfoAdapter,
)
from app.modules.system.adapters.platform.in_memory_health_check_adapter import (
    InMemoryHealthCheckAdapter,
)
from app.modules.system.adapters.platform.in_memory_release_provider import (
    InMemoryReleaseProvider,
)
from app.modules.system.application.check_for_updates import CheckForUpdates
from app.modules.system.application.get_health_ready import GetHealthReady
from app.modules.system.application.get_health_ready_detail import GetHealthReadyDetail
from app.modules.system.application.get_version_detail import (
    GetVersionDetail,
    VersionDetailSources,
)
from app.modules.system.domain.app_info import AppInfo
from app.modules.system.domain.readiness import (
    CheckObservation,
    CheckStatus,
    ReadinessReport,
)
from app.modules.system.domain.release import CheckFailure, Release, ReleaseChannel
from app.platform.config import get_identity_settings
from app.platform.database import get_session_factory
from app.platform.storage_probe import DirectoryProbe
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import Actor

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path
    from types import TracebackType

    from fastapi import FastAPI

    from app.platform.storage_probe import DirectoryState

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
            "/api/v1/system/health/ready/detail"
        )

    assert response.status_code == 403
    assert "checks" not in response.json()


def test_readiness_check_failure_is_logged_not_returned() -> None:
    """The real error goes to the log with a fixed message in the payload."""
    engine = _make_mock_engine(checkedout=0, pool_size=5)
    with patch(_PATCH_GET_ENGINE, return_value=engine), capture_logs() as logs:
        response = TestClient(_app_with_failing_db()).get(
            "/api/v1/system/health/ready/detail"
        )

    assert "connection refused" not in response.text
    failures = [e for e in logs if e["event"] == "readiness check failed"]
    assert len(failures) == 3
    assert all(isinstance(e["exc_info"], OSError) for e in failures)


def test_readiness_503_when_db_unreachable() -> None:
    """The detail returns 503, status fail, and a fixed output on DB checks."""
    engine = _make_mock_engine(checkedout=0, pool_size=5)
    with patch(_PATCH_GET_ENGINE, return_value=engine):
        client = TestClient(_app_with_failing_db())
        response = client.get("/api/v1/system/health/ready/detail")

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
        response = client.get("/api/v1/system/health/ready/detail")

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
        response = client.get("/api/v1/system/health/ready/detail")

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
        response = client.get("/api/v1/system/health/ready/detail")

    data = response.json()
    pool_check = data["checks"]["database:poolUtilization"][0]
    assert pool_check["status"] == "pass"
    assert "output" not in pool_check


@pytest.mark.parametrize("storage", ["media", "backup"])
def test_readiness_reports_warn_status_without_503(storage: str) -> None:
    """A warn-status check is reflected in the payload but does not trigger 503."""
    report = ReadinessReport(
        status=CheckStatus.WARN,
        checks={
            f"storage:{storage}Writable": [
                CheckObservation(
                    component_type="datastore",
                    observed_value="not-writable",
                    observed_unit="state",
                    status=CheckStatus.WARN,
                    time=datetime.now(UTC),
                    output="Use chown 1000:1000 <host directory>.",
                )
            ],
            f"storage:{storage}FreeSpace": [
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
        adapter, InMemoryAccessGuard()
    )
    app.dependency_overrides[get_get_health_ready_detail_use_case] = lambda: (
        GetHealthReadyDetail(adapter, get_access_guard())
    )
    client = TestClient(app)

    public = client.get("/api/health/ready")
    response = client.get("/api/v1/system/health/ready/detail")

    assert public.status_code == 200
    assert public.headers["cache-control"] == "max-age=10"
    assert public.json() == {"status": "pass"}
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "warn"
    assert data["checks"][f"storage:{storage}Writable"][0]["status"] == "warn"
    assert "chown" in data["checks"][f"storage:{storage}Writable"][0]["output"]
    assert data["checks"][f"storage:{storage}FreeSpace"][0]["observedValue"] == 41.7


@pytest.mark.parametrize("state", ["writable", "missing", "not-writable"])
async def test_storage_check_includes_configured_backup_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, state: DirectoryState
) -> None:
    """The cached readiness check probes backup storage independently of media."""
    media_path = tmp_path / "media"
    backup_path = tmp_path / "backup"
    monkeypatch.setattr(
        dependencies,
        "get_media_settings",
        lambda: SimpleNamespace(storage_path=media_path),
    )
    monkeypatch.setattr(
        dependencies,
        "get_backup_settings",
        lambda: SimpleNamespace(path=backup_path),
    )

    def probe(path: Path) -> DirectoryProbe:
        return DirectoryProbe(
            state=state if path == backup_path else "writable",
            free_bytes=None if path == backup_path and state == "missing" else 2**31,
        )

    monkeypatch.setattr(
        "app.modules.system.adapters.platform.checks.storage_check.probe_directory",
        probe,
    )
    dependencies.get_storage_check.cache_clear()
    try:
        check = dependencies.get_storage_check()
        assert dependencies.get_storage_check() is check
        result = await check.run()
    finally:
        dependencies.get_storage_check.cache_clear()

    assert result["storage:mediaWritable"].status is CheckStatus.PASS
    backup = result["storage:backupWritable"]
    assert backup.observed_value == state
    assert backup.status is (
        CheckStatus.PASS if state == "writable" else CheckStatus.WARN
    )
    if state == "writable":
        assert backup.output is None
        assert result["storage:backupFreeSpace"].status is CheckStatus.PASS
    else:
        assert backup.output is not None
        assert str(backup_path) in backup.output
        if state == "missing":
            assert "storage:backupFreeSpace" not in result
        else:
            assert "chown 1000:1000" in backup.output


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
    response = ready_client.get("/api/v1/system/health/ready/detail")

    assert public.status_code == 200
    assert public.json() == {"status": "pass"}
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/health+json")

    data = response.json()
    assert data["status"] in {"pass", "warn"}

    assert data["checks"]["scheduler:workerHeartbeat"][0]["status"] in {"pass", "warn"}

    for key, checks in data["checks"].items():
        for check in checks:
            if key.startswith("storage:") or key == "scheduler:workerHeartbeat":
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
    data = TestClient(create_app()).get("/api/v1/system/version").json()

    assert set(data) == {"name", "current_version"}


def _app_with_updates(
    *,
    repository_url: str | None = "https://github.com/o/r",
    releases: list[Release] | None = None,
    failure: CheckFailure | None = None,
    channel: ReleaseChannel = ReleaseChannel.STABLE,
    role: str = "admin",
) -> tuple[FastAPI, InMemoryUpdateCheckStore, InMemoryReleaseProvider]:
    """An app whose release source, store and channel are in memory."""
    app = create_app()
    as_user(app, uuid.UUID(int=7), role)
    guard = RoleAccessGuard(RoleAuthorisationAdapter(), OwnerAccessPolicy())
    info = InMemoryAppInfoAdapter(
        AppInfo(
            name="menagerist",
            version="0.2026.10.0",
            dirty=False,
            repository_url=repository_url,
            migration_head=("abc",),
        )
    )
    store = InMemoryUpdateCheckStore()
    provider = InMemoryReleaseProvider(releases, failure=failure)
    app.dependency_overrides[get_release_channel] = lambda: channel
    app.dependency_overrides[get_get_version_detail_use_case] = lambda: (
        GetVersionDetail(VersionDetailSources(app_info=info, updates=store), guard)
    )
    app.dependency_overrides[get_check_for_updates_use_case] = lambda: CheckForUpdates(
        create_in_memory_system_uow(store), guard, app_info=info, provider=provider
    )
    return app, store, provider


def test_version_detail_for_admin_has_build_provenance() -> None:
    """Administrators get the full payload."""
    app, _, _ = _app_with_updates()

    data = TestClient(app).get("/api/v1/system/version/detail").json()

    assert {"name", "current_version", "migration_head"} <= set(data)


def test_version_detail_reports_an_unchecked_release_status_without_a_request() -> None:
    """Before any check, the status is unknown and GitHub is never contacted."""
    app, _, provider = _app_with_updates()

    data = TestClient(app).get("/api/v1/system/version/detail").json()

    assert data["release"] == {
        "channel": "stable",
        "provider": "github",
        "status": "unknown",
    }
    assert provider.calls == []


def test_version_detail_omits_release_when_the_build_names_no_repository() -> None:
    """With nothing to check against, there is no release object at all."""
    app, _, _ = _app_with_updates(repository_url=None)

    data = TestClient(app).get("/api/v1/system/version/detail").json()

    assert "release" not in data


def test_check_now_stores_a_result_the_detail_then_reports() -> None:
    """POST checks and stores; the next GET shows the newer release."""
    newer = Release(
        version="0.2026.11.0", url="https://github.com/o/r/releases/tag/0.2026.11.0"
    )
    app, _, provider = _app_with_updates(releases=[newer])
    client = TestClient(app)

    checked = client.post("/api/v1/system/version/check")
    data = client.get("/api/v1/system/version/detail").json()

    assert checked.status_code == 204
    assert len(provider.calls) == 1
    release = data["release"]
    assert release["status"] == "update_available"
    assert release["latest_version"] == "0.2026.11.0"
    assert release["url"] == "https://github.com/o/r/releases/tag/0.2026.11.0"
    assert release["checked_at"] is not None
    assert "failure" not in release


def test_a_failed_check_is_reported_and_not_an_error() -> None:
    """The route succeeds; the failure shows in the detail as a fixed code."""
    app, _, _ = _app_with_updates(failure=CheckFailure.RATE_LIMITED)
    client = TestClient(app)

    checked = client.post("/api/v1/system/version/check")
    release = client.get("/api/v1/system/version/detail").json()["release"]

    assert checked.status_code == 204
    assert release["status"] == "unknown"
    assert release["failure"] == "rate_limited"
    assert "checked_at" not in release


def test_check_now_is_forbidden_for_members() -> None:
    """Only holders of the check permission can make the server call out."""
    app, _, provider = _app_with_updates(role="member")

    response = TestClient(app).post("/api/v1/system/version/check")

    assert response.status_code == 403
    assert provider.calls == []


def test_version_detail_is_forbidden_for_members() -> None:
    """A member gets 403 and no build metadata."""
    app, _, _ = _app_with_updates(role="member")

    response = TestClient(app).get("/api/v1/system/version/detail")

    assert response.status_code == 403
    assert "migration_head" not in response.json()


# ---------------------------------------------------------------------------
# Browser check
# ---------------------------------------------------------------------------

_BROWSER = {"Sec-Fetch-Site": "same-origin", "Origin": "http://testserver"}
_SESSION = {"Cookie": f"{get_identity_settings().cookie_name}=secret-session-value"}


def _browser_client(role: str = "admin") -> TestClient:
    app = create_app()
    as_user(app, uuid.UUID(int=7), role)
    client = TestClient(app)
    client.headers.pop("Origin", None)
    return client


def test_browser_check_passes_for_intact_headers() -> None:
    """A browser's own headers reach the app and are reported back."""
    response = _browser_client().post(
        "/api/v1/system/browser-check", headers={**_BROWSER, **_SESSION}
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "status": "pass",
        "sec_fetch_site": "same-origin",
        "origin": "http://testserver",
        "seen_origin": "http://testserver",
    }


def test_browser_check_warns_when_the_origin_differs() -> None:
    """A proxy that changes the host shows both origins."""
    headers = {"Sec-Fetch-Site": "same-origin", "Origin": "https://public.example"}
    data = (
        _browser_client()
        .post("/api/v1/system/browser-check", headers={**headers, **_SESSION})
        .json()
    )

    assert data["status"] == "warn"
    assert data["origin"] == "https://public.example"
    assert data["seen_origin"] == "http://testserver"
    assert "MENAGERIST_API_TRUSTED_PROXIES" in data["output"]


def test_browser_check_is_refused_when_the_headers_were_removed() -> None:
    """A signed-in request without Origin or Sec-Fetch-Site is a csrf_failed 403."""
    response = _browser_client().post("/api/v1/system/browser-check", headers=_SESSION)

    assert response.status_code == 403
    assert response.json()["type"].endswith("csrf_failed")


def test_browser_check_needs_the_diagnostics_permission() -> None:
    """A member is refused with the permission problem, not a CSRF one."""
    response = _browser_client("member").post(
        "/api/v1/system/browser-check", headers={**_BROWSER, **_SESSION}
    )

    assert response.status_code == 403
    assert not response.json()["type"].endswith("csrf_failed")


_MOVED = [
    ("get", "/api/version"),
    ("get", "/api/version/detail"),
    ("get", "/api/health/ready/detail"),
    ("post", "/api/browser-check"),
]


def test_public_version_needs_no_session_at_its_v1_path() -> None:
    """The public version answers without a session."""
    assert TestClient(create_app()).get("/api/v1/system/version").status_code == 200


def test_root_probes_need_no_session() -> None:
    """Liveness is not behind authentication."""
    assert TestClient(create_app()).get("/api/health").status_code == 200


@pytest.mark.parametrize(("method", "path"), _MOVED)
def test_old_system_paths_are_gone(method: str, path: str) -> None:
    """The pre-v1 paths no longer exist."""
    response = TestClient(create_app()).request(method, path)
    assert response.status_code in {404, 405}


def test_system_operation_ids_are_unchanged() -> None:
    """Moving the paths leaves the generated client's function names alone."""
    schema = create_app().openapi()
    ids = {
        (path, method): op["operationId"]
        for path, item in schema["paths"].items()
        for method, op in item.items()
        if "/system/" in path or path.startswith("/api/health")
    }
    assert ids == {
        ("/api/health", "get"): "get_health",
        ("/api/health/ready", "get"): "get_health_ready",
        ("/api/v1/system/health/ready/detail", "get"): "get_health_ready_detail",
        ("/api/v1/system/version", "get"): "get_version",
        ("/api/v1/system/version/detail", "get"): "get_version_detail",
        ("/api/v1/system/version/check", "post"): "check_for_updates",
        ("/api/v1/system/browser-check", "post"): "run_browser_check",
    }
