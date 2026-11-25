"""Importing a CSV again: rows recognised by a key column are not created twice."""

import uuid
from typing import TYPE_CHECKING, Any

import pytest

from app.modules.transfer.adapters.persistence.in_memory_import_repository import (
    InMemoryItemImportRepository,
)
from app.modules.transfer.adapters.persistence.in_memory_source_link_repository import (
    InMemorySourceLinkRepository,
)
from app.modules.transfer.application.item_import import (
    ImportItems,
    ItemImportRequest,
    PlanItemImport,
)
from app.modules.transfer.domain.bundle import BundleItemType
from app.modules.transfer.domain.entity_kind import EntityKind
from app.modules.transfer.domain.errors import InvalidImportFileError
from app.modules.transfer.domain.plan import Plan, PlanAction, PlannedEntity
from app.modules.transfer.domain.tabular import (
    ColumnMapping,
    ExtraField,
    ExtraFieldKind,
)
from app.modules.transfer.ports.unit_of_work import TransferRepos
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import Actor
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork

if TYPE_CHECKING:
    from tests.modules.conftest import Shared, Targets

ALICE = Actor(id=uuid.UUID(int=0xA1), roles=frozenset({"member"}))
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "code": {"type": "string", "title": "Code", "x-menagerist": {"kind": "text"}},
        "price": {
            "type": "number",
            "title": "Price",
            "x-menagerist": {"kind": "number"},
        },
    },
}
HEADER = "code,title,price\n"
MAPPING = (
    ColumnMapping(column="code", target="code"),
    ColumnMapping(column="title", target="name"),
    ColumnMapping(column="price", target="price"),
)


class World:
    """One person's targets and link store, shared by every run in a test."""

    def __init__(self, t: Targets) -> None:
        self.t = t
        self.repos = TransferRepos(
            links=InMemorySourceLinkRepository(), imports=InMemoryItemImportRepository()
        )

    async def plan(self, request: ItemImportRequest) -> Plan:
        """Plan `request` as Alice, with this world's link store."""
        use_case = PlanItemImport(
            self.repos, InMemoryAccessGuard(), self.t.presets, self.t.graph
        )
        return await use_case.handle(request, ALICE)

    async def run(
        self, request: ItemImportRequest
    ) -> InMemoryUnitOfWork[TransferRepos]:
        """Import `request` as Alice, returning the unit of work it used."""
        uow = InMemoryUnitOfWork(self.repos)
        use_case = ImportItems(uow, InMemoryAccessGuard(), self.t.presets, self.t.graph)
        await use_case.handle(request, ALICE)
        return uow


async def _world(shared: Shared) -> World:
    t = shared.targets(ALICE)
    await t.graph.create_item_type(
        BundleItemType(
            ref="signature",
            slug="signature",
            label="Signature",
            attributes_schema=SCHEMA,
        ),
        {},
    )
    return World(t)


def _request(
    body: str,
    *,
    key_field: str | None = "code",
    mapping: tuple[ColumnMapping, ...] = MAPPING,
    header: str = HEADER,
    restore: tuple[str, ...] = (),
) -> ItemImportRequest:
    return ItemImportRequest(
        data=(header + body).encode(),
        item_type="signature",
        mapping=mapping,
        key_field=key_field,
        restore=restore,
    )


async def _names(shared: Shared) -> list[str]:
    nodes = await shared.graph_repos.nodes.list(
        after=None, limit=100, scope=ContentFilter.everyone()
    )
    return sorted(n.name for n in nodes)


def _items(plan: Plan) -> list[PlannedEntity]:
    return [e for e in plan.entities if e.kind is EntityKind.ITEM]


async def test_without_a_key_column_nothing_is_recorded(shared: Shared) -> None:
    """Without a key column, a second run imports every row again."""
    world = await _world(shared)
    await world.run(_request("A1,Alien,1\n", key_field=None))
    await world.run(_request("A1,Alien,1\n", key_field=None))

    assert await _names(shared) == ["Alien", "Alien"]


