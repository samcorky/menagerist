"""Import a CSV into one item type: inspect it, preview it, run it.

The file is read and converted here, on the server, and the items go through the same
plan and apply as any other import. One bad value blocks the run, so the preview names
every problem (up to a cap) by spreadsheet row and field.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.transfer.application.cell_values import convert_cell
from app.modules.transfer.application.csv_rows import (
    CsvTable,
    read_csv,
    suggest_mapping,
)
from app.modules.transfer.application.extras import BundleExtras
from app.modules.transfer.application.permissions import TransferPermission
from app.modules.transfer.application.pipeline import (
    AppliedBundle,
    apply_bundle,
    plan_bundle,
)
from app.modules.transfer.domain.bundle import Bundle, BundleItem, BundleItemType
from app.modules.transfer.domain.entity_kind import EntityKind
from app.modules.transfer.domain.errors import CellValueError, InvalidImportFileError
from app.modules.transfer.domain.plan import ClashPolicy, Plan, PlanBlocker
from app.modules.transfer.domain.tabular import (
    MAX_IMPORT_ROWS,
    MAX_LISTED_PROBLEMS,
    CellProblem,
    ColumnMapping,
    FieldSpec,
)
from app.shared_kernel.access import Access, Requires
from app.shared_kernel.cqrs import UseCase

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.modules.transfer.ports.targets import GraphTarget, PresetTarget
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()

_BUILT_IN = ("name", "description", "tags")
_SAMPLE_ROWS = 5


@dataclass(frozen=True, kw_only=True, eq=False)
class ItemImportRequest:
    """A CSV file, the item type it becomes, and how its columns map to fields."""

    data: bytes
    item_type: str
    mapping: tuple[ColumnMapping, ...] = ()
    list_separator: str = ","


@dataclass(frozen=True, kw_only=True, eq=False)
class ItemImportInspection:
    """What is in the file, the type's fields, and a mapping to start from."""

    headers: tuple[str, ...]
    sample_rows: tuple[tuple[str, ...], ...]
    row_count: int
    fields: tuple[FieldSpec, ...]
    suggested_mapping: tuple[ColumnMapping, ...]


def build_item_bundle(
    table: CsvTable,
    mapping: Sequence[ColumnMapping],
    fields: Sequence[FieldSpec],
    item_type: str,
    list_separator: str,
) -> tuple[Bundle, list[CellProblem]]:
    """Turn the rows into a bundle of items of `item_type`, with what is wrong.

    A row with a problem is left out of the bundle and reported.

    Raises:
        InvalidImportFileError: the mapping cannot be used for this file and type.
    """
    columns = _columns(table.headers, mapping, fields)
    by_key = {field.key: field for field in fields}
    items: list[BundleItem] = []
    problems: list[CellProblem] = []
    for number, cells in zip(table.numbers, table.rows, strict=True):
        name = cells[columns["name"]].strip()
        found: list[CellProblem] = []
        if not name:
            found.append(CellProblem(row=number, field="Name", message="name is empty"))
        attributes: dict[str, object] = {}
        for key, index in columns.items():
            if key in _BUILT_IN:
                continue
            field = by_key[key]
            try:
                value = convert_cell(cells[index], field, list_separator=list_separator)
            except CellValueError as error:
                found.append(
                    CellProblem(row=number, field=field.title, message=str(error))
                )
                continue
            if value is not None:
                attributes[key] = value
        if found:
            problems.extend(found)
            continue
        items.append(
            BundleItem(
                ref=f"row-{number}",
                type_ref=item_type,
                name=name,
                description=_cell(cells, columns, "description"),
                attributes=attributes,
                tags=_tags(cells, columns, list_separator),
            )
        )
    bundle = Bundle(
        id=f"csv-{item_type}",
        item_types=(BundleItemType(ref=item_type, slug=item_type, label=item_type),),
        items=tuple(items),
        item_limit=MAX_IMPORT_ROWS,
    )
    return bundle, problems


def _columns(
    headers: Sequence[str],
    mapping: Sequence[ColumnMapping],
    fields: Sequence[FieldSpec],
) -> dict[str, int]:
    """Return each mapped target's column index, after checking the mapping."""
    index = {header: i for i, header in enumerate(headers)}
    by_key = {field.key: field for field in fields}
    columns: dict[str, int] = {}
    for entry in mapping:
        if entry.target is None:
            continue
        if entry.column not in index:
            raise InvalidImportFileError(f"The file has no column '{entry.column}'.")
        if entry.target in columns:
            raise InvalidImportFileError(f"'{entry.target}' is mapped more than once.")
        _check_target(entry.target, by_key)
        columns[entry.target] = index[entry.column]
    if "name" not in columns:
        raise InvalidImportFileError("Map a column to name: every item needs one.")
    return columns


def _check_target(target: str, by_key: dict[str, FieldSpec]) -> None:
    """Refuse a target that is not a field of the type or cannot be filled."""
    if target in _BUILT_IN:
        return
    field = by_key.get(target)
    if field is None:
        raise InvalidImportFileError(f"'{target}' is not a field of this item type.")
    if not field.importable:
        raise InvalidImportFileError(
            field.reason or f"{field.title} cannot be imported yet"
        )


