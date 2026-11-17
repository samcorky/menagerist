from datetime import UTC, datetime

import pytest

from app.modules.identity.domain.avatar import (
    AVATAR_SIZES,
    MAX_AVATAR_BYTES,
    Avatar,
    AvatarSource,
    CropSquare,
)
from app.modules.identity.domain.errors import InvalidAvatarError
from app.modules.identity.domain.user import User

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)


def _user() -> User:
    return User.create(
        username="alice", display_name="Alice", password_hash="fake$x", now=NOW
    )


def _avatar(version: str = "0123456789abcdef") -> Avatar:
    return Avatar(version=version, source=AvatarSource.UPLOAD, updated_at=NOW)


def test_limits_match_the_spec() -> None:
    """Pictures come in three sizes and uploads stop at 5 MB."""
    assert AVATAR_SIZES == (64, 128, 256)
    assert MAX_AVATAR_BYTES == 5 * 1024 * 1024


def test_crop_square_accepts_origin() -> None:
    """A crop at the top-left corner is valid."""
    assert CropSquare(x=0, y=0, size=1).size == 1


@pytest.mark.parametrize(("x", "y"), [(-1, 0), (0, -1)])
def test_crop_square_rejects_negative_offset(x: int, y: int) -> None:
    """A crop cannot start left of or above the image."""
    with pytest.raises(InvalidAvatarError):
        CropSquare(x=x, y=y, size=10)


def test_crop_square_rejects_zero_size() -> None:
    """A crop must cover at least one pixel."""
    with pytest.raises(InvalidAvatarError):
        CropSquare(x=0, y=0, size=0)


def test_new_user_has_no_avatar() -> None:
    """Accounts start with the initials default."""
    assert _user().avatar is None


def test_set_avatar_stores_and_touches() -> None:
    """Setting a picture records it and bumps `updated_at`."""
    user = _user()
    user.set_avatar(_avatar())
    assert user.avatar == _avatar()
    assert user.updated_at > NOW


def test_clear_avatar_removes_it() -> None:
    """Clearing returns to the initials default and bumps `updated_at`."""
    user = _user()
    user.set_avatar(_avatar())
    user.updated_at = NOW
    user.clear_avatar()
    assert user.avatar is None
    assert user.updated_at > NOW
