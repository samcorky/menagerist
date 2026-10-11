import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.modules.examples.domain.errors import RequirementsNotMetError
from app.modules.examples.domain.installation import (
    EntityKind,
    EntityRecord,
    Installation,
    InstallationStatus,
)
from app.modules.examples.domain.removal import holds_shared_type

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.modules.examples.domain.pack import ExamplePack
    from app.modules.examples.ports.pack_catalogue import PackCatalogue
    from app.modules.examples.ports.pack_targets import GraphTarget


@dataclass(kw_only=True, frozen=True, eq=False)
class ResolvedRef:
    """A live entity of a required pack: its id, and its slug or name."""

    entity_id: uuid.UUID
    slug: str | None = None
    name: str | None = None


ResolvedRefs = dict[tuple[EntityKind, str, str], ResolvedRef]


async def resolve_external_refs(
    pack: ExamplePack,
    active_installations: Sequence[Installation],
    graph: GraphTarget,
    catalogue: PackCatalogue,
    others: Sequence[Installation] = (),
) -> ResolvedRefs:
    """Find the live entity behind every `pack:ref` the add-on uses.

    Each required pack must be installed and finished, and each entity it is
    referenced for must still be owned by that pack and exist. Nothing is created.

    Types are shared structure: when this person's own installation reused a type
    another person's installation of the pack created, `others` (other people's
    installations) supplies its record.

    Raises:
        RequirementsNotMetError: a required pack is not installed, or no longer
            has something the add-on refers to.
    """
    names = {s.id: s.name for s in await catalogue.list_packs()}
    finished = {
        i.pack_id: i
        for i in active_installations
        if i.status is InstallationStatus.INSTALLED
    }
    for required in pack.requires:
        if required not in finished:
            raise RequirementsNotMetError(f"Add {names[required]} first.")

    resolved: ResolvedRefs = {}
    for key in sorted(pack.external_refs()):
        kind, pack_id, ref = key
        installation = finished[pack_id]
        record = next(
            (r for r in installation.owned(kind) if r.ref == ref),
            None,
        ) or _shared_record(others, kind, pack_id, ref)
        inspection = (
            None if record is None else await graph.inspect(kind, record.entity_id)
        )
        if record is None or inspection is None:
            label = next(
                (
                    r.label
                    for r in installation.entities
                    if (r.kind, r.ref) == (kind, ref)
                ),
                ref,
            )
            raise RequirementsNotMetError(f"{names[pack_id]} no longer has {label}.")
        resolved[key] = ResolvedRef(
            entity_id=record.entity_id,
            slug=inspection.content.get("slug"),
            name=inspection.content.get("name"),
        )
    return resolved


def _shared_record(
    others: Sequence[Installation], kind: EntityKind, pack_id: str, ref: str
) -> EntityRecord | None:
    """Return another person's record of the shared type `ref` of `pack_id`."""
    return next(
        (
            r
            for i in others
            if i.pack_id == pack_id
            for r in i.entities
            if (r.kind, r.ref) == (kind, ref) and holds_shared_type(i, r)
        ),
        None,
    )
