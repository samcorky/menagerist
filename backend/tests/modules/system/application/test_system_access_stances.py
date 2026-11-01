from app.modules.system.application.get_health import GetHealth
from app.modules.system.application.get_health_ready import GetHealthReady
from app.modules.system.application.get_health_ready_detail import GetHealthReadyDetail
from app.modules.system.application.get_version import GetVersion
from app.modules.system.application.get_version_detail import GetVersionDetail
from app.modules.system.application.permissions import SystemPermission
from app.modules.system.application.run_browser_check import RunBrowserCheck
from app.shared_kernel.access import Public, Requires


def test_public_probes_are_public() -> None:
    """Liveness, readiness and version are open to anyone."""
    assert {
        GetHealth: GetHealth.access,
        GetHealthReady: GetHealthReady.access,
        GetVersion: GetVersion.access,
    } == {GetHealth: Public(), GetHealthReady: Public(), GetVersion: Public()}


def test_diagnostic_detail_requires_the_diagnostics_permission() -> None:
    """The detail views stay behind the diagnostics permission."""
    expected = Requires(SystemPermission.READ_DIAGNOSTICS)
    assert GetHealthReadyDetail.access == expected
    assert GetVersionDetail.access == expected
    assert RunBrowserCheck.access == expected
