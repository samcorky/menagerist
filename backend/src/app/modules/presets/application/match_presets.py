from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from app.modules.presets.application.import_presets import existing_hashes
from app.modules.presets.application.pack import content_hash
from app.modules.presets.application.permissions import PresetPermission
from app.modules.presets.ports.unit_of_work import PresetRepos
from app.shared_kernel.access import Access, Content
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class MatchPresetsQuery:
    """Pack items (`kind`, `label`, `definition`) to look for in the actor's presets."""

    items: list[dict[str, Any]]


class MatchPresets(QueryHandler[PresetRepos, MatchPresetsQuery, list[bool]]):
    """Report, per item, whether the actor already has an identical preset."""

    access: ClassVar[Access] = Content(PresetPermission.PRESET_READ)

    async def _handle(self, query: MatchPresetsQuery, actor: Actor) -> list[bool]:
        """Return one flag per item, in order; nothing is created."""
        if not query.items:
            return []
        seen = await existing_hashes(self._repos.presets, self.scope(actor))
        return [
            content_hash(i["kind"], i["label"], i["definition"]) in seen
            for i in query.items
        ]
