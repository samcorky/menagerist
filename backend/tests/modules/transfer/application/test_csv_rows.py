"""Reading a CSV file and suggesting where its columns go."""

import pytest

from app.modules.transfer.application.csv_rows import (
    normalise_text,
    read_csv,
    suggest_mapping,
)
from app.modules.transfer.domain.errors import InvalidImportFileError
from app.modules.transfer.domain.tabular import (
    MAX_IMPORT_BYTES,
    MAX_IMPORT_ROWS,
    ColumnMapping,
    CsvEncoding,
    FieldSpec,
)


def _field(key: str, title: str | None = None) -> FieldSpec:
    return FieldSpec(
        key=key,
        title=title or key,
        json_type="string",
        kind="text",
        options=None,
    )


def test_reads_headers_and_rows() -> None:
    """Headers and rows come back as written."""
    table = read_csv(b"title,year\nAlien,1979\nAliens,1986\n")
    assert table.headers == ("title", "year")
    assert table.rows == (("Alien", "1979"), ("Aliens", "1986"))


def test_strips_a_byte_order_mark_and_header_space() -> None:
    """A BOM from a spreadsheet export does not stick to the first header."""
    table = read_csv("﻿ title , year \nAlien,1979\n".encode())
    assert table.headers == ("title", "year")


def test_handles_windows_line_endings_quotes_and_embedded_newlines() -> None:
    """Quoted commas and line breaks stay inside their cell."""
    data = b'title,notes\r\n"Alien, the film","line one\nline two"\r\n'
    table = read_csv(data)
    assert table.rows == (("Alien, the film", "line one\nline two"),)


@pytest.mark.parametrize("delimiter", [";", "\t"])
def test_sniffs_semicolons_and_tabs(delimiter: str) -> None:
    """The delimiter is read from the header line."""
    table = read_csv(f"title{delimiter}year\nAlien{delimiter}1979\n".encode())
    assert table.headers == ("title", "year")
    assert table.rows == (("Alien", "1979"),)


def test_an_empty_file_is_refused() -> None:
    """There is nothing to import."""
    with pytest.raises(InvalidImportFileError, match="empty"):
        read_csv(b"")


def test_a_file_with_only_headers_has_no_rows() -> None:
    """Headers alone are readable, and have no rows."""
    table = read_csv(b"title,year\n")
    assert table.rows == ()


@pytest.mark.parametrize(
    "data", [b"title,title\nA,B\n", b"title,\nA,B\n", b"title, \nA,B\n"]
)
def test_duplicate_and_blank_headers_are_refused(data: bytes) -> None:
    """Every column needs its own name."""
    with pytest.raises(InvalidImportFileError, match="header"):
        read_csv(data)


def test_a_row_of_the_wrong_width_is_refused_by_row_number() -> None:
    """The header is row 1, so the first item is row 2."""
    with pytest.raises(InvalidImportFileError, match=r"Row 3 has 3 cells"):
        read_csv(b"title,year\nAlien,1979\nAliens,1986,extra\n")


def test_blank_lines_are_skipped_not_counted_as_rows() -> None:
    """A trailing blank line is not an item."""
    table = read_csv(b"title\nAlien\n\n")
    assert table.rows == (("Alien",),)


def test_each_row_keeps_its_spreadsheet_number_past_blank_lines() -> None:
    """The header is row 1, and a skipped blank line still counts."""
    table = read_csv(b"title\nA\n\nB\n")
    assert table.rows == (("A",), ("B",))
    assert table.numbers == (2, 4)


def test_more_rows_than_the_limit_are_refused() -> None:
    """The message names the limit."""
    data = ("title\n" + "x\n" * (MAX_IMPORT_ROWS + 1)).encode()
    with pytest.raises(InvalidImportFileError, match="50,000"):
        read_csv(data)


def test_a_file_over_the_byte_limit_is_refused() -> None:
    """The message names the limit in megabytes."""
    with pytest.raises(InvalidImportFileError, match="50 MB"):
        read_csv(b"t" * (MAX_IMPORT_BYTES + 1))


