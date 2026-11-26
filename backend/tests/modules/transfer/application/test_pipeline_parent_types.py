"""A type's parent travels with it through import, export and its content (#770)."""

import uuid
from typing import TYPE_CHECKING

from app.modules.transfer.application.pipeline import apply_bundle, plan_bundle
from app.modules.transfer.domain.bundle import Bundle, BundleItemType
from app.modules.transfer.domain.plan import ClashPolicy
from app.shared_kernel.actor import Actor
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.paging import PageRequest

if TYPE_CHECKING:
    from tests.modules.conftest import Shared, Targets

ALICE = Actor(id=uuid.UUID(int=0xA1), roles=frozenset({"member"}))
BOB = Actor(id=uuid.UUID(int=0xB2), roles=frozenset({"member"}))
MEMO = BundleItemType(
    ref="memo",
    slug="memorabilia",
    label="Memorabilia",
    attributes_schema={
        "type": "object",
        "properties": {"condition": {"type": "string"}},
    },
)
POSTER = BundleItemType(
    ref="poster",
    slug="poster",
    label="Poster",
    parent="memo",
    attributes_schema={"type": "object", "properties": {"width": {"type": "string"}}},
)


async def _import(t: Targets, *item_types: BundleItemType) -> None:
    bundle = Bundle(id="b", item_types=item_types)
    plan = await plan_bundle(bundle, t.presets, t.graph, clash=ClashPolicy.SKIP)
    await apply_bundle(plan, bundle, t.presets, t.graph)


async def _parents(shared: Shared, actor: Actor) -> dict[str, str | None]:
    """Each of the person's item types by slug, with its parent's slug."""
    scope = ContentFilter(user_id=actor.id)
    found = (
        await shared.graph_repos.node_types.list(
            scope=scope, page=PageRequest(limit=50)
        )
    ).items
    return {str(t.slug): t.parent for t in found}


async def test_a_parent_is_created_before_its_subtype_whatever_the_order(
    shared: Shared,
) -> None:
    """A subtype listed first still lands under a parent made first."""
    await _import(shared.targets(ALICE), POSTER, MEMO)

    assert await _parents(shared, ALICE) == {
        "memorabilia": None,
        "poster": "memorabilia",
    }


async def test_a_subtype_joins_a_parent_the_person_already_has(
    shared: Shared,
) -> None:
    """A taken parent is kept as it is, and the new subtype goes beneath it."""
    t = shared.targets(ALICE)
    await t.graph.create_item_type(MEMO, {})

    await _import(t, MEMO, POSTER)

    assert await _parents(shared, ALICE) == {
        "memorabilia": None,
        "poster": "memorabilia",
    }


async def test_exporting_a_subtype_brings_its_parent_so_the_file_stands_alone(
    shared: Shared,
) -> None:
    """The file holds the parent and names it by ref, and imports for someone else."""
    alice = shared.targets(ALICE)
    await _import(alice, MEMO, POSTER)
    poster = next(
        t
        for t in (
            await shared.graph_repos.node_types.list(
                scope=ContentFilter(user_id=ALICE.id), page=PageRequest(limit=50)
            )
        ).items
        if str(t.slug) == "poster"
    )

    read = await alice.graph.read_item_types([poster.id])

    assert sorted((t.slug, t.parent is not None) for t in read) == [
        ("memorabilia", False),
        ("poster", True),
    ]
    by_ref = {t.ref: t for t in read}
    subtype = next(t for t in read if t.slug == "poster")
    assert subtype.parent is not None
    assert by_ref[subtype.parent].slug == "memorabilia"
    await _import(shared.targets(BOB), *read)
    assert await _parents(shared, BOB) == {"memorabilia": None, "poster": "memorabilia"}


async def test_a_created_type_records_its_parent_only_when_it_has_one(
    shared: Shared,
) -> None:
    """The content kept for edit detection gains `parent` only for a subtype."""
    t = shared.targets(ALICE)

    top = await t.graph.create_item_type(MEMO, {})
    sub = await t.graph.create_item_type(POSTER, {}, parent_slug="memorabilia")

    assert "parent" not in top.content
    assert sub.content["parent"] == "memorabilia"
