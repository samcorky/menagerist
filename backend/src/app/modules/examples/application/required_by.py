from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Collection, Sequence

    from app.modules.examples.domain.pack import PackSummary


def dependants_by_pack(
    packs: Sequence[PackSummary], active_pack_ids: Collection[str]
) -> dict[str, list[PackSummary]]:
    """Map each pack id to the active add-ons that require it, in catalogue order.

    Active ids that are not in `packs` are ignored.
    """
    dependants: dict[str, list[PackSummary]] = defaultdict(list)
    for summary in packs:
        if summary.id in active_pack_ids:
            for required in summary.requires:
                dependants[required].append(summary)
    return dict(dependants)
