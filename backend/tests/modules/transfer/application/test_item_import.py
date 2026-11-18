"""Importing a CSV into one item type: inspect, plan and run."""

import uuid
from typing import TYPE_CHECKING, Any

import pytest

from app.modules.transfer.application.item_import import (
    ImportItems,
    InspectItemImport,
    ItemImportRequest,
    PlanItemImport,
)
from app.modules.transfer.domain.bundle import BundleItemType
from app.modules.transfer.domain.entity_kind import EntityKind
from app.modules.transfer.domain.errors import (
    BundleConflictError,
    InvalidImportFileError,
)
from app.modules.transfer.domain.plan import PlanAction
from app.modules.transfer.domain.tabular import ColumnMapping, CsvEncoding
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import Actor
from app.shared_kernel.content_filter import ContentFilter

if TYPE_CHECKING:
    from tests.modules.conftest import Shared, Targets

ALICE = Actor(id=uuid.UUID(int=0xA1), roles=frozenset({"member"}))
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "position": {
            "type": "string",
            "title": "Position and pen",
            "x-menagerist": {"kind": "text"},
        },
        "authenticated": {
            "type": "boolean",
            "title": "Authenticated",
            "x-menagerist": {"kind": "boolean"},
        },
        "signed_on": {
            "type": "string",
            "title": "Signed on",
            "pattern": "^[0-9]{4}(-(0[1-9]|1[0-2])(-(0[1-9]|[12][0-9]|3[01]))?)?$",
            "x-menagerist": {"kind": "partialdate"},
        },
        "code": {
            "type": "string",
            "title": "Code",
            "maxLength": 3,
            "x-menagerist": {"kind": "text"},
        },
        "value": {
            "type": "number",
            "title": "Value",
            "x-menagerist": {"kind": "money"},
        },
    },
}
HEADER = "title,signed_on,position,authenticated,notes\n"
MAPPING = (
    ColumnMapping(column="title", target="name"),
    ColumnMapping(column="signed_on", target="signed_on"),
    ColumnMapping(column="position", target="position"),
    ColumnMapping(column="authenticated", target="authenticated"),
    ColumnMapping(column="notes", target="description"),
)


async def _with_type(shared: Shared) -> Targets:
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
    return t


def _request(
    body: str,
    mapping: tuple[ColumnMapping, ...] = MAPPING,
    item_type: str = "signature",
) -> ItemImportRequest:
    return ItemImportRequest(
        data=(HEADER + body).encode(), item_type=item_type, mapping=mapping
    )


def _plan(t: Targets) -> PlanItemImport:
    return PlanItemImport(InMemoryAccessGuard(), t.presets, t.graph)


def _run(t: Targets) -> ImportItems:
    return ImportItems(InMemoryAccessGuard(), t.presets, t.graph)


async def _nodes(shared: Shared) -> list[Any]:
    return await shared.graph_repos.nodes.list(
        after=None, limit=10000, scope=ContentFilter.everyone()
    )


async def test_the_plan_adds_each_item_and_leaves_the_type_out(
    shared: Shared,
) -> None:
    """The preview lists items to add, not the type they go under."""
    t = await _with_type(shared)
    body = "Alien #1,2019-08,cover,yes,\nHulk 181,2021,back,no,COA\n"

    plan = await _plan(t).handle(_request(body), ALICE)

    assert plan.ready
    assert [(e.kind, e.action) for e in plan.entities] == [
        (EntityKind.ITEM, PlanAction.CREATE)
    ] * 2
    assert [e.label for e in plan.entities] == ["Alien #1", "Hulk 181"]


async def test_a_bad_cell_becomes_a_blocker_naming_row_and_field(
    shared: Shared,
) -> None:
    """One bad value stops the import and names where it is."""
    t = await _with_type(shared)
    body = "Alien #1,2019-08,cover,yes,\nHulk 181,19th Aug,back,no,\n"

    plan = await _plan(t).handle(_request(body), ALICE)

    assert not plan.ready
    [blocker] = plan.blockers
    assert blocker.code == "InvalidCellError"
    assert blocker.reason.startswith("Row 3, Signed on: '19th Aug' is not a date")


async def test_a_schema_problem_is_reported_with_the_field_title(
    shared: Shared,
) -> None:
    """A value the field's own rules refuse is reported too."""
    t = await _with_type(shared)
    mapping = (*MAPPING, ColumnMapping(column="code", target="code"))
    request = ItemImportRequest(
        data=b"title,signed_on,position,authenticated,notes,code\nA,2019,x,yes,,abcd\n",
        item_type="signature",
        mapping=mapping,
    )

    plan = await _plan(t).handle(request, ALICE)

    [blocker] = plan.blockers
    assert blocker.reason.startswith("Row 2, Code: ")


async def test_listed_problems_are_capped_with_a_count(shared: Shared) -> None:
    """Twenty problems are listed and the rest are counted."""
    t = await _with_type(shared)
    body = "A,soon,x,yes,\n" * 25

    plan = await _plan(t).handle(_request(body), ALICE)

    assert len(plan.blockers) == 21
    assert plan.blockers[-1].reason == "and 5 more problems."


