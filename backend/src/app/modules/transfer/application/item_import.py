"""Import a CSV into one item type: inspect it, preview it, run it.

The file is read and converted here, on the server, and the items go through the same
plan and apply as any other import. One bad value blocks the run, so the preview names
every problem (up to a cap) by spreadsheet row and field.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

import structlog

from app.modules.transfer.application.cell_values import (
    convert_cell,
    suggest_day_month_order,
)
from app.modules.transfer.application.csv_rows import (
    CsvTable,
    read_csv,
    suggest_mapping,
)
from app.modules.transfer.application.extra_columns import (
    check_key,
    choice_options,
    extra_property,
    extra_spec,
    suggest_kind,
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
    MAX_EXTRA_FIELDS,
    MAX_IMPORT_ROWS,
    MAX_LISTED_PROBLEMS,
    CellProblem,
    ColumnKind,
    ColumnMapping,
    CsvEncoding,
    DayMonthOrder,
    DayMonthOrderGuess,
    ExtraField,
    ExtraFieldKind,
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
    day_month_order: DayMonthOrder = DayMonthOrder.DAY_FIRST


@dataclass(frozen=True, kw_only=True, eq=False)
class ItemImportInspection:
    """What is in the file, the type's fields, and a mapping to start from."""

    headers: tuple[str, ...]
    sample_rows: tuple[tuple[str, ...], ...]
    row_count: int
    fields: tuple[FieldSpec, ...]
    suggested_mapping: tuple[ColumnMapping, ...]
    encoding: CsvEncoding
    # None when no cell is written as three numbers, so there is nothing to choose.
    day_month_order: DayMonthOrderGuess | None
    # Each column's kind, should it be kept as the items' own field.
    column_kinds: tuple[ColumnKind, ...] = ()


def build_item_bundle(
    table: CsvTable,
    mapping: Sequence[ColumnMapping],
    fields: Sequence[FieldSpec],
    item_type: str,
    list_separator: str,
    day_month_order: DayMonthOrder = DayMonthOrder.DAY_FIRST,
) -> tuple[Bundle, list[CellProblem]]:
    """Turn the rows into a bundle of items of `item_type`, with what is wrong.

    A row with a problem is left out of the bundle and reported.

    Raises:
        InvalidImportFileError: the mapping cannot be used for this file and type.
    """
    columns, kept = _columns(table.headers, mapping, fields)
    by_key = {field.key: field for field in fields}
    # Each filled column: its index, how to read it, and the item's own definition
    # when the column is kept as an extra field rather than one of the type's.
    filled: list[tuple[int, FieldSpec, dict[str, Any] | None]] = [
        (index, by_key[key], None)
        for key, index in columns.items()
        if key not in _BUILT_IN
    ]
    filled.extend(_extras(table, kept))
    items: list[BundleItem] = []
    problems: list[CellProblem] = []
    for number, cells in zip(table.numbers, table.rows, strict=True):
        name = cells[columns["name"]].strip()
        found: list[CellProblem] = []
        if not name:
            found.append(CellProblem(row=number, field="Name", message="name is empty"))
        attributes: dict[str, object] = {}
        own: dict[str, Any] = {}
        for index, spec, prop in filled:
            try:
                value = convert_cell(
                    cells[index],
                    spec,
                    list_separator=list_separator,
                    day_month_order=day_month_order,
                )
            except CellValueError as error:
                found.append(
                    CellProblem(row=number, field=spec.title, message=str(error))
                )
                continue
            if value is None:
                continue
            attributes[spec.key] = value
            if prop is not None:
                own[spec.key] = prop
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
                extra_schema={"type": "object", "properties": own} if own else None,
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
) -> tuple[dict[str, int], list[tuple[int, ExtraField]]]:
    """Return each mapped target's column index and the kept columns, once checked."""
    index = {header: i for i, header in enumerate(headers)}
    by_key = {field.key: field for field in fields}
    columns: dict[str, int] = {}
    kept = _kept(mapping, index)
    for entry in mapping:
        if entry.target is None or entry.extra is not None:
            continue
        if entry.column not in index:
            raise InvalidImportFileError(f"The file has no column '{entry.column}'.")
        if entry.target in columns:
            raise InvalidImportFileError(f"'{entry.target}' is mapped more than once.")
        _check_target(entry.target, by_key)
        columns[entry.target] = index[entry.column]
    if "name" not in columns:
        raise InvalidImportFileError("Map a column to name: every item needs one.")
    _check_kept(kept, by_key)
    return columns, kept


