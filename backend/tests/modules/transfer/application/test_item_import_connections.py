"""Importing a CSV whose columns name other items each row connects to."""

import uuid
from dataclasses import replace
from typing import TYPE_CHECKING, Any

import pytest

from app.modules.transfer.adapters.persistence.in_memory_import_repository import (
    InMemoryItemImportRepository,
)
from app.modules.transfer.adapters.persistence.in_memory_source_link_repository import (
    InMemorySourceLinkRepository,
)
from app.modules.transfer.application import item_import
from app.modules.transfer.application.item_import import (
    ImportItems,
    ItemImportRequest,
    PlanItemImport,
)
from app.modules.transfer.domain.bundle import (
    BundleItem,
    BundleItemType,
    BundleRelationshipType,
    NameLookup,
)
from app.modules.transfer.domain.entity_kind import EntityKind
from app.modules.transfer.domain.errors import InvalidImportFileError
from app.modules.transfer.domain.plan import Plan, PlanAction, PlannedEntity
from app.modules.transfer.domain.tabular import (
    ColumnMapping,
    ConnectionColumn,
    ConnectionEnd,
)
from app.modules.transfer.ports.unit_of_work import TransferRepos
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import Actor
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork

if TYPE_CHECKING:
    from app.modules.transfer.application.pipeline import AppliedBundle
    from tests.modules.conftest import Shared, Targets

ALICE = Actor(id=uuid.UUID(int=0xA1), roles=frozenset({"member"}))
HEADER = "code,title,signer,where\n"
MAPPING = (
    ColumnMapping(column="code", target="code"),
    ColumnMapping(column="title", target="name"),
)
CODE: dict[str, Any] = {
    "type": "object",
    "properties": {"code": {"type": "string", "title": "Code"}},
}
BORN: dict[str, Any] = {
    "type": "object",
    "properties": {"born": {"type": "string", "title": "Born"}},
    "required": ["born"],
}


def _where(**over: Any) -> ConnectionColumn:  # noqa: ANN401
    fields: dict[str, Any] = {
        "column": "where",
        "relationship_type": "obtained-at",
        "item_type": "place",
        "row_end": ConnectionEnd.SOURCE,
    }
    return ConnectionColumn(**(fields | over))


def _signer(**over: Any) -> ConnectionColumn:  # noqa: ANN401
    fields: dict[str, Any] = {
        "column": "signer",
        "relationship_type": "signed",
        "item_type": "person",
        "row_end": ConnectionEnd.TARGET,
    }
    return ConnectionColumn(**(fields | over))


class World:
    """Alice's targets, with a signature type, people, places and their links."""

    def __init__(self, t: Targets) -> None:
        self.t = t
        self.repos = TransferRepos(
            links=InMemorySourceLinkRepository(), imports=InMemoryItemImportRepository()
        )

    async def plan(self, request: ItemImportRequest) -> Plan:
        """Plan `request` as Alice."""
        use_case = PlanItemImport(
            self.repos, InMemoryAccessGuard(), self.t.presets, self.t.graph
        )
        return await use_case.handle(request, ALICE)

    async def run(self, request: ItemImportRequest) -> AppliedBundle:
        """Import `request` as Alice."""
        uow = InMemoryUnitOfWork(self.repos)
        use_case = ImportItems(uow, InMemoryAccessGuard(), self.t.presets, self.t.graph)
        return await use_case.handle(request, ALICE)

    async def named(self, item_type: str, name: str) -> list[uuid.UUID]:
        """Alice's items of `item_type` called `name`, in any case."""
        return await self.t.graph.find_items_by_field(
            item_type, "name", name, limit=5, ignore_case=True
        )


async def _world(shared: Shared, *, person: dict[str, Any] | None = None) -> World:
    t = shared.targets(ALICE)
    for ref, schema in (("signature", CODE), ("person", person), ("place", None)):
        await t.graph.create_item_type(
            BundleItemType(
                ref=ref, slug=ref, label=ref.title(), attributes_schema=schema
            ),
            {},
        )
    for slug in ("obtained-at", "signed"):
        await t.graph.create_relationship_type(
            BundleRelationshipType(ref=slug, slug=slug, label=slug), {}
        )
    return World(t)


