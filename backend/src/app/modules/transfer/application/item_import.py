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
    normalise_text,
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
from app.modules.transfer.application.item_connections import ImportedRow, connect_rows
from app.modules.transfer.application.permissions import TransferPermission
from app.modules.transfer.application.pipeline import (
    AppliedBundle,
    apply_bundle,
    plan_bundle,
)
from app.modules.transfer.domain.bundle import (
    Bundle,
    BundleItem,
    BundleItemType,
    BundleSource,
)
from app.modules.transfer.domain.entity_kind import EntityKind
from app.modules.transfer.domain.errors import CellValueError, InvalidImportFileError
from app.modules.transfer.domain.plan import ClashPolicy, Plan, PlanAction, PlanBlocker
from app.modules.transfer.domain.tabular import (
    MAX_CONNECTION_COLUMNS,
    MAX_EXTRA_FIELDS,
    MAX_IMPORT_ROWS,
    MAX_LISTED_PROBLEMS,
    CellProblem,
    ColumnKind,
    ColumnMapping,
    ConnectionColumn,
    CsvEncoding,
    DayMonthOrder,
    DayMonthOrderGuess,
    ExtraField,
    ExtraFieldKind,
    FieldSpec,
)
from app.modules.transfer.ports.unit_of_work import TransferRepos, TransferUnitOfWork
from app.shared_kernel.access import Access, Requires
from app.shared_kernel.cqrs import CommandHandler, QueryHandler, UseCase

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.modules.transfer.ports.source_link_repository import SourceLinkRepository
    from app.modules.transfer.ports.targets import GraphTarget, PresetTarget
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()

_BUILT_IN = ("name", "description", "tags")
_SAMPLE_ROWS = 5
# Kinds the import builds on but never makes, so its preview does not list them.
_NOT_LISTED = (EntityKind.ITEM_TYPE, EntityKind.RELATIONSHIP_TYPE)


