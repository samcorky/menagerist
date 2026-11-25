"""Keeping CSV columns the item type has no field for as the items' own fields."""

import uuid
from typing import TYPE_CHECKING, Any

import pytest

from app.modules.transfer.adapters.persistence.in_memory_import_repository import (
    InMemoryItemImportRepository,
)
from app.modules.transfer.adapters.persistence.in_memory_source_link_repository import (
    InMemorySourceLinkRepository,
)
from app.modules.transfer.adapters.persistence.unit_of_work import (
    create_in_memory_transfer_uow,
)
from app.modules.transfer.application.item_import import (
    ImportItems,
    InspectItemImport,
    ItemImportRequest,
    PlanItemImport,
)
from app.modules.transfer.domain.bundle import BundleItemType
from app.modules.transfer.domain.errors import InvalidImportFileError
from app.modules.transfer.domain.tabular import (
    MAX_CHOICE_OPTIONS,
    MAX_EXTRA_FIELDS,
    ColumnMapping,
    ExtraField,
    ExtraFieldKind,
)
from app.modules.transfer.ports.unit_of_work import TransferRepos, TransferUnitOfWork
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import Actor
from app.shared_kernel.content_filter import ContentFilter

if TYPE_CHECKING:
    from tests.modules.conftest import Shared, Targets

ALICE = Actor(id=uuid.UUID(int=0xA1), roles=frozenset({"member"}))


def _repos() -> TransferRepos:
    return TransferRepos(
        links=InMemorySourceLinkRepository(), imports=InMemoryItemImportRepository()
    )


def _uow() -> TransferUnitOfWork:
    return create_in_memory_transfer_uow(_repos())


SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "code": {"type": "string", "title": "Code", "x-menagerist": {"kind": "text"}},
    },
}
HEADER = "title,code,paper,extra\n"
PARTIAL_DATE = "^[0-9]{4}(-(0[1-9]|1[0-2])(-(0[1-9]|[12][0-9]|3[01]))?)?$"


def _keep(
    column: str, kind: ExtraFieldKind, key: str = "paper", title: str = "Paper"
) -> ColumnMapping:
    return ColumnMapping(
        column=column, target=None, extra=ExtraField(key=key, title=title, kind=kind)
    )


def _mapping(*extra: ColumnMapping) -> tuple[ColumnMapping, ...]:
    return (
        ColumnMapping(column="title", target="name"),
        ColumnMapping(column="code", target="code"),
        *extra,
    )


async def _with_type(shared: Shared) -> Targets:
    t = shared.targets(ALICE)
    await t.graph.create_item_type(
        BundleItemType(
            ref="poster", slug="poster", label="Poster", attributes_schema=SCHEMA
        ),
        {},
    )
    return t


def _request(body: str, mapping: tuple[ColumnMapping, ...]) -> ItemImportRequest:
    return ItemImportRequest(
        data=(HEADER + body).encode(), item_type="poster", mapping=mapping
    )


async def _run(t: Targets, body: str, mapping: tuple[ColumnMapping, ...]) -> None:
    await ImportItems(_uow(), InMemoryAccessGuard(), t.presets, t.graph).handle(
        _request(body, mapping), ALICE
    )


async def _nodes(shared: Shared) -> dict[str, Any]:
    nodes = await shared.graph_repos.nodes.list(
        after=None, limit=10000, scope=ContentFilter.everyone()
    )
    return {node.name: node for node in nodes}


async def test_a_kept_column_becomes_each_item_s_own_field(shared: Shared) -> None:
    """The value is stored and the field is described on the item, not the type."""
    t = await _with_type(shared)

    await _run(t, "Alien,A1,Matte,\n", _mapping(_keep("paper", ExtraFieldKind.TEXT)))

    alien = (await _nodes(shared))["Alien"]
    assert alien.attributes == {"code": "A1", "paper": "Matte"}
    assert alien.extra_schema == {
        "type": "object",
        "properties": {
            "paper": {
                "title": "Paper",
                "type": "string",
                "x-menagerist": {"kind": "text"},
            }
        },
    }
    fields = await t.graph.item_type_fields("poster")
    assert fields is not None
    assert [f.key for f in fields] == ["code"]


async def test_a_blank_cell_leaves_the_field_off_that_item(shared: Shared) -> None:
    """An item gets the field only when its cell has a value."""
    t = await _with_type(shared)

    await _run(
        t, "Alien,A1,Matte,\nHeat,H1,,\n", _mapping(_keep("paper", ExtraFieldKind.TEXT))
    )

    nodes = await _nodes(shared)
    assert nodes["Heat"].attributes == {"code": "H1"}
    assert nodes["Heat"].extra_schema is None
    assert nodes["Alien"].extra_schema is not None


@pytest.mark.parametrize(
    ("kind", "cell", "value", "shape"),
    [
        (ExtraFieldKind.NUMBER, "12.5", 12.5, {"type": "number"}),
        (ExtraFieldKind.BOOLEAN, "yes", True, {"type": "boolean"}),
        (
            ExtraFieldKind.DATE,
            "2019-08-19",
            "2019-08-19",
            {"type": "string", "format": "date"},
        ),
        (
            ExtraFieldKind.PARTIAL_DATE,
            "2019-08",
            "2019-08",
            {"type": "string", "pattern": PARTIAL_DATE},
        ),
    ],
)
async def test_each_kind_converts_its_cells_and_is_described_like_the_editor_does(
    shared: Shared,
    kind: ExtraFieldKind,
    cell: str,
    value: object,
    shape: dict[str, Any],
) -> None:
    """The definition is the one the item page's Add field writes for that kind."""
    t = await _with_type(shared)

    await _run(t, f"Alien,A1,{cell},\n", _mapping(_keep("paper", kind)))

    alien = (await _nodes(shared))["Alien"]
    assert alien.attributes["paper"] == value
    assert alien.extra_schema["properties"]["paper"] == {
        "title": "Paper",
        **shape,
        "x-menagerist": {"kind": str(kind)},
    }