def _request(
    body: str,
    *connections: ConnectionColumn,
    key_field: str | None = "code",
    mapping: tuple[ColumnMapping, ...] = MAPPING,
) -> ItemImportRequest:
    return ItemImportRequest(
        data=(HEADER + body).encode(),
        item_type="signature",
        mapping=mapping,
        key_field=key_field,
        connections=connections,
    )


def _of(plan: Plan, kind: EntityKind) -> list[PlannedEntity]:
    return [e for e in plan.entities if e.kind is kind]


async def test_a_column_connects_each_row_to_the_named_item(shared: Shared) -> None:
    """Each row is joined to the place its Where cell names, created if missing."""
    world = await _world(shared)

    plan = await world.plan(_request("A1,Photo,,Comic Con\n", _where()))
    applied = await world.run(_request("A1,Photo,,Comic Con\n", _where()))

    assert [(e.label, e.action) for e in _of(plan, EntityKind.CONNECTION)] == [
        ("Photo to Comic Con", PlanAction.CREATE)
    ]
    assert applied.created[EntityKind.CONNECTION] == 1
    assert len(await world.named("place", "Comic Con")) == 1


async def test_the_row_can_be_the_target(shared: Shared) -> None:
    """With the row as the target, the named item is the connection's source."""
    world = await _world(shared)

    plan = await world.plan(_request("A1,Photo,Mark Hamill,\n", _signer()))

    assert [e.label for e in _of(plan, EntityKind.CONNECTION)] == [
        "Mark Hamill to Photo"
    ]


async def test_names_differing_in_case_and_spaces_make_one_item(
    shared: Shared,
) -> None:
    """eBay, ' eBay ' and ebay are one place, created once with the first spelling."""
    world = await _world(shared)
    body = "A1,Photo,,eBay\nA2,Card,, eBay \nA3,Print,,ebay\n"

    plan = await world.plan(_request(body, _where()))
    applied = await world.run(_request(body, _where()))

    places = [e for e in _of(plan, EntityKind.ITEM) if e.ref.startswith("named-")]
    assert [(e.label, e.action) for e in places] == [("eBay", PlanAction.CREATE)]
    assert applied.created[EntityKind.ITEM] == 4
    assert applied.created[EntityKind.CONNECTION] == 3


async def test_an_empty_cell_makes_no_connection(shared: Shared) -> None:
    """A row with nothing in the column is imported without a connection."""
    world = await _world(shared)

    plan = await world.plan(_request("A1,Photo,, \nA2,Card,,eBay\n", _where()))

    assert [e.label for e in _of(plan, EntityKind.CONNECTION)] == ["Card to eBay"]


async def test_a_column_can_be_the_name_and_a_connection(shared: Shared) -> None:
    """The column that names the row can also name the item it connects to."""
    world = await _world(shared)
    mapping = (ColumnMapping(column="title", target="name"),)

    plan = await world.plan(
        _request(
            "A1,Mark Hamill,,\n",
            _signer(column="title"),
            key_field=None,
            mapping=mapping,
        )
    )

    assert [e.label for e in _of(plan, EntityKind.CONNECTION)] == [
        "Mark Hamill to Mark Hamill"
    ]


async def test_a_missing_column_is_refused(shared: Shared) -> None:
    """A connection column the file does not have is refused."""
    world = await _world(shared)

    with pytest.raises(InvalidImportFileError, match="no column 'venue'"):
        await world.plan(_request("A1,Photo,,\n", _where(column="venue")))


async def test_more_than_five_connection_columns_are_refused(shared: Shared) -> None:
    """At most five columns connect."""
    world = await _world(shared)

    with pytest.raises(InvalidImportFileError, match=r"^Connect at most 5 columns\.$"):
        await world.plan(_request("A1,Photo,,\n", *([_where()] * 6)))


async def test_an_unknown_relationship_type_is_refused(shared: Shared) -> None:
    """A relationship type the person does not have is refused."""
    world = await _world(shared)

    with pytest.raises(
        InvalidImportFileError, match=r"^You have no relationship type called 'x'\.$"
    ):
        await world.plan(_request("A1,Photo,,\n", _where(relationship_type="x")))


async def test_an_unknown_other_item_type_is_refused(shared: Shared) -> None:
    """An item type for the other end the person does not have is refused."""
    world = await _world(shared)

    with pytest.raises(
        InvalidImportFileError, match=r"^You have no item type called 'venue'\.$"
    ):
        await world.plan(_request("A1,Photo,,\n", _where(item_type="venue")))