@dataclass(frozen=True, kw_only=True, eq=False)
class ItemImportRequest:
    """A CSV file, the item type it becomes, and how its columns map to fields.

    `key_field` is the field or kept detail that recognises rows imported before,
    and `restore` holds the keys of rows and connections deleted after importing
    that are to be created again. Each of `connections` joins every row to an item
    its column names.
    """

    data: bytes
    item_type: str
    mapping: tuple[ColumnMapping, ...] = ()
    list_separator: str = ","
    day_month_order: DayMonthOrder = DayMonthOrder.DAY_FIRST
    key_field: str | None = None
    restore: tuple[str, ...] = ()
    connections: tuple[ConnectionColumn, ...] = ()


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
    key_field: str | None = None,
    connections: Sequence[ConnectionColumn] = (),
) -> tuple[Bundle, list[CellProblem]]:
    """Turn the rows into a bundle of items of `item_type`, with what is wrong.

    A row with a problem is left out of the bundle and reported. With `key_field`,
    the bundle's source is the type and that field, and each item's source key is
    its cell in that column as written, normalised. Each of `connections` adds the
    items its column names, found by name, and a connection from each row to one.

    Raises:
        InvalidImportFileError: the mapping cannot be used for this file and type,
            `key_field` is not a column it maps or keeps, or a connection column is
            not in the file.
    """
    columns, kept = _columns(table.headers, mapping, fields)
    key_index = None if key_field is None else _key_index(key_field, columns, kept)
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
    rows: list[ImportedRow] = []
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
        key = None if key_index is None else normalise_text(cells[key_index]) or None
        items.append(
            BundleItem(
                ref=f"row-{number}",
                type_ref=item_type,
                name=name,
                description=_cell(cells, columns, "description"),
                attributes=attributes,
                tags=_tags(cells, columns, list_separator),
                extra_schema={"type": "object", "properties": own} if own else None,
                source_key=key,
            )
        )
        rows.append(ImportedRow(ref=f"row-{number}", cells=cells, key=key))
    connected = connect_rows(table.headers, rows, connections, item_type)
    bundle = Bundle(
        id=f"csv-{item_type}",
        source=(
            None
            if key_field is None
            else BundleSource(
                name=f"csv:{item_type}:{key_field}",
                key_field=key_field,
                require_keys=True,
            )
        ),
        relationship_types=connected.relationship_types,
        item_types=(
            BundleItemType(ref=item_type, slug=item_type, label=item_type),
            *connected.item_types,
        ),
        items=(*items, *connected.items),
        connections=connected.connections,
        # Rows, and an item named in each connection column of each row.
        item_limit=MAX_IMPORT_ROWS * (1 + MAX_CONNECTION_COLUMNS),
        connection_limit=MAX_IMPORT_ROWS * MAX_CONNECTION_COLUMNS,
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


def _key_index(
    key_field: str,
    columns: dict[str, int],
    kept: Sequence[tuple[int, ExtraField]],
) -> int:
    """The column holding each row's key: the name, a mapped field or a kept one.

    Raises:
        InvalidImportFileError: no such column is mapped or kept.
    """
    if key_field in columns and key_field not in ("description", "tags"):
        return columns[key_field]
    for index, extra in kept:
        if extra.key == key_field:
            return index
    raise InvalidImportFileError(
        "Recognise rows by a column you map to a field or keep."
    )


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


class _Importer:
    """Reads the file and plans it into the type, for each of the use cases."""

    def __init__(self, presets: PresetTarget, graph: GraphTarget) -> None:
        self.presets = presets
        self.graph = graph

    async def fields(self, slug: str) -> list[FieldSpec]:
        fields = await self.graph.item_type_fields(slug)
        if fields is None:
            raise InvalidImportFileError(f"You have no item type called '{slug}'.")
        return fields

    async def _check_connections(self, columns: Sequence[ConnectionColumn]) -> None:
        """Refuse too many connection columns, or types the person does not have."""
        if len(columns) > MAX_CONNECTION_COLUMNS:
            raise InvalidImportFileError(
                f"Connect at most {MAX_CONNECTION_COLUMNS} columns."
            )
        for column in columns:
            await self.fields(column.item_type)
            slug = column.relationship_type
            if not await self.graph.slug_taken(EntityKind.RELATIONSHIP_TYPE, slug):
                raise InvalidImportFileError(
                    f"You have no relationship type called '{slug}'."
                )

    async def plan(
        self, request: ItemImportRequest, extras: BundleExtras
    ) -> tuple[Bundle, Plan]:
        """Plan the file; every problem in it becomes a blocker on the plan."""
        fields = await self.fields(request.item_type)
        await self._check_connections(request.connections)
        bundle, problems = build_item_bundle(
            read_csv(request.data),
            request.mapping,
            fields,
            request.item_type,
            request.list_separator,
            request.day_month_order,
            request.key_field,
            request.connections,
        )
        listed = [(p.row, f"Row {p.row}, {p.field}: {p.message}.") for p in problems]
        for item in bundle.items:
            if item.lookup is not None:
                continue  # just a name; a type's required fields are advisory
            number = int(item.ref.removeprefix("row-"))
            own = (item.extra_schema or {}).get("properties", {})
            found = await self.graph.check_item_attributes(
                request.item_type,
                {k: v for k, v in item.attributes.items() if k not in own},
            )
            listed.extend((number, f"Row {number}, {text}.") for text in found)
        plan = await plan_bundle(
            bundle, self.presets, self.graph, clash=ClashPolicy.SKIP, extras=extras
        )
        blockers = _blockers([text for _, text in sorted(listed, key=lambda e: e[0])])
        return bundle, Plan(
            bundle_id=plan.bundle_id,
            entities=plan.entities,
            blockers=(*plan.blockers, *_too_many(plan), *blockers),
        )


def _link_extras(
    request: ItemImportRequest, links: SourceLinkRepository, actor: Actor
) -> BundleExtras:
    """What planning and applying need to recognise and link the actor's rows."""
    return BundleExtras(
        links=links, owner_id=actor.id, restore=frozenset(request.restore)
    )


def _too_many(plan: Plan) -> list[PlanBlocker]:
    """Block an import that would create more items than a file may have rows."""
    creating = sum(
        1
        for e in plan.entities
        if e.kind is EntityKind.ITEM and e.action is PlanAction.CREATE
    )
    if creating <= MAX_IMPORT_ROWS:
        return []
    return [
        PlanBlocker(
            code="ImportTooLargeError",
            reason=f"This import would create more than {MAX_IMPORT_ROWS:,} items.",
        )
    ]


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


class InspectItemImport(UseCase[ItemImportRequest, ItemImportInspection]):
    """Read a CSV and describe it, with the type's fields and a suggested mapping.

    Raises:
        ValidationError: the file is not a usable CSV, or the type does not exist.
    """

    access: ClassVar[Access] = Requires(TransferPermission.BUNDLE_IMPORT)

    def __init__(
        self, guard: AccessGuard, presets: PresetTarget, graph: GraphTarget
    ) -> None:
        """Initialise with the access guard and the targets."""
        self._guard = guard
        self._importer = _Importer(presets, graph)

    async def _handle(
        self, request: ItemImportRequest, actor: Actor
    ) -> ItemImportInspection:
        """Return the headers, a few rows and a first guess at the mapping."""
        fields = await self._importer.fields(request.item_type)
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


class PlanItemImport(QueryHandler[TransferRepos, ItemImportRequest, Plan]):
    """Return what importing the file would do; nothing is written.

    Every value that cannot be imported is a blocker naming its row and field. With
    a key column, rows imported before are recognised and named, and a row whose
    item was deleted is left out unless the request restores it.

    Raises:
        ValidationError: the file or the mapping cannot be used, or the type does
            not exist.
    """

    access: ClassVar[Access] = Requires(TransferPermission.BUNDLE_IMPORT)

    def __init__(
        self,
        repos: TransferRepos,
        guard: AccessGuard,
        presets: PresetTarget,
        graph: GraphTarget,
    ) -> None:
        """Initialise with the link store, the access guard and the targets."""
        super().__init__(repos, guard)
        self._importer = _Importer(presets, graph)

    async def _handle(self, request: ItemImportRequest, actor: Actor) -> Plan:
        """Plan the items and connections, leaving out the types they build on."""
        _, plan = await self._importer.plan(
            request, _link_extras(request, self._repos.links, actor)
        )
        return Plan(
            bundle_id=plan.bundle_id,
            entities=tuple(e for e in plan.entities if e.kind not in _NOT_LISTED),
            blockers=plan.blockers,
        )


class ImportItems(CommandHandler[TransferUnitOfWork, ItemImportRequest, AppliedBundle]):
    """Import the file: plan it as `PlanItemImport` does, then create the items.

    The links that recognise the rows next time are committed once the items are
    made; should that fail, the next import finds the items by their key instead.

    Raises:
        ValidationError: the file or the mapping cannot be used, or the type does
            not exist.
        BundleConflictError: the plan has problems.
    """

    access: ClassVar[Access] = Requires(TransferPermission.BUNDLE_IMPORT)

    def __init__(
        self,
        uow: TransferUnitOfWork,
        guard: AccessGuard,
        presets: PresetTarget,
        graph: GraphTarget,
    ) -> None:
        """Initialise with the unit of work, the access guard and the targets."""
        super().__init__(uow, guard)
        self._importer = _Importer(presets, graph)

    async def _handle(self, request: ItemImportRequest, actor: Actor) -> AppliedBundle:
        """Plan again, and apply only a plan with nothing wrong."""
        async with self._uow as repos:
            # Planning fills the extras with what applying reads, so both share them.
            extras = _link_extras(request, repos.links, actor)
            bundle, plan = await self._importer.plan(request, extras)
            applied = await apply_bundle(
                plan,
                bundle,
                self._importer.presets,
                self._importer.graph,
                extras=extras,
            )
            await self._uow.commit()
        logger.info("items imported", created=applied.total_created)
        return applied
