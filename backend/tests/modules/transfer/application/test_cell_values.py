"""Converting the text of a spreadsheet cell into a field's value."""

import pytest

from app.modules.transfer.application.cell_values import convert_cell
from app.modules.transfer.domain.errors import CellValueError
from app.modules.transfer.domain.tabular import FieldSpec


def _field(**overrides: object) -> FieldSpec:
    base: dict[str, object] = {
        "key": "f",
        "title": "Field",
        "json_type": "string",
        "kind": "text",
        "options": None,
    }
    return FieldSpec(**(base | overrides))  # type: ignore[arg-type]


def _convert(text: str, **overrides: object) -> object:
    return convert_cell(text, _field(**overrides), list_separator=",")


def test_text_is_used_as_written_without_surrounding_space() -> None:
    """Text keeps its content and loses the space around it."""
    assert _convert("  Alien ") == "Alien"


def test_a_blank_cell_is_left_out() -> None:
    """A blank cell gives no value, so the field is not stored."""
    assert _convert("   ") is None


def test_numbers_parse_as_integers_or_decimals() -> None:
    """Whole numbers stay whole, and decimals are accepted for number fields."""
    assert _convert("12", json_type="number", kind="number") == 12
    assert _convert("3.5", json_type="number", kind="number") == 3.5


def test_a_number_field_refuses_text_and_special_values() -> None:
    """Text, NaN and infinity are not numbers."""
    for text in ("x", "nan", "inf"):
        with pytest.raises(CellValueError, match="is not a number"):
            _convert(text, json_type="number", kind="number")


def test_an_integer_field_refuses_a_decimal() -> None:
    """A whole-number field does not take a fraction."""
    with pytest.raises(CellValueError, match="is not a whole number"):
        _convert("3.5", json_type="integer", kind="number")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("yes", True),
        ("Y", True),
        ("TRUE", True),
        ("1", True),
        ("no", False),
        ("n", False),
        ("False", False),
        ("0", False),
    ],
)
def test_yes_no_accepts_the_usual_words(text: str, expected: bool) -> None:
    """Yes and no come in several spellings, in any case."""
    assert _convert(text, json_type="boolean", kind="boolean") is expected


def test_yes_no_refuses_anything_else() -> None:
    """Anything but yes or no is refused, with the value in the message."""
    with pytest.raises(CellValueError, match="'maybe' is not yes or no"):
        _convert("maybe", json_type="boolean", kind="boolean")


def test_a_choice_matches_an_option_ignoring_case() -> None:
    """The stored value is the option as written in the list."""
    assert _convert("mint", kind="choice", options=("Mint", "Good")) == "Mint"


def test_a_choice_refuses_an_unknown_option_and_lists_the_options() -> None:
    """The message names the options, so the file can be fixed."""
    with pytest.raises(CellValueError, match="Mint, Good"):
        _convert("Fair", kind="choice", options=("Mint", "Good"))


def test_a_multiple_choice_splits_and_matches_each_part() -> None:
    """Several choices share one cell, split on the separator."""
    field = _field(kind="multichoice", options=("Mint", "Good"), multiple=True)
    assert convert_cell("mint, Good", field, list_separator=",") == ["Mint", "Good"]


def test_a_multiple_choice_uses_the_given_separator() -> None:
    """A semicolon separator leaves commas alone."""
    field = _field(kind="multichoice", options=("A, B", "C"), multiple=True)
    assert convert_cell("A, B; C", field, list_separator=";") == ["A, B", "C"]


def test_a_multiple_choice_refuses_an_unknown_part() -> None:
    """One unknown part refuses the whole cell."""
    field = _field(kind="multichoice", options=("Mint",), multiple=True)
    with pytest.raises(CellValueError, match="'Fair'"):
        convert_cell("Mint, Fair", field, list_separator=",")


def test_a_date_must_be_a_full_calendar_date() -> None:
    """A date is year, month and day."""
    assert _convert("2019-08-19", kind="date") == "2019-08-19"
    with pytest.raises(CellValueError, match="is not a date, use 2019-08-19"):
        _convert("19th Aug", kind="date")
    with pytest.raises(CellValueError, match="is not a date"):
        _convert("2019-02-31", kind="date")


@pytest.mark.parametrize("text", ["2019", "2019-08", "2019-08-19"])
def test_a_partial_date_accepts_year_month_or_day(text: str) -> None:
    """A partial date may stop at the year or the month."""
    assert _convert(text, kind="partialdate") == text


@pytest.mark.parametrize("text", ["2019-13", "19-08", "2019-02-31", "Aug 2019"])
def test_a_partial_date_refuses_the_rest(text: str) -> None:
    """Impossible and differently written dates are refused."""
    with pytest.raises(CellValueError, match="is not a date"):
        _convert(text, kind="partialdate")


def test_an_unimportable_field_refuses_with_its_reason() -> None:
    """A field the import cannot fill says why."""
    field = _field(importable=False, reason="Price cannot be imported yet")
    with pytest.raises(CellValueError, match="Price cannot be imported yet"):
        convert_cell("12", field, list_separator=",")


def test_a_field_of_an_unknown_shape_is_refused() -> None:
    """Without a known shape, nothing is guessed."""
    with pytest.raises(CellValueError, match="cannot be imported yet"):
        _convert("x", json_type="object", kind=None)
