from app.modules.system.application.get_web_app_manifest import (
    GetWebAppManifest,
    GetWebAppManifestQuery,
)
from app.shared_kernel.access import Public
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import SYSTEM_ACTOR


async def test_manifest_carries_the_configured_public_origin() -> None:
    """The origin comes from configuration, never from the request."""
    use_case = GetWebAppManifest(
        InMemoryAccessGuard(), public_origin="https://menagerist.example.com"
    )

    manifest = await use_case.handle(GetWebAppManifestQuery(), SYSTEM_ACTOR)

    assert manifest.origin == "https://menagerist.example.com"


async def test_manifest_without_a_public_origin_has_none() -> None:
    """With no origin configured the manifest's URLs stay relative."""
    use_case = GetWebAppManifest(InMemoryAccessGuard(), public_origin=None)

    manifest = await use_case.handle(GetWebAppManifestQuery(), SYSTEM_ACTOR)

    assert manifest.origin is None


def test_manifest_is_public() -> None:
    """Browsers fetch the manifest without credentials."""
    assert GetWebAppManifest.access == Public()