async def test_a_bare_item_of_a_type_with_required_fields_is_created(
    shared: Shared,
) -> None:
    """A type's required fields are advisory, so a name alone makes the person."""
    world = await _world(shared, person=BORN)

    applied = await world.run(_request("A1,Photo,Dave Prowse,\n", _signer()))

    assert applied.created[EntityKind.ITEM] == 2
    assert len(await world.named("person", "Dave Prowse")) == 1


async def test_a_required_field_does_not_block_finding_an_item(
    shared: Shared,
) -> None:
    """A person you already have is used, whatever fields a new one would need."""
    world = await _world(shared, person=BORN)
    await world.run(_request("A1,Photo,,\n"))
    await world.t.graph.create_item(
        BundleItem(
            ref="x", type_ref="person", name="Dave Prowse", attributes={"born": "1935"}
        ),
        type_slug="person",
    )

    plan = await world.plan(_request("A1,Photo,dave prowse,\n", _signer()))

    assert plan.ready


async def test_more_created_items_than_allowed_block(
    shared: Shared, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rows and the items they name together may not pass the row limit."""
    monkeypatch.setattr(item_import, "MAX_IMPORT_ROWS", 2)
    world = await _world(shared)

    plan = await world.plan(_request("A1,Photo,,Comic Con\nA2,Card,,eBay\n", _where()))

    assert [b.reason for b in plan.blockers] == [
        "This import would create more than 2 items."
    ]


async def test_the_plan_leaves_out_types_and_relationship_types(
    shared: Shared,
) -> None:
    """The types and relationship types the import builds on are not listed."""
    world = await _world(shared)

    plan = await world.plan(
        _request("A1,Photo,Mark Hamill,eBay\n", _where(), _signer())
    )

    kinds = {e.kind for e in plan.entities}
    assert kinds == {EntityKind.ITEM, EntityKind.CONNECTION}


async def test_a_column_that_skips_missing_names_creates_none(
    shared: Shared,
) -> None:
    """With skip, a name you have no item for is left out, and so is its connection."""
    world = await _world(shared)

    applied = await world.run(
        _request("A1,Photo,,Comic Con\n", _where(on_missing=NameLookup.SKIP))
    )

    assert applied.created[EntityKind.ITEM] == 1
    assert await world.named("place", "Comic Con") == []


async def test_re_import_adds_only_missing_connections(shared: Shared) -> None:
    """A second run adds the connections the file now has, and nothing twice."""
    world = await _world(shared)
    await world.run(_request("A1,Photo,,eBay\n", _where()))

    plan = await world.plan(
        _request("A1,Photo,Mark Hamill,eBay\n", _where(), _signer())
    )
    applied = await world.run(
        _request("A1,Photo,Mark Hamill,eBay\n", _where(), _signer())
    )

    assert [(e.label, e.action) for e in _of(plan, EntityKind.CONNECTION)] == [
        ("Photo to eBay", PlanAction.UNCHANGED),
        ("Mark Hamill to Photo", PlanAction.CREATE),
    ]
    assert applied.created[EntityKind.CONNECTION] == 1
    assert applied.created[EntityKind.ITEM] == 1


async def test_a_deleted_connection_stays_deleted_and_can_be_restored(
    shared: Shared,
) -> None:
    """The connection's key is the row key, the column and the name as written."""
    world = await _world(shared)
    await world.run(_request("A1,Photo,,eBay\n", _where()))
    plan = await world.plan(_request("A1,Photo,,eBay\n", _where()))
    (connection,) = _of(plan, EntityKind.CONNECTION)
    key = "A1\x1fwhere\x1febay"
    link = await world.repos.links.get_by_key(
        "csv:signature:code",
        EntityKind.CONNECTION,
        key,
        scope=ContentFilter.of(ALICE.id),
    )
    assert link is not None
    await world.t.graph.remove(EntityKind.CONNECTION, link.entity_id)

    kept = await world.plan(_request("A1,Photo,,EBAY\n", _where()))
    restored = await world.run(
        replace(_request("A1,Photo,,eBay\n", _where()), restore=(key,))
    )

    assert connection.source_key == key
    assert _of(kept, EntityKind.CONNECTION)[0].reason == (
        "You deleted this after importing it."
    )
    assert restored.created[EntityKind.CONNECTION] == 1