def _kept(
    mapping: Sequence[ColumnMapping], index: dict[str, int]
) -> list[tuple[int, ExtraField]]:
    """The columns kept as the items' own fields, with their index."""
    kept: list[tuple[int, ExtraField]] = []
    for entry in mapping:
        if entry.extra is None:
            continue
        if entry.column not in index:
            raise InvalidImportFileError(f"The file has no column '{entry.column}'.")
        if entry.target is not None:
            raise InvalidImportFileError(
                f"'{entry.column}' goes to either a field or kept as an extra "
                + "detail, not both."
            )
        kept.append((index[entry.column], entry.extra))
    return kept


def _check_kept(
    kept: Sequence[tuple[int, ExtraField]], by_key: dict[str, FieldSpec]
) -> None:
    """Refuse kept columns that would clash, or more than an item may have."""
    if len(kept) > MAX_EXTRA_FIELDS:
        raise InvalidImportFileError(
            f"An item can have at most {MAX_EXTRA_FIELDS} extra fields."
        )
    keys: set[str] = set()
    for _, extra in kept:
        if not extra.title.strip():
            raise InvalidImportFileError(
                f"The field kept as '{extra.key}' needs a name."
            )
        if extra.key in by_key or extra.key in _BUILT_IN:
            raise InvalidImportFileError(
                f"'{extra.key}' is already a field of this item type."
            )
        check_key(extra.key)
        if extra.key in keys:
            raise InvalidImportFileError(
                f"'{extra.key}' is used for more than one column."
            )
        keys.add(extra.key)


def _extras(
    table: CsvTable, kept: Sequence[tuple[int, ExtraField]]
) -> list[tuple[int, FieldSpec, dict[str, Any] | None]]:
    """Each kept column's index, its conversion and the definition items get."""
    found: list[tuple[int, FieldSpec, dict[str, Any] | None]] = []
    for index, extra in kept:
        options = (
            choice_options((row[index] for row in table.rows), extra.title)
            if extra.kind is ExtraFieldKind.CHOICE
            else ()
        )
        found.append(
            (index, extra_spec(extra, options), extra_property(extra, options))
        )
    return found


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
            request.day_month_order,
        )
        listed = [(p.row, f"Row {p.row}, {p.field}: {p.message}.") for p in problems]
        for item in bundle.items:
            number = int(item.ref.removeprefix("row-"))
            own = (item.extra_schema or {}).get("properties", {})
            found = await self._graph.check_item_attributes(
                request.item_type,
                {k: v for k, v in item.attributes.items() if k not in own},
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
        order = suggest_day_month_order(cell for row in table.rows for cell in row)
        reading = DayMonthOrder.DAY_FIRST if order is None else order.order
        return ItemImportInspection(
            headers=table.headers,
            sample_rows=table.rows[:_SAMPLE_ROWS],
            row_count=len(table.rows),
            fields=tuple(fields),
            suggested_mapping=tuple(suggest_mapping(table.headers, fields)),
            encoding=table.encoding,
            day_month_order=order,
            column_kinds=tuple(
                ColumnKind(
                    column=header,
                    kind=suggest_kind((row[i] for row in table.rows), reading),
                )
                for i, header in enumerate(table.headers)
            ),
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
