from typing import TYPE_CHECKING

from app.modules.transfer.domain.entity_kind import EntityKind

if TYPE_CHECKING:
    from collections.abc import Iterable

    from app.modules.transfer.application.removal import KeptEntity


def reported_kept(kept: Iterable[KeptEntity]) -> list[KeptEntity]:
    """The kept entities a removal reports.

    A kept cover is settled and recorded but not reported: the person sees the item
    that holds it, and covers are not something a pack lists or counts.
    """
    return [k for k in kept if k.kind is not EntityKind.COVER]