async def test_an_empty_name_is_a_problem(shared: Shared) -> None:
    """A row needs a name."""
    t = await _with_type(shared)

    plan = await _plan(t).handle(_request(" ,2019,x,yes,\n"), ALICE)

    [blocker] = plan.blockers
    assert blocker.reason == "Row 2, Name: name is empty."


@pytest.mark.parametrize(
    ("mapping", "message"),
    [
        (
            (ColumnMapping(column="signed_on", target="signed_on"),),
            "name",
        ),
        (
            (
                ColumnMapping(column="title", target="name"),
                ColumnMapping(column="notes", target="name"),
            ),
            "more than once",
        ),
        (
            (
                ColumnMapping(column="title", target="name"),
                ColumnMapping(column="nope", target="position"),
            ),
            "no column 'nope'",
        ),
        (
            (
                ColumnMapping(column="title", target="name"),
                ColumnMapping(column="notes", target="colour"),
            ),
            "'colour' is not a field",
        ),
        (
            (
                ColumnMapping(column="title", target="name"),
                ColumnMapping(column="notes", target="value"),
            ),
            "Value cannot be imported yet",
        ),
    ],
)
async def test_a_bad_mapping_is_refused_before_converting(
    shared: Shared, mapping: tuple[ColumnMapping, ...], message: str
) -> None:
    """The mapping is checked as a whole before any row is read."""
    t = await _with_type(shared)
    with pytest.raises(InvalidImportFileError, match=message):
        await _plan(t).handle(_request("A,2019,x,yes,n\n", mapping), ALICE)


async def test_an_unknown_type_is_refused_not_created(shared: Shared) -> None:
    """The import never makes a type."""
    t = shared.targets(ALICE)
    with pytest.raises(InvalidImportFileError, match="no item type called 'ghost'"):
        await _plan(t).handle(_request("A,2019,x,yes,\n", item_type="ghost"), ALICE)
    assert await t.graph.item_type_fields("ghost") is None


async def test_the_run_creates_the_items_with_converted_values(
    shared: Shared,
) -> None:
    """Values are stored typed, and blank optional cells are left out."""
    t = await _with_type(shared)
    body = "Alien #1,2019-08,,yes,\n"

    applied = await _run(t).handle(_request(body), ALICE)

    assert applied.created[EntityKind.ITEM] == 1
    [node] = await _nodes(shared)
    assert node.name == "Alien #1"
    assert node.attributes == {"signed_on": "2019-08", "authenticated": True}
    assert node.type == "signature"


async def test_the_run_refuses_what_the_plan_refused(shared: Shared) -> None:
    """Nothing is created when any cell is bad."""
    t = await _with_type(shared)
    body = "Alien #1,2019-08,cover,yes,\nHulk 181,soon,back,no,\n"

    with pytest.raises(BundleConflictError):
        await _run(t).handle(_request(body), ALICE)

    assert await _nodes(shared) == []


async def test_more_than_500_rows_are_allowed(shared: Shared) -> None:
    """A spreadsheet may hold more than a bundle file can."""
    t = await _with_type(shared)
    body = "Alien,2019,x,yes,\n" * 501

    plan = await _plan(t).handle(_request(body), ALICE)

    assert plan.ready
    assert len(plan.entities) == 501


async def test_a_column_mapped_to_nothing_is_ignored(shared: Shared) -> None:
    """A column with no target is read past, and its content never matters."""
    t = await _with_type(shared)
    mapping = (
        ColumnMapping(column="title", target="name"),
        ColumnMapping(column="signed_on", target=None),
    )

    plan = await _plan(t).handle(_request("Alien,not a date,x,yes,\n", mapping), ALICE)

    assert plan.ready


async def test_tags_are_split_on_the_separator_and_trimmed(shared: Shared) -> None:
    """A tags column becomes the item's tags."""
    t = await _with_type(shared)
    mapping = (
        ColumnMapping(column="title", target="name"),
        ColumnMapping(column="notes", target="tags"),
    )

    await _run(t).handle(
        _request('Alien,2019,x,yes," rare , signed ,,"\n', mapping), ALICE
    )

    [node] = await _nodes(shared)
    assert node.tags == ["rare", "signed"]


async def test_inspect_returns_headers_samples_count_fields_and_suggestions(
    shared: Shared,
) -> None:
    """The first call shows what is in the file and how it could be mapped."""
    t = await _with_type(shared)
    body = "".join(f"Item {n},2019,x,yes,\n" for n in range(8))
    request = ItemImportRequest(data=(HEADER + body).encode(), item_type="signature")

    result = await InspectItemImport(InMemoryAccessGuard(), t.presets, t.graph).handle(
        request, ALICE
    )

    assert result.headers == (
        "title",
        "signed_on",
        "position",
        "authenticated",
        "notes",
    )
    assert len(result.sample_rows) == 5
    assert result.row_count == 8
    assert result.encoding == CsvEncoding.UTF_8
    assert {f.key for f in result.fields} >= {"signed_on", "position", "value"}
    targets = {m.column: m.target for m in result.suggested_mapping}
    assert targets == {
        "title": "name",
        "signed_on": "signed_on",
        "position": "position",
        "authenticated": "authenticated",
        "notes": "description",
    }