def test_utf8_is_read_with_or_without_a_mark() -> None:
    """Accents survive, and the encoding is reported."""
    plain = read_csv("title\nRené\n".encode())
    marked = read_csv("\ufefftitle\nRené\n".encode())
    assert plain.rows == marked.rows == (("René",),)
    assert plain.encoding == marked.encoding == CsvEncoding.UTF_8


@pytest.mark.parametrize(
    "mark_and_codec", [(b"\xff\xfe", "utf-16-le"), (b"\xfe\xff", "utf-16-be")]
)
def test_utf16_is_read_by_its_mark(mark_and_codec: tuple[bytes, str]) -> None:
    """Excel's "Unicode Text" starts with a UTF-16 byte-order mark."""
    mark, codec = mark_and_codec
    data = mark + "title\tyear\nDéjà Vu\t1987\n".encode(codec)
    table = read_csv(data)
    assert table.headers == ("title", "year")
    assert table.rows == (("Déjà Vu", "1987"),)
    assert table.encoding == CsvEncoding.UTF_16


def test_windows_1252_is_the_fallback() -> None:
    """Excel's plain CSV on Western Windows is not valid UTF-8."""
    table = read_csv("title\nRené\nDéjà Vu\n€5\n".encode("cp1252"))
    assert table.rows == (("René",), ("Déjà Vu",), ("€5",))
    assert table.encoding == CsvEncoding.WINDOWS_1252


@pytest.mark.parametrize(
    "data",
    [b"title\nbad \x81 byte\n", b"title\n\x00\x01\x02\n"],
    ids=["byte Windows-1252 leaves undefined", "binary"],
)
def test_bytes_no_listed_encoding_reads_are_refused(data: bytes) -> None:
    """The message says what encodings are understood."""
    with pytest.raises(InvalidImportFileError, match="UTF-8, UTF-16 or Windows-1252"):
        read_csv(data)


def test_suggestions_match_key_then_title_ignoring_case_and_separators() -> None:
    """`signed_on`, `Signed On` and `signed-on` all find the field."""
    fields = [_field("signed_on", "Signed on"), _field("position")]
    mapping = suggest_mapping(["Signed-On", "POSITION"], fields)
    assert mapping == [
        ColumnMapping(column="Signed-On", target="signed_on"),
        ColumnMapping(column="POSITION", target="position"),
    ]


def test_title_matches_when_the_key_does_not() -> None:
    """A header written like the field's title finds it."""
    mapping = suggest_mapping(["Position and pen"], [_field("pos", "Position and pen")])
    assert mapping == [ColumnMapping(column="Position and pen", target="pos")]


def test_name_description_and_tags_have_aliases() -> None:
    """The built-in fields are found under their usual spreadsheet names."""
    mapping = suggest_mapping(["Title", "Notes", "Tags"], [])
    assert [m.target for m in mapping] == ["name", "description", "tags"]


def test_a_field_is_suggested_for_one_column_only() -> None:
    """The first matching column wins; later ones are left unmatched."""
    mapping = suggest_mapping(["position", "Position"], [_field("position")])
    assert [m.target for m in mapping] == ["position", None]


def test_unmatched_columns_are_ignored() -> None:
    """A column nothing matches has no target."""
    mapping = suggest_mapping(["whatever"], [_field("position")])
    assert mapping == [ColumnMapping(column="whatever", target=None)]


def test_a_single_cell_over_the_csv_field_limit_is_refused() -> None:
    """A cell too large for the CSV reader is refused, not a server error."""
    data = b"title,notes\nAlien," + b"x" * 200_000 + b"\n"
    with pytest.raises(InvalidImportFileError, match="not valid CSV"):
        read_csv(data)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("  eBay ", "eBay"),
        ("Rick   Astley", "Rick Astley"),
        ("Rick	Astley", "Rick Astley"),
        ("Café", "Café"),
        ("   ", ""),
    ],
)
def test_normalise_text_trims_collapses_spaces_and_composes(
    text: str, expected: str
) -> None:
    """Text is trimmed, its runs of spaces collapsed and its accents composed."""
    assert normalise_text(text) == expected
