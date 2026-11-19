from app.modules.system.application.get_web_app_manifest import (
    GetWebAppManifest,
    GetWebAppManifestQuery,
)
from app.modules.system.domain.branding import Branding
from app.shared_kernel.access import Public
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import SYSTEM_ACTOR

APP = Branding(description="An app.")


async def test_manifest_carries_the_configured_public_origin() -> None:
    """The origin comes from configuration, never from the request."""
    use_case = GetWebAppManifest(
        InMemoryAccessGuard(),
        branding=APP,
        public_origin="https://menagerist.example.com",
    )

    manifest = await use_case.handle(GetWebAppManifestQuery(), SYSTEM_ACTOR)

    assert manifest.origin == "https://menagerist.example.com"


async def test_manifest_without_a_public_origin_has_none() -> None:
    """With no origin configured the manifest's URLs stay relative."""
    use_case = GetWebAppManifest(
        InMemoryAccessGuard(), branding=APP, public_origin=None
    )

    manifest = await use_case.handle(GetWebAppManifestQuery(), SYSTEM_ACTOR)

    assert manifest.origin is None


async def test_manifest_carries_the_branding_it_is_given() -> None:
    """Name and description come from the branding the builder supplies."""
    branding = Branding(
        name="The Hoard",
        short_name="Hoard",
        description="Our family's things.",
    )
    use_case = GetWebAppManifest(
        InMemoryAccessGuard(), branding=branding, public_origin=None
    )

    manifest = await use_case.handle(GetWebAppManifestQuery(), SYSTEM_ACTOR)

    assert (manifest.name, manifest.short_name) == ("The Hoard", "Hoard")
    assert manifest.description == "Our family's things."


def test_manifest_is_public() -> None:
    """Browsers fetch the manifest without credentials."""
    assert GetWebAppManifest.access == Public()