async def test_a_second_run_creates_only_new_rows(shared: Shared) -> None:
    """Rows imported before are left alone; only the new one is created."""
    world = await _world(shared)
    await world.run(_request("A1,Alien,1\nA2,Aliens,2\n"))
    await world.run(_request("A1,Alien,1\nA2,Aliens,2\nA3,Alien 3,3\n"))

    assert await _names(shared) == ["Alien", "Alien 3", "Aliens"]


async def test_a_recognised_row_is_unchanged_and_names_its_item(
    shared: Shared,
) -> None:
    """A recognised row says where it came from and which item it is."""
    world = await _world(shared)
    await world.run(_request("A1,Alien,1\n"))

    (entity,) = _items(await world.plan(_request("A1,Alien,1\n")))

    assert entity.action is PlanAction.UNCHANGED
    assert entity.reason == "Already imported."
    assert entity.matched_name == "Alien"


async def test_a_value_changed_in_the_file_is_reported_not_written(
    shared: Shared,
) -> None:
    """A recognised row whose price changed says so, and keeps the old one."""
    world = await _world(shared)
    await world.run(_request("A1,Alien,1\n"))

    (entity,) = _items(await world.plan(_request("A1,Alien,2\n")))

    assert entity.changed == ("attributes.price",)


async def test_a_kept_detail_can_be_the_key(shared: Shared) -> None:
    """A column kept as each item's own detail recognises rows."""
    world = await _world(shared)
    mapping = (
        ColumnMapping(
            column="code",
            target=None,
            extra=ExtraField(key="ref", title="Ref", kind=ExtraFieldKind.TEXT),
        ),
        ColumnMapping(column="title", target="name"),
    )
    await world.run(_request("A1,Alien,1\n", key_field="ref", mapping=mapping))
    await world.run(_request("A1,Alien,1\n", key_field="ref", mapping=mapping))

    assert await _names(shared) == ["Alien"]


async def test_the_key_can_be_any_of_several_kept_details(shared: Shared) -> None:
    """The kept detail named as the key is used, not the first one kept."""
    world = await _world(shared)
    mapping = (
        ColumnMapping(
            column="price",
            target=None,
            extra=ExtraField(key="cost", title="Cost", kind=ExtraFieldKind.TEXT),
        ),
        ColumnMapping(
            column="code",
            target=None,
            extra=ExtraField(key="ref", title="Ref", kind=ExtraFieldKind.TEXT),
        ),
        ColumnMapping(column="title", target="name"),
    )

    plan = await world.plan(_request("A1,Alien,1\n", key_field="ref", mapping=mapping))

    assert [e.action for e in _items(plan)] == [PlanAction.CREATE]
    await world.run(_request("A1,Alien,1\n", key_field="ref", mapping=mapping))
    link = await world.repos.links.get_by_key(
        "csv:signature:ref", EntityKind.ITEM, "A1", scope=ContentFilter.of(ALICE.id)
    )
    assert link is not None


async def test_a_number_key_column_recognises_rows_again(shared: Shared) -> None:
    """An ID kept as a number is matched on its text, so rows are found again."""
    world = await _world(shared)
    mapping = (
        ColumnMapping(
            column="code",
            target=None,
            extra=ExtraField(key="ident", title="ID", kind=ExtraFieldKind.NUMBER),
        ),
        ColumnMapping(column="title", target="name"),
    )
    await world.run(_request("5,Alien,1\n", key_field="ident", mapping=mapping))
    await world.run(_request("5,Alien,1\n", key_field="ident", mapping=mapping))

    assert await _names(shared) == ["Alien"]


