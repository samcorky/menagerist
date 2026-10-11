import uuid

from app.modules.media.adapters.persistence.in_memory_attach_target_access import (
    InMemoryAttachTargetAccess,
)
from app.modules.media.domain.media_attachment import AttachmentTarget
from app.shared_kernel.access_scope import AccessScope

ALICE = uuid.UUID(int=101)
BOB = uuid.UUID(int=102)


async def test_only_registered_targets_inside_the_scope_can_be_attached() -> None:
    """A target needs to exist and be owned inside the scope."""
    access = InMemoryAttachTargetAccess()
    target_id = uuid.uuid7()
    access.add_target(AttachmentTarget.NODE, target_id, ALICE)

    node = AttachmentTarget.NODE
    assert await access.can_attach(node, target_id, AccessScope.of(ALICE))
    assert await access.can_attach(node, target_id, AccessScope.everyone())
    assert not await access.can_attach(node, target_id, AccessScope.of(BOB))
    assert not await access.can_attach(
        AttachmentTarget.EDGE, target_id, AccessScope.of(ALICE)
    )
    assert not await access.can_attach(node, uuid.uuid7(), AccessScope.everyone())
