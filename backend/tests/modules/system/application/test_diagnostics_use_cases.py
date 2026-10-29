import uuid

import pytest

from app.entrypoints.api.shared.access_guard import RoleAccessGuard
from app.entrypoints.api.shared.access_policy import OwnerAccessPolicy
from app.entrypoints.api.shared.authorisation import RoleAuthorisationAdapter
from app.modules.system.adapters.persistence.in_memory_update_check_store import (
    InMemoryUpdateCheckStore,
)
from app.modules.system.adapters.platform.in_memory_app_info_adapter import (
    InMemoryAppInfoAdapter,
)
from app.modules.system.adapters.platform.in_memory_health_check_adapter import (
    InMemoryHealthCheckAdapter,
)
from app.modules.system.application.get_health_ready_detail import (
    GetHealthReadyDetail,
    GetHealthReadyDetailQuery,
)
from app.modules.system.application.get_version_detail import (
    GetVersionDetail,
    GetVersionDetailQuery,
    VersionDetailSources,
)
from app.modules.system.application.permissions import SystemPermission
from app.modules.system.application.run_browser_check import (
    RunBrowserCheck,
    RunBrowserCheckQuery,
)
from app.modules.system.domain.app_info import AppInfo
from app.modules.system.domain.browser_check import BrowserRequest, assess
from app.modules.system.domain.readiness import CheckStatus, ReadinessReport
from app.shared_kernel.actor import SYSTEM_ACTOR, Actor
from app.shared_kernel.errors import ForbiddenError

GUARD = RoleAccessGuard(RoleAuthorisationAdapter(), OwnerAccessPolicy())
ADMIN = Actor(id=uuid.UUID(int=1), roles=frozenset({"admin"}))
MEMBER = Actor(id=uuid.UUID(int=2), roles=frozenset({"member"}))
APP_INFO = AppInfo(name="menagerist", version="1.2.3", migration_head=("abc123",))
REPORT = ReadinessReport(status=CheckStatus.PASS, checks={})


def test_permission_value_follows_the_naming_pattern() -> None:
    """The permission reads `<module>:<resource>:<action>`."""
    assert SystemPermission.READ_DIAGNOSTICS.value == "system:diagnostics:read"


@pytest.mark.parametrize("actor", [ADMIN, SYSTEM_ACTOR])
async def test_admin_and_system_read_version_detail(actor: Actor) -> None:
    """Holders of the permission get the full build metadata."""
    use_case = GetVersionDetail(
        VersionDetailSources(
            app_info=InMemoryAppInfoAdapter(APP_INFO),
            updates=InMemoryUpdateCheckStore(),
        ),
        GUARD,
    )

    detail = await use_case.handle(GetVersionDetailQuery(), actor)

    assert detail.app_info is APP_INFO
    assert detail.release is None


async def test_member_cannot_read_version_detail() -> None:
    """Members hold no diagnostics permission."""
    use_case = GetVersionDetail(
        VersionDetailSources(
            app_info=InMemoryAppInfoAdapter(APP_INFO),
            updates=InMemoryUpdateCheckStore(),
        ),
        GUARD,
    )

    with pytest.raises(ForbiddenError):
        await use_case.handle(GetVersionDetailQuery(), MEMBER)


async def test_admin_reads_readiness_detail_and_member_is_refused() -> None:
    """The checks run only for a holder of the permission."""
    adapter = InMemoryHealthCheckAdapter(REPORT)
    use_case = GetHealthReadyDetail(adapter, GUARD)

    assert await use_case.handle(GetHealthReadyDetailQuery(), ADMIN) is REPORT
    with pytest.raises(ForbiddenError):
        await use_case.handle(GetHealthReadyDetailQuery(), MEMBER)


async def test_admin_runs_the_browser_check_and_member_is_refused() -> None:
    """The result is the assessment; a member holds no diagnostics permission."""
    request = BrowserRequest(
        sec_fetch_site="same-origin", origin="http://x", seen_origin="http://x"
    )
    use_case = RunBrowserCheck(GUARD)

    result = await use_case.handle(RunBrowserCheckQuery(request=request), ADMIN)

    assert result == assess(request)
    with pytest.raises(ForbiddenError):
        await use_case.handle(RunBrowserCheckQuery(request=request), MEMBER)
