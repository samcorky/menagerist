from typing import TYPE_CHECKING

import structlog

from app.modules.examples.application.content_hash import content_hash
from app.modules.examples.domain.installation import EntityKind, Installation
from app.modules.examples.domain.pack import ExamplePack, PackConnection, split_ref

if TYPE_CHECKING:
    import uuid
    from collections.abc import Awaitable, Callable

    from app.modules.examples.domain.pack import PackLink
    from app.modules.examples.ports.pack_targets import GraphTarget

logger = structlog.get_logger()


def link_ref(with_pack: str, index: int) -> str:
    """Return the record ref of the `index`th link, which removal matches by prefix."""
    return f"link:{with_pack}:{index}"


async def apply_links(
    *,
    declaring_pack: ExamplePack,
    declaring: Installation,
    other: Installation,
    graph: GraphTarget,
    persist: Callable[[Installation], Awaitable[None]],
) -> int:
    """Create the links `declaring_pack` declares with the pack `other` installed.

    Each link is an ordinary connection, recorded in `declaring`. A link is skipped,
    quietly, when an end no longer exists, when it was already applied, or when the
    same connection is already there. A failure is logged and the link skipped: the
    packs themselves are installed and links are optional.

    Returns:
        How many links were created.
    """
    created = 0
    for index, link in enumerate(declaring_pack.links):
        if link.with_pack != other.pack_id:
            continue
        try:
            if await _apply_one(
                declaring_pack, declaring, other, link, index, graph, persist
            ):
                created += 1
        except Exception:
            logger.exception(
                "example pack link failed",
                pack_id=declaring_pack.id,
                with_pack=link.with_pack,
                link=index,
            )
    return created


async def _apply_one(
    pack: ExamplePack,
    declaring: Installation,
    other: Installation,
    link: PackLink,
    index: int,
    graph: GraphTarget,
    persist: Callable[[Installation], Awaitable[None]],
) -> bool:
    ref = link_ref(link.with_pack, index)
    if any(r.ref == ref for r in declaring.owned(EntityKind.CONNECTION)):
        return False
    source = await _end(link.source_ref, declaring, other, graph)
    target = await _end(link.target_ref, declaring, other, graph)
    if source is None or target is None:
        return False
    slug = next(t.slug for t in pack.relationship_types if t.ref == link.type_ref)
    if await graph.connection_exists(source[0], target[0], slug):
        return False
    created = await graph.create_connection(
        PackConnection(
            source_ref=link.source_ref,
            target_ref=link.target_ref,
            type_ref=link.type_ref,
            attributes=link.attributes,
        ),
        source_id=source[0],
        target_id=target[0],
        type_slug=slug,
    )
    declaring.record_late(
        EntityKind.CONNECTION,
        ref,
        f"{source[1]} to {target[1]}",
        created.entity_id,
        content_hash(created.content),
    )
    await persist(declaring)
    return True


async def _end(
    ref: str, declaring: Installation, other: Installation, graph: GraphTarget
) -> tuple[uuid.UUID, str] | None:
    """Return the live item's id and name behind a link end, or None if it is gone."""
    pack_id, local = split_ref(ref)
    installation = declaring if pack_id is None else other
    record = next(
        (r for r in installation.owned(EntityKind.ITEM) if r.ref == local), None
    )
    if record is None:
        return None
    found = await graph.inspect(EntityKind.ITEM, record.entity_id)
    if found is None:
        return None
    return record.entity_id, str(found.content["name"])