async def test_a_choice_offers_every_value_in_the_column(shared: Shared) -> None:
    """The options are the column's distinct values, in the order they first appear."""
    t = await _with_type(shared)
    body = "Alien,A1,Matte,\nHeat,H1,Gloss,\nRan,R1,Matte,\nDune,D1,,\n"

    await _run(t, body, _mapping(_keep("paper", ExtraFieldKind.CHOICE)))

    paper = (await _nodes(shared))["Heat"].extra_schema["properties"]["paper"]
    assert paper["enum"] == ["Matte", "Gloss"]
    assert paper["x-menagerist"] == {"kind": "choice"}


async def test_a_choice_with_too_many_values_is_refused(shared: Shared) -> None:
    """Past the cap the column is better kept as text."""
    t = await _with_type(shared)
    body = "".join(f"P{n},C{n},Paper {n},\n" for n in range(MAX_CHOICE_OPTIONS + 1))
    mapping = _mapping(_keep("paper", ExtraFieldKind.CHOICE))

    with pytest.raises(InvalidImportFileError, match="keep it as text"):
        await PlanItemImport(
            _repos(), InMemoryAccessGuard(), t.presets, t.graph
        ).handle(_request(body, mapping), ALICE)


async def test_a_bad_cell_in_a_kept_column_blocks_the_run(shared: Shared) -> None:
    """A value the kind cannot take is a problem naming the row and the field."""
    t = await _with_type(shared)
    mapping = _mapping(_keep("paper", ExtraFieldKind.NUMBER, title="Copies"))

    plan = await PlanItemImport(
        _repos(), InMemoryAccessGuard(), t.presets, t.graph
    ).handle(_request("Alien,A1,lots,\n", mapping), ALICE)

    assert [b.reason for b in plan.blockers] == [
        "Row 2, Copies: 'lots' is not a number."
    ]


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        ((_keep("paper", ExtraFieldKind.TEXT, key="code"),), "already a field"),
        ((_keep("paper", ExtraFieldKind.TEXT, key="name"),), "already a field"),
        (
            (
                _keep("paper", ExtraFieldKind.TEXT),
                _keep("extra", ExtraFieldKind.TEXT),
            ),
            "'paper' is used for more than one column",
        ),
        ((_keep("paper", ExtraFieldKind.TEXT, key="Paper Type"),), "not a usable key"),
        ((_keep("paper", ExtraFieldKind.TEXT, key="__proto__"),), "not a usable key"),
        ((_keep("paper", ExtraFieldKind.TEXT, title=" "),), "needs a name"),
        ((_keep("colour", ExtraFieldKind.TEXT),), "no column 'colour'"),
        (
            (
                ColumnMapping(
                    column="paper",
                    target="code",
                    extra=ExtraField(
                        key="paper", title="Paper", kind=ExtraFieldKind.TEXT
                    ),
                ),
            ),
            "either a field or kept as an extra detail",
        ),
    ],
)
async def test_a_bad_extra_field_is_refused_before_converting(
    shared: Shared, extra: tuple[ColumnMapping, ...], message: str
) -> None:
    """The kept columns are checked with the rest of the mapping."""
    t = await _with_type(shared)
    mapping = (ColumnMapping(column="title", target="name"), *extra)

    with pytest.raises(InvalidImportFileError, match=message):
        await PlanItemImport(
            _repos(), InMemoryAccessGuard(), t.presets, t.graph
        ).handle(_request("Alien,A1,Matte,x\n", mapping), ALICE)


async def test_more_extra_fields_than_an_item_may_have_are_refused(
    shared: Shared,
) -> None:
    """An item can have at most 50 extra fields."""
    t = await _with_type(shared)
    columns = [f"c{n}" for n in range(MAX_EXTRA_FIELDS + 1)]
    data = "title," + ",".join(columns) + "\n" + "Alien" + ",x" * len(columns)
    mapping = (
        ColumnMapping(column="title", target="name"),
        *(_keep(c, ExtraFieldKind.TEXT, key=c, title=c) for c in columns),
    )

    with pytest.raises(InvalidImportFileError, match="at most 50"):
        await PlanItemImport(
            _repos(), InMemoryAccessGuard(), t.presets, t.graph
        ).handle(
            ItemImportRequest(data=data.encode(), item_type="poster", mapping=mapping),
            ALICE,
        )


async def test_inspect_guesses_a_kind_for_each_column(shared: Shared) -> None:
    """The guess is the narrowest kind that takes every value in the column."""
    t = await _with_type(shared)
    data = "\n".join(
        (
            "title,copies,signed,printed,year_month,paper,empty",
            "Alien,3,yes,2019-08-19,2019-08,Matte,",
            "Heat,12.5,no,2020-01-02,2020,Gloss,",
        )
    )

    result = await InspectItemImport(InMemoryAccessGuard(), t.presets, t.graph).handle(
        ItemImportRequest(data=data.encode(), item_type="poster"), ALICE
    )

    assert {c.column: c.kind for c in result.column_kinds} == {
        "title": ExtraFieldKind.TEXT,
        "copies": ExtraFieldKind.NUMBER,
        "signed": ExtraFieldKind.BOOLEAN,
        "printed": ExtraFieldKind.DATE,
        "year_month": ExtraFieldKind.PARTIAL_DATE,
        "paper": ExtraFieldKind.TEXT,
        "empty": ExtraFieldKind.TEXT,
    }
