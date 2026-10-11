import uuid

from app.modules.media.adapters.persistence.in_memory_media_asset_repository import (
    InMemoryMediaAssetRepository,
)
from app.modules.media.adapters.persistence.unit_of_work import (
    create_in_memory_media_uow,
    make_in_memory_repos,
)
from app.modules.media.application.claim_orphaned_media import (
    ClaimOrphanedMedia,
    ClaimOrphanedMediaCommand,
)
from app.modules.media.domain.media_asset import MediaAsset
from app.shared_kernel.actor import SYSTEM_ACTOR


async def test_claims_system_owned_assets_and_commits() -> None:
    """System-owned assets move to the new owner; another user's stay."""
    assets = InMemoryMediaAssetRepository()
    uow = create_in_memory_media_uow(make_in_memory_repos(assets=assets))
    mine = MediaAsset.create(
        owner_id=SYSTEM_ACTOR.id,
        filename="a.jpg",
        content_type="image/jpeg",
        size=1,
        sha256="x",
    )
    theirs = MediaAsset.create(
        owner_id=uuid.uuid7(),
        filename="b.jpg",
        content_type="image/jpeg",
        size=1,
        sha256="y",
    )
    await assets.add(mine)
    await assets.add(theirs)
    owner = uuid.uuid7()

    count = await ClaimOrphanedMedia(uow).handle(
        ClaimOrphanedMediaCommand(owner_id=owner), SYSTEM_ACTOR
    )

    assert count == 1
    assert mine.owner_id == owner
    assert theirs.owner_id != owner
    assert getattr(uow, "committed", False)
