"""Build a small FastAPI app and print everything the route-analysis caches touch.

Run as a script by `test_route_analysis_cache.py` twice, with and without the caches,
in fresh interpreters so FastAPI is unpatched the first time. The two outputs must
match; if a FastAPI upgrade changes what route construction depends on, they stop
matching. It holds no tests: pytest imports it and finds nothing to run.
"""
# ruff: noqa: D103  (the routes and dependencies are fixtures, named for the output)

import dataclasses
import json
import re
import sys
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Query, Security
from fastapi.dependencies.models import Dependant
from fastapi.testclient import TestClient

_SKIPPED = {"path"}


def _describe(value: object) -> object:
    if isinstance(value, Dependant):
        return {
            f.name: _describe(getattr(value, f.name))
            for f in dataclasses.fields(value)
            if f.name not in _SKIPPED
        }
    if isinstance(value, list | tuple):
        return [_describe(v) for v in value]
    if hasattr(value, "field_info"):
        field: Any = value
        return [field.name, repr(field.field_info), repr(field.field_info.annotation)]
    if callable(value):
        return getattr(value, "__qualname__", type(value).__name__)
    return re.sub(r" at 0x[0-9a-f]+", "", repr(value))


def session() -> str:
    return "session"


def guard(db: Annotated[str, Depends(session)]) -> str:
    return db


def by_id(item_id: int, db: Annotated[str, Depends(guard)]) -> int:
    return item_id


def scoped(db: Annotated[str, Depends(guard)]) -> str:
    return db


def times_ten(item_id: int) -> int:
    return item_id * 10


def main(mode: str) -> None:
    if mode == "cached":
        from app.entrypoints.api.shared import route_analysis_cache

        route_analysis_cache.install()

    app = FastAPI()

    @app.get("/items/{item_id}")
    def read_item(
        item_id: int,
        value: Annotated[int, Depends(by_id)],
        limit: Annotated[int, Query(ge=1, le=10)] = 5,
        tag: Annotated[int, Query(gt=0)] = 1,
        ratio: Annotated[float, Query(gt=0.0)] = 1.0,
    ) -> list[int]:
        return [item_id, value, limit, tag]

    @app.get("/other")
    def read_other(
        value: Annotated[int, Depends(by_id)],
        limit: Annotated[int, Query(ge=2)] = 5,
    ) -> list[int]:
        return [value, limit]

    @app.get("/scoped/{item_id}")
    def read_scoped(
        value: Annotated[str, Security(scoped, scopes=["read"])], item_id: int
    ) -> str:
        return value

    @app.get("/scoped-write")
    def read_scoped_write(
        value: Annotated[str, Security(scoped, scopes=["write"])],
    ) -> str:
        return value

    app.dependency_overrides[by_id] = times_ten
    client = TestClient(app)
    requests = [
        ("/items/3", {}),
        ("/items/3", {"limit": 0}),
        ("/items/3", {"limit": 11}),
        ("/items/3", {"tag": 0}),
        ("/items/3", {"ratio": 0}),
        ("/items/x", {}),
        ("/other", {"item_id": 4}),
        ("/other", {"item_id": 4, "limit": 1}),
        ("/other", {}),
        ("/scoped/1", {}),
        ("/scoped-write", {}),
    ]
    print(
        json.dumps(
            {
                "openapi": app.openapi(),
                "routes": {
                    r.path: _describe(r.dependant)  # type: ignore[attr-defined]
                    for r in app.routes
                    if hasattr(r, "dependant")
                },
                "responses": [
                    [path, params, client.get(path, params=params).json()]
                    for path, params in requests
                ],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main(sys.argv[1])
