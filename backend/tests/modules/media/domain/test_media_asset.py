import pytest

from app.modules.media.domain.media_asset import MediaAsset, MediaStatus
from app.shared_kernel.errors import ValidationError


def test_create_sets_fields_and_staged_status() -> None:
    """MediaAsset.create sets all fields and defaults status to STAGED."""
    asset = MediaAsset.create(
        filename="cover.jpg",
        content_type="image/jpeg",
        size=1024,
        sha256="abc123",
    )

    assert asset.filename == "cover.jpg"
    assert asset.content_type == "image/jpeg"
    assert asset.size == 1024
    assert asset.sha256 == "abc123"
    assert asset.status is MediaStatus.STAGED
    assert asset.created_at == asset.updated_at


def test_create_with_explicit_asset_id_uses_it() -> None:
    """MediaAsset.create with asset_id uses the caller-supplied id."""
    import uuid

    asset_id = uuid.uuid7()
    asset = MediaAsset.create(
        asset_id=asset_id,
        filename="photo.png",
        content_type="image/png",
        size=512,
        sha256="def456",
    )

    assert asset.id == asset_id


def test_create_without_asset_id_generates_one() -> None:
    """MediaAsset.create without asset_id generates a uuid."""
    asset = MediaAsset.create(
        filename="photo.png",
        content_type="image/png",
        size=512,
        sha256="def456",
    )

    assert asset.id is not None


@pytest.mark.parametrize("filename", ["", "   "])
def test_create_rejects_empty_filename(filename: str) -> None:
    """MediaAsset.create raises ValidationError for empty or blank filename."""
    with pytest.raises(ValidationError, match="filename must be provided"):
        MediaAsset.create(
            filename=filename,
            content_type="image/jpeg",
            size=1024,
            sha256="abc",
        )


def test_promote_transitions_staged_to_attached() -> None:
    """promote() changes status from STAGED to ATTACHED and updates updated_at."""
    asset = MediaAsset.create(
        filename="f.jpg", content_type="image/jpeg", size=1, sha256="x"
    )
    original_updated_at = asset.updated_at

    asset.promote()

    assert asset.status is MediaStatus.ATTACHED
    assert asset.updated_at >= original_updated_at


def test_promote_raises_if_already_attached() -> None:
    """promote() raises ValidationError if the asset is not staged."""
    asset = MediaAsset.create(
        filename="f.jpg", content_type="image/jpeg", size=1, sha256="x"
    )
    asset.promote()

    with pytest.raises(ValidationError, match="cannot promote"):
        asset.promote()


def test_promote_raises_if_orphaned() -> None:
    """promote() raises ValidationError if the asset is orphaned."""
    asset = MediaAsset.create(
        filename="f.jpg", content_type="image/jpeg", size=1, sha256="x"
    )
    asset.promote()
    asset.orphan()

    with pytest.raises(ValidationError, match="cannot promote"):
        asset.promote()


def test_orphan_transitions_attached_to_orphaned() -> None:
    """orphan() changes status from ATTACHED to ORPHANED and updates updated_at."""
    asset = MediaAsset.create(
        filename="f.jpg", content_type="image/jpeg", size=1, sha256="x"
    )
    asset.promote()
    original_updated_at = asset.updated_at

    asset.orphan()

    assert asset.status is MediaStatus.ORPHANED
    assert asset.updated_at >= original_updated_at


def test_orphan_raises_if_staged() -> None:
    """orphan() raises ValidationError if the asset is staged."""
    asset = MediaAsset.create(
        filename="f.jpg", content_type="image/jpeg", size=1, sha256="x"
    )

    with pytest.raises(ValidationError, match="cannot orphan"):
        asset.orphan()


def test_mark_thumbnail_generated_sets_flag_and_hash() -> None:
    """mark_thumbnail_generated sets has_thumbnail and stores the thumbnail's hash."""
    asset = MediaAsset.create(
        filename="f.jpg", content_type="image/jpeg", size=1, sha256="original-hash"
    )

    asset.mark_thumbnail_generated(sha256="thumbnail-hash")

    assert asset.has_thumbnail is True
    assert asset.thumbnail_sha256 == "thumbnail-hash"
    assert asset.thumbnail_sha256 != asset.sha256


def test_orphan_raises_if_already_orphaned() -> None:
    """orphan() raises ValidationError if the asset is already orphaned."""
    asset = MediaAsset.create(
        filename="f.jpg", content_type="image/jpeg", size=1, sha256="x"
    )
    asset.promote()
    asset.orphan()

    with pytest.raises(ValidationError, match="cannot orphan"):
        asset.orphan()
