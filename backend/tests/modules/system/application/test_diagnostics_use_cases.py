import uuid

import pytest

from app.entrypoints.api.shared.authorization import RoleAuthorizationAdapter
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
)
from app.modules.system.application.permissions import SystemPermission
from app.modules.system.domain.app_info import AppInfo
from app.modules.system.domain.readiness import CheckStatus, ReadinessReport
from app.shared_kernel.actor import SYSTEM_ACTOR, Actor
from app.shared_kernel.errors import ForbiddenError

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
        InMemoryAppInfoAdapter(APP_INFO), RoleAuthorizationAdapter()
    )

    assert await use_case.handle(GetVersionDetailQuery(), actor) is APP_INFO


async def test_member_cannot_read_version_detail() -> None:
    """Members hold no diagnostics permission."""
    use_case = GetVersionDetail(
        InMemoryAppInfoAdapter(APP_INFO), RoleAuthorizationAdapter()
    )

    with pytest.raises(ForbiddenError):
        await use_case.handle(GetVersionDetailQuery(), MEMBER)


async def test_admin_reads_readiness_detail_and_member_is_refused() -> None:
    """The checks run only for a holder of the permission."""
    adapter = InMemoryHealthCheckAdapter(REPORT)
    use_case = GetHealthReadyDetail(adapter, RoleAuthorizationAdapter())

    assert await use_case.handle(GetHealthReadyDetailQuery(), ADMIN) is REPORT
    with pytest.raises(ForbiddenError):
        await use_case.handle(GetHealthReadyDetailQuery(), MEMBER)
