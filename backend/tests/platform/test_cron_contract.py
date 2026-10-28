"""The server decides what a schedule is; the browser only explains it.

`shared/contracts/cron-conformance.json` is read by this test and by
`frontend/tests/cron-conformance.test.ts`, so the two cannot drift apart.
"""

import json
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from app.platform.config._types import Cron
from app.platform.shared_data import shared_data_path

CONTRACT: dict[str, Any] = json.loads(
    shared_data_path("contracts/cron-conformance.json").read_text(encoding="utf-8")
)
SCHEDULE = TypeAdapter(Cron)

ACCEPTED = [
    *(case["expression"] for case in CONTRACT["valid"]),
    *(case["cron"] for case in CONTRACT["sentences"]),
    *CONTRACT["custom"],
]
REFUSED = [*CONTRACT["invalid"], *CONTRACT["server_rejects_only"]]


@pytest.mark.parametrize("expression", ACCEPTED, ids=repr)
def test_the_server_accepts_every_schedule_the_browser_can_explain_or_build(
    expression: str,
) -> None:
    """Everything the form offers, and everything it explains, is saveable."""
    assert SCHEDULE.validate_python(expression) == expression


@pytest.mark.parametrize("expression", REFUSED, ids=repr)
def test_the_server_refuses_the_schedules_the_contract_marks_invalid(
    expression: str,
) -> None:
    """These must stay refused, including the cases only the server can see."""
    with pytest.raises(ValidationError, match="invalid cron schedule"):
        SCHEDULE.validate_python(expression)


def test_an_empty_schedule_is_valid_and_means_off() -> None:
    """The form sends an empty string to turn a job off."""
    assert SCHEDULE.validate_python("") == ""
    assert {"kind": "off"} in [case["sentence"] for case in CONTRACT["sentences"]]