async def test_an_empty_key_cell_skips_the_row(shared: Shared) -> None:
    """A row with no key is skipped, and the others are imported."""
    world = await _world(shared)

    plan = await world.plan(_request(" ,Alien,1\nA2,Aliens,2\n"))

    assert [(e.label, e.action, e.reason) for e in _items(plan)] == [
        ("Alien", PlanAction.SKIP, "No key."),
        ("Aliens", PlanAction.CREATE, None),
    ]


async def test_keys_are_trimmed_and_case_counts(shared: Shared) -> None:
    """Spaces around a key do not matter; its case does."""
    world = await _world(shared)
    await world.run(_request(" A1 ,Alien,1\n"))

    plan = await world.plan(_request("A1,Alien,1\na1,Other,1\n"))

    assert [e.action for e in _items(plan)] == [
        PlanAction.UNCHANGED,
        PlanAction.CREATE,
    ]


async def test_a_deleted_row_stays_deleted_unless_restored(shared: Shared) -> None:
    """A row whose item was deleted is not created again until it is restored."""
    world = await _world(shared)
    await world.run(_request("A1,Alien,1\n"))
    link = await world.repos.links.get_by_key(
        "csv:signature:code", EntityKind.ITEM, "A1", scope=ContentFilter.of(ALICE.id)
    )
    assert link is not None
    await world.t.graph.remove(EntityKind.ITEM, link.entity_id)

    (kept,) = _items(await world.plan(_request("A1,Alien,1\n")))
    await world.run(_request("A1,Alien,1\n"))
    assert kept.reason == "You deleted this after importing it."
    assert await _names(shared) == []

    await world.run(_request("A1,Alien,1\n", restore=("A1",)))
    assert await _names(shared) == ["Alien"]


@pytest.mark.parametrize("key_field", ["description", "notes", "price_eur"])
async def test_a_key_that_is_not_mapped_or_kept_is_refused(
    shared: Shared, key_field: str
) -> None:
    """The key must be the name, a mapped field or a kept detail."""
    world = await _world(shared)

    with pytest.raises(InvalidImportFileError, match="map to a field or keep"):
        await world.plan(_request("A1,Alien,1\n", key_field=key_field))


async def test_the_name_can_be_the_key(shared: Shared) -> None:
    """Rows can be recognised by the column mapped to the name."""
    world = await _world(shared)
    await world.run(_request("A1,Alien,1\n", key_field="name"))

    (entity,) = _items(await world.plan(_request("A9,Alien,1\n", key_field="name")))

    assert entity.action is PlanAction.UNCHANGED


async def test_items_made_without_links_are_found_by_their_key_next_time(
    shared: Shared,
) -> None:
    """Items an import made without recording links are matched, not duplicated."""
    world = await _world(shared)
    await world.run(_request("A1,Alien,1\n", key_field=None))

    (entity,) = _items(await world.plan(_request("A1,Alien,1\n")))
    await world.run(_request("A1,Alien,1\n"))

    assert (
        entity.reason == "Matches your existing item. It will be linked, not changed."
    )
    assert await _names(shared) == ["Alien"]


async def test_links_are_committed_with_the_import(shared: Shared) -> None:
    """The run commits the links it records."""
    world = await _world(shared)

    uow = await world.run(_request("A1,Alien,1\n"))

    assert uow.committed


async def test_a_number_key_finds_items_imported_without_links(shared: Shared) -> None:
    """An ID kept as a number finds the items an import without links made."""
    world = await _world(shared)
    mapping = (
        ColumnMapping(
            column="code",
            target=None,
            extra=ExtraField(key="ident", title="ID", kind=ExtraFieldKind.NUMBER),
        ),
        ColumnMapping(column="title", target="name"),
    )
    await world.run(_request("5,Alien,1\n", key_field=None, mapping=mapping))

    (entity,) = _items(
        await world.plan(_request("5,Alien,1\n", key_field="ident", mapping=mapping))
    )
    await world.run(_request("5,Alien,1\n", key_field="ident", mapping=mapping))

    assert entity.action is PlanAction.UNCHANGED
    assert await _names(shared) == ["Alien"]
