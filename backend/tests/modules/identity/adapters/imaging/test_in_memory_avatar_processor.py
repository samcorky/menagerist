import pytest

from app.modules.identity.adapters.imaging.in_memory_avatar_processor import (
    InMemoryAvatarProcessor,
)
from app.modules.identity.domain.avatar import AVATAR_SIZES, CropSquare
from app.modules.identity.domain.errors import InvalidAvatarError


async def test_versions_follow_input_and_record_crops() -> None:
    """Different bytes give different versions; every size is filled in."""
    processor = InMemoryAvatarProcessor()
    crop = CropSquare(x=1, y=2, size=3)
    first = await processor.process(b"one", crop=crop)
    second = await processor.process(b"two", crop=None)
    assert first.version != second.version
    assert set(first.images) == set(AVATAR_SIZES)
    assert processor.crops == [crop, None]


async def test_fail_next_refuses_once() -> None:
    """`fail_next` refuses one call, then processing works again."""
    processor = InMemoryAvatarProcessor()
    processor.fail_next = True
    with pytest.raises(InvalidAvatarError):
        await processor.process(b"x", crop=None)
    assert (await processor.process(b"x", crop=None)).version
