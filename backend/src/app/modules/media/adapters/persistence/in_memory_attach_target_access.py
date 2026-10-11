from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid

    from app.modules.media.domain.media_attachment import AttachmentTarget
    from app.shared_kernel.access_scope import AccessScope


class InMemoryAttachTargetAccess:
    """Dict-backed `AttachTargetAccess` for tests: only registered targets exist."""

    def __init__(self) -> None:
        self._owners: dict[tuple[AttachmentTarget, uuid.UUID], uuid.UUID | None] = {}

    def add_target(
        self,
        target_type: AttachmentTarget,
        target_id: uuid.UUID,
        owner_id: uuid.UUID | None,
    ) -> None:
        """Register a target and its owner."""
        self._owners[(target_type, target_id)] = owner_id

    async def can_attach(
        self, target_type: AttachmentTarget, target_id: uuid.UUID, scope: AccessScope
    ) -> bool:
        """Whether the target is registered and its owner is inside `scope`."""
        key = (target_type, target_id)
        return key in self._owners and scope.covers(self._owners[key])
