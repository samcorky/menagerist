from collections.abc import Callable
from datetime import datetime
from uuid import uuid7

import pytest
from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.platform.config import get_scheduler_settings

URL = "/api/v1/scheduling/schedule-preview"

type AsUser = Callable[..., None]


def client(as_user: AsUser, role: str = "admin") -> TestClient:
    """The app signed in as someone with the given role."""
    app = create_app()
    as_user(app, uuid7(), role)
    return TestClient(app)


def test_it_returns_the_next_runs_in_the_instance_zone(as_user: AsUser) -> None:
    """Runs come back as increasing instants with the zone they are read in."""
    response = client(as_user).get(URL, params={"expression": "0 3 * * *"})
    assert response.status_code == 200
    body = response.json()
    assert body["timezone"] == get_scheduler_settings().timezone.key
    runs = [datetime.fromisoformat(run) for run in body["runs"]]
    assert len(runs) == 3
    assert runs == sorted(runs)
    assert response.headers["cache-control"] == "private, no-store"


def test_the_count_is_honoured(as_user: AsUser) -> None:
    """Ask for five, get five."""
    response = client(as_user).get(
        URL, params={"expression": "*/5 * * * *", "count": 5}
    )
    assert len(response.json()["runs"]) == 5


def test_an_empty_schedule_has_no_runs(as_user: AsUser) -> None:
    """Off is not an error."""
    for params in ({"expression": ""}, {}):
        response = client(as_user).get(URL, params=params)
        assert (response.status_code, response.json()["runs"]) == (200, [])


def test_an_unreadable_schedule_is_a_problem_response(as_user: AsUser) -> None:
    """The evaluator's refusal reaches the caller as a 400 with a reason."""
    response = client(as_user).get(URL, params={"expression": "61 * * * *"})
    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert "61 * * * *" in response.json()["detail"]


@pytest.mark.parametrize(
    "params", [{"count": 0}, {"count": 11}, {"expression": "x" * 201}]
)
def test_out_of_range_requests_are_rejected(
    as_user: AsUser, params: dict[str, str | int]
) -> None:
    """Bad counts and over-long expressions never reach the evaluator."""
    assert client(as_user).get(URL, params=params).status_code == 422


def test_members_are_refused(as_user: AsUser) -> None:
    """Only administrators may preview."""
    response = client(as_user, role="member").get(
        URL, params={"expression": "0 3 * * *"}
    )
    assert response.status_code == 403
