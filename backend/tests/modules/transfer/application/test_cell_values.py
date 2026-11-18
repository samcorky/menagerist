"""Converting the text of a spreadsheet cell into a field's value."""

import pytest

from app.modules.transfer.application.cell_values import (
    convert_cell,
    suggest_date_order,
)
from app.modules.transfer.domain.errors import CellValueError
from app.modules.transfer.domain.tabular import DateOrder, FieldSpec


def _field(**overrides: object) -> FieldSpec:
    base: dict[str, object] = {
        "key": "f",
        "title": "Field",
        "json_type": "string",
        "kind": "text",
        "options": None,
    }
    return FieldSpec(**(base | overrides))  # type: ignore[arg-type]


def _convert(
    text: str, order: DateOrder = DateOrder.DAY_FIRST, **overrides: object
) -> object:
    return convert_cell(text, _field(**overrides), list_separator=",", date_order=order)


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


@pytest.mark.parametrize(
    "text", ["2019-13", "19-08", "2019-02-31", "13/2019", "Foo-18", "19th Aug"]
)
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


@pytest.mark.parametrize(
    ("text", "stored"),
    [
        ("08/2019", "2019-08"),
        ("8/2019", "2019-08"),
        ("Oct-18", "2018-10"),
        ("oct 2018", "2018-10"),
        ("October 2018", "2018-10"),
        ("Sept-99", "1999-09"),
        ("19/08/2019", "2019-08-19"),
        ("1/2/19", "2019-02-01"),
    ],
)
def test_a_partial_date_reads_excels_shapes(text: str, stored: str) -> None:
    """Every shape reads into the one stored form."""
    assert _convert(text, kind="partialdate") == stored


@pytest.mark.parametrize(
    ("text", "stored"),
    [("49", "2049"), ("00", "2000"), ("50", "1950"), ("99", "1999")],
)
def test_two_digit_years_pivot_at_fifty(text: str, stored: str) -> None:
    """00 to 49 is 2000 to 2049, and 50 to 99 is 1950 to 1999."""
    assert _convert(f"Jan-{text}", kind="partialdate") == f"{stored}-01"
    assert _convert(f"01/02/{text}", kind="date") == f"{stored}-02-01"


def test_three_parts_follow_the_chosen_order() -> None:
    """03/04/2019 is 3 April or 4 March, as chosen."""
    assert _convert("03/04/2019", kind="date") == "2019-04-03"
    assert _convert("03/04/2019", DateOrder.MONTH_FIRST, kind="date") == "2019-03-04"


def test_an_impossible_three_part_date_is_refused() -> None:
    """31/04 is no date, and 19/08 is none month first."""
    with pytest.raises(CellValueError, match="is not a date"):
        _convert("31/04/2019", kind="date")
    with pytest.raises(CellValueError, match="is not a date"):
        _convert("19/08/2019", DateOrder.MONTH_FIRST, kind="date")


def test_a_column_may_mix_shapes() -> None:
    """Each cell is read on its own."""
    cells = ["2019", "2019-08", "08/2019", "Oct-18", "19/08/2019"]
    stored = [_convert(c, kind="partialdate") for c in cells]
    assert stored == ["2019", "2019-08", "2019-08", "2018-10", "2019-08-19"]


@pytest.mark.parametrize("text", ["08/2019", "Oct-18", "2019", "2019-08"])
def test_a_plain_date_refuses_a_value_with_no_day(text: str) -> None:
    """The message says a day is missing, and where a partial date would fit."""
    with pytest.raises(CellValueError, match="no day"):
        _convert(text, kind="date")


def test_suggest_none_without_three_part_dates() -> None:
    """With nothing ambiguous to read, no choice is offered."""
    assert suggest_date_order(["2019-08-19", "Oct-18", "08/2019", "x"]) is None


def test_suggest_day_first_when_a_first_number_is_over_twelve() -> None:
    """19/08/2019 can only be day first."""
    guess = suggest_date_order(["03/04/2019", "19/08/2019"])
    assert guess is not None
    assert (guess.order, guess.certain) == (DateOrder.DAY_FIRST, True)


def test_suggest_month_first_when_a_second_number_is_over_twelve() -> None:
    """08/19/2019 can only be month first."""
    guess = suggest_date_order(["03/04/2019", "08/19/2019"])
    assert guess is not None
    assert (guess.order, guess.certain) == (DateOrder.MONTH_FIRST, True)


def test_suggest_day_first_unsure_when_nothing_decides() -> None:
    """Without evidence, or with conflicting evidence, day first is a guess."""
    for cells in (["03/04/2019"], ["19/08/2019", "08/19/2019"]):
        guess = suggest_date_order(cells)
        assert guess is not None
        assert (guess.order, guess.certain) == (DateOrder.DAY_FIRST, False)
