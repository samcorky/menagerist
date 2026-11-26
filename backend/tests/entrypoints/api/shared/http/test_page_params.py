from enum import StrEnum
from typing import Annotated

import pytest
from fastapi import FastAPI, Query
from fastapi.testclient import TestClient

# FastAPI reads the route's annotations at runtime, so these cannot be type-only.
from app.entrypoints.api.shared.http.parameters import PageParams, SearchPageParams  # noqa: TC001
from app.shared_kernel.paging import SortOrder


class _Sort(StrEnum):
    NAME = "name"
    CREATED_AT = "created_at"


def _app() -> FastAPI:
    app = FastAPI()

    @app.get("/rows")
    def list_rows(
        page: Annotated[PageParams[_Sort], Query()],
    ) -> dict[str, str | int | None]:
        return {
            "after": None if page.after is None else str(page.after),
            "limit": page.limit,
            "order": page.order,
            "sort": page.sort,
        }

    @app.get("/searchable")
    def search_rows(page: Annotated[SearchPageParams[_Sort], Query()]) -> str | None:
        return page.q

    return app


@pytest.mark.fast
def test_defaults_are_the_first_page_by_id_ascending() -> None:
    """Leaving every parameter out asks for the first 50 rows, oldest first."""
    body = TestClient(_app()).get("/rows").json()
    assert body == {"after": None, "limit": 50, "order": SortOrder.ASC, "sort": None}


@pytest.mark.fast
def test_each_parameter_is_read_from_the_query_string() -> None:
    """Every field, including the route's own `sort`, comes from the query."""
    cursor = "0198a2b4-0000-7000-8000-000000000000"
    response = TestClient(_app()).get(
        "/rows", params={"after": cursor, "limit": 5, "order": "desc", "sort": "name"}
    )
    assert response.json() == {
        "after": cursor,
        "limit": 5,
        "order": "desc",
        "sort": "name",
    }


@pytest.mark.fast
@pytest.mark.parametrize(
    "params",
    [{"sort": "bogus"}, {"order": "sideways"}, {"limit": 0}, {"limit": 101}],
)
def test_an_invalid_value_is_a_422(params: dict[str, str | int]) -> None:
    """An unknown key or direction, or a limit outside 1-100, is unparseable."""
    assert TestClient(_app()).get("/rows", params=params).status_code == 422


@pytest.mark.fast
def test_the_schema_lists_the_fields_as_separate_described_query_parameters() -> None:
    """The model is flattened, so the generated client sees ordinary parameters."""
    parameters = _app().openapi()["paths"]["/rows"]["get"]["parameters"]
    assert {p["name"] for p in parameters} == {"after", "limit", "order", "sort"}
    assert all(p["in"] == "query" and p["description"] for p in parameters)


@pytest.mark.fast
def test_a_searchable_list_also_takes_q() -> None:
    """`SearchPageParams` adds a text filter of at most 200 characters."""
    client = TestClient(_app())
    assert client.get("/searchable", params={"q": "nebula"}).json() == "nebula"
    assert client.get("/searchable", params={"q": "x" * 201}).status_code == 422
    names = {
        p["name"] for p in _app().openapi()["paths"]["/searchable"]["get"]["parameters"]
    }
    assert names == {"after", "limit", "sort", "order", "q"}