def _cell(cells: Sequence[str], columns: dict[str, int], target: str) -> str | None:
    if target not in columns:
        return None
    return cells[columns[target]].strip() or None


def _tags(
    cells: Sequence[str], columns: dict[str, int], separator: str
) -> tuple[str, ...]:
    text = _cell(cells, columns, "tags")
    if text is None:
        return ()
    return tuple(part.strip() for part in text.split(separator) if part.strip())


class _ItemImport:
    def __init__(
        self, guard: AccessGuard, presets: PresetTarget, graph: GraphTarget
    ) -> None:
        """Initialise with the access guard and the targets."""
        self._guard = guard
        self._presets = presets
        self._graph = graph

    async def _fields(self, slug: str) -> list[FieldSpec]:
        fields = await self._graph.item_type_fields(slug)
        if fields is None:
            raise InvalidImportFileError(f"You have no item type called '{slug}'.")
        return fields

    async def _plan(self, request: ItemImportRequest) -> tuple[Bundle, Plan]:
        """Plan the file; every problem in it becomes a blocker on the plan."""
        fields = await self._fields(request.item_type)
        bundle, problems = build_item_bundle(
            read_csv(request.data),
            request.mapping,
            fields,
            request.item_type,
            request.list_separator,
        )
        listed = [(p.row, f"Row {p.row}, {p.field}: {p.message}.") for p in problems]
        for item in bundle.items:
            number = int(item.ref.removeprefix("row-"))
            found = await self._graph.check_item_attributes(
                request.item_type, item.attributes
            )
            listed.extend((number, f"Row {number}, {text}.") for text in found)
        plan = await plan_bundle(
            bundle,
            self._presets,
            self._graph,
            clash=ClashPolicy.SKIP,
            extras=BundleExtras(),
        )
        blockers = _blockers([text for _, text in sorted(listed, key=lambda e: e[0])])
        return bundle, Plan(
            bundle_id=plan.bundle_id,
            entities=plan.entities,
            blockers=(*plan.blockers, *blockers),
        )


def _blockers(texts: Sequence[str]) -> list[PlanBlocker]:
    blockers = [
        PlanBlocker(code="InvalidCellError", reason=text)
        for text in texts[:MAX_LISTED_PROBLEMS]
    ]
    more = len(texts) - MAX_LISTED_PROBLEMS
    if more > 0:
        noun = "problem" if more == 1 else "problems"
        blockers.append(
            PlanBlocker(code="InvalidCellError", reason=f"and {more} more {noun}.")
        )
    return blockers


class InspectItemImport(_ItemImport, UseCase[ItemImportRequest, ItemImportInspection]):
    """Read a CSV and describe it, with the type's fields and a suggested mapping.

    Raises:
        ValidationError: the file is not a usable CSV, or the type does not exist.
    """

    access: ClassVar[Access] = Requires(TransferPermission.BUNDLE_IMPORT)

    async def _handle(
        self, request: ItemImportRequest, actor: Actor
    ) -> ItemImportInspection:
        """Return the headers, a few rows and a first guess at the mapping."""
        fields = await self._fields(request.item_type)
        table = read_csv(request.data)
        return ItemImportInspection(
            headers=table.headers,
            sample_rows=table.rows[:_SAMPLE_ROWS],
            row_count=len(table.rows),
            fields=tuple(fields),
            suggested_mapping=tuple(suggest_mapping(table.headers, fields)),
        )


class PlanItemImport(_ItemImport, UseCase[ItemImportRequest, Plan]):
    """Return what importing the file would do; nothing is written.

    Every value that cannot be imported is a blocker naming its row and field.

    Raises:
        ValidationError: the file or the mapping cannot be used, or the type does
            not exist.
    """

    access: ClassVar[Access] = Requires(TransferPermission.BUNDLE_IMPORT)

    async def _handle(self, request: ItemImportRequest, actor: Actor) -> Plan:
        """Plan the items, leaving out the type they go under."""
        _, plan = await self._plan(request)
        return Plan(
            bundle_id=plan.bundle_id,
            entities=tuple(
                e for e in plan.entities if e.kind is not EntityKind.ITEM_TYPE
            ),
            blockers=plan.blockers,
        )


class ImportItems(_ItemImport, UseCase[ItemImportRequest, AppliedBundle]):
    """Import the file: plan it as `PlanItemImport` does, then create the items.

    Raises:
        ValidationError: the file or the mapping cannot be used, or the type does
            not exist.
        BundleConflictError: the plan has problems.
    """

    access: ClassVar[Access] = Requires(TransferPermission.BUNDLE_IMPORT)

    async def _handle(self, request: ItemImportRequest, actor: Actor) -> AppliedBundle:
        """Plan again, and apply only a plan with nothing wrong."""
        bundle, plan = await self._plan(request)
        applied = await apply_bundle(
            plan, bundle, self._presets, self._graph, extras=BundleExtras()
        )
        logger.info("items imported", created=applied.total_created)
        return applied
