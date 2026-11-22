"""Turn a CSV's connection columns into the items they name and the connections.

Each non-empty cell names one item of the column's type. Names that differ only in
case or spacing are one item, found or created once for the whole file.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.modules.transfer.application.csv_rows import normalise_text
from app.modules.transfer.domain.bundle import (
    BundleConnection,
    BundleItem,
    BundleItemType,
    BundleRelationshipType,
)
from app.modules.transfer.domain.errors import InvalidImportFileError
from app.modules.transfer.domain.tabular import ConnectionColumn, ConnectionEnd

if TYPE_CHECKING:
    from collections.abc import Sequence

# Joins the parts of a connection's source key; whitespace, so no name holds it.
_KEY_SEPARATOR = "\x1f"


@dataclass(kw_only=True, frozen=True, eq=False)
class ImportedRow:
    """A row that became an item: its ref, its cells and its key, if it has one."""

    ref: str
    cells: tuple[str, ...]
    key: str | None


@dataclass(kw_only=True, frozen=True, eq=False)
class Connected:
    """What the connection columns add to the bundle."""

    items: tuple[BundleItem, ...] = ()
    connections: tuple[BundleConnection, ...] = ()
    item_types: tuple[BundleItemType, ...] = ()
    relationship_types: tuple[BundleRelationshipType, ...] = ()


def connect_rows(
    headers: Sequence[str],
    rows: Sequence[ImportedRow],
    columns: Sequence[ConnectionColumn],
    item_type: str,
) -> Connected:
    """Return the items each row's connection cells name, and the connections.

    A connection's source key is the row's key, the column and the name as written,
    case-folded, so renaming the item later does not bring back a deleted one.

    Raises:
        InvalidImportFileError: the file has no such column.
    """
    index = {header: i for i, header in enumerate(headers)}
    for column in columns:
        if column.column not in index:
            raise InvalidImportFileError(f"The file has no column '{column.column}'.")
    named: dict[tuple[str, str], BundleItem] = {}
    connections: list[BundleConnection] = []
    for row in rows:
        for column in columns:
            name = normalise_text(row.cells[index[column.column]])
            if not name:
                continue
            folded = name.casefold()
            other = named.get((column.item_type, folded))
            if other is None:
                other = BundleItem(
                    ref=f"named-{len(named)}",
                    type_ref=column.item_type,
                    name=name,
                    lookup=column.on_missing,
                )
                named[column.item_type, folded] = other
            source, target = (row.ref, other.ref)
            if column.row_end is ConnectionEnd.TARGET:
                source, target = target, source
            key = (
                None
                if row.key is None
                else _KEY_SEPARATOR.join((row.key, column.column, folded))
            )
            connections.append(
                BundleConnection(
                    source_ref=source,
                    target_ref=target,
                    type_ref=column.relationship_type,
                    source_key=key,
                )
            )
    others = dict.fromkeys(c.item_type for c in columns if c.item_type != item_type)
    relationships = dict.fromkeys(c.relationship_type for c in columns)
    return Connected(
        items=tuple(named.values()),
        connections=tuple(connections),
        item_types=tuple(
            BundleItemType(ref=slug, slug=slug, label=slug) for slug in others
        ),
        relationship_types=tuple(
            BundleRelationshipType(ref=slug, slug=slug, label=slug)
            for slug in relationships
        ),
    )
