"""Read a CSV file into headers and rows, and suggest where its columns go."""

import csv
import io
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.modules.transfer.domain.errors import InvalidImportFileError
from app.modules.transfer.domain.tabular import (
    MAX_IMPORT_BYTES,
    MAX_IMPORT_ROWS,
    ColumnMapping,
    FieldSpec,
)

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

_DELIMITERS = (",", ";", "\t")
_ALIASES = {
    "name": frozenset({"name", "title"}),
    "description": frozenset({"description", "notes", "note"}),
    "tags": frozenset({"tags", "tag"}),
}


@dataclass(frozen=True, kw_only=True, eq=False)
class CsvTable:
    """A file's headers and, under them, one tuple of cell text per row."""

    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    # The spreadsheet row of each of `rows`; the header is row 1, blank lines count.
    numbers: tuple[int, ...] = ()


def read_csv(data: bytes) -> CsvTable:
    """Read `data` as UTF-8 CSV.

    Row numbers in messages follow a spreadsheet: the header is row 1.

    Raises:
        InvalidImportFileError: the file is too big, empty, not UTF-8, or its
            headers or rows are not usable.
    """
    if len(data) > MAX_IMPORT_BYTES:
        raise InvalidImportFileError(
            f"The file is over the {MAX_IMPORT_BYTES // (1024 * 1024)} MB limit."
        )
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise InvalidImportFileError("The file is not UTF-8 text.") from None
    if not text.strip():
        raise InvalidImportFileError("The file is empty.")
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=_delimiter(text))
    try:
        return _table(reader)
    except csv.Error as error:
        raise InvalidImportFileError(f"The file is not valid CSV: {error}") from None


def _delimiter(text: str) -> str:
    header = text.splitlines()[0]
    return max(_DELIMITERS, key=header.count)


def _table(reader: Iterator[list[str]]) -> CsvTable:
    headers = tuple(cell.strip() for cell in next(reader))
    if not all(headers) or len(set(headers)) != len(headers):
        raise InvalidImportFileError(
            "Every column needs its own name in the header row."
        )
    rows: list[tuple[str, ...]] = []
    numbers: list[int] = []
    for number, cells in enumerate(reader, start=2):
        if not cells:
            continue
        if len(cells) != len(headers):
            raise InvalidImportFileError(
                f"Row {number} has {len(cells)} cells but the header has "
                + f"{len(headers)}."
            )
        rows.append(tuple(cells))
        numbers.append(number)
        if len(rows) > MAX_IMPORT_ROWS:
            raise InvalidImportFileError(
                f"The file has more than the {MAX_IMPORT_ROWS:,} rows allowed."
            )
    return CsvTable(headers=headers, rows=tuple(rows), numbers=tuple(numbers))


def _plain(text: str) -> str:
    """Lowercase `text` without spaces, hyphens and underscores."""
    return re.sub(r"[\s_-]+", "", text).casefold()


def suggest_mapping(
    headers: Sequence[str], fields: Sequence[FieldSpec]
) -> list[ColumnMapping]:
    """Suggest a target for each header: a field by key or title, else a built-in.

    A target is suggested for one column only; the first match wins.
    """
    by_name: dict[str, str] = {}
    for field in fields:
        by_name.setdefault(_plain(field.key), field.key)
    for field in fields:
        by_name.setdefault(_plain(field.title), field.key)
    for target, names in _ALIASES.items():
        for name in names:
            by_name.setdefault(name, target)
    used: set[str] = set()
    suggested: list[ColumnMapping] = []
    for header in headers:
        found = by_name.get(_plain(header))
        if found is not None and found not in used:
            used.add(found)
            suggested.append(ColumnMapping(column=header, target=found))
        else:
            suggested.append(ColumnMapping(column=header, target=None))
    return suggested
