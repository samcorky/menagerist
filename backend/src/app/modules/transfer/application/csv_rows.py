"""Read a CSV file into headers and rows, and suggest where its columns go."""

import codecs
import csv
import io
import re
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from app.modules.transfer.domain.errors import InvalidImportFileError
from app.modules.transfer.domain.tabular import (
    MAX_IMPORT_BYTES,
    MAX_IMPORT_ROWS,
    ColumnMapping,
    CsvEncoding,
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
    # The encoding the bytes were read as, named as people know it.
    encoding: CsvEncoding = CsvEncoding.UTF_8


def read_csv(data: bytes) -> CsvTable:
    """Read `data` as CSV in UTF-8, UTF-16 or Windows-1252.

    Row numbers in messages follow a spreadsheet: the header is row 1.

    Raises:
        InvalidImportFileError: the file is too big, empty, in no encoding read
            here, or its headers or rows are not usable.
    """
    if len(data) > MAX_IMPORT_BYTES:
        raise InvalidImportFileError(
            f"The file is over the {MAX_IMPORT_BYTES // (1024 * 1024)} MB limit."
        )
    text, encoding = _decode(data)
    if not text.strip():
        raise InvalidImportFileError("The file is empty.")
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=_delimiter(text))
    try:
        return replace(_table(reader), encoding=encoding)
    except csv.Error as error:
        raise InvalidImportFileError(f"The file is not valid CSV: {error}") from None


def _decode(data: bytes) -> tuple[str, CsvEncoding]:
    """Return the text of `data` and the encoding it was read as.

    A byte-order mark names the encoding. Without one, text that is valid UTF-8 is
    UTF-8 (text in a legacy encoding almost never is), and anything else is read as
    Windows-1252, which is what Excel's plain "CSV" writes on Western Windows.
    """
    try:
        if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
            return data.decode("utf-16"), CsvEncoding.UTF_16
        # Text in UTF-8 or Windows-1252 has no NUL; binary files nearly always do.
        if b"\0" in data:
            raise UnicodeDecodeError("utf-8", data, 0, 1, "binary")
        try:
            return data.decode("utf-8-sig"), CsvEncoding.UTF_8
        except UnicodeDecodeError:
            return data.decode("cp1252"), CsvEncoding.WINDOWS_1252
    except UnicodeDecodeError:
        raise InvalidImportFileError(
            "The file is not text in UTF-8, UTF-16 or Windows-1252."
        ) from None


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
