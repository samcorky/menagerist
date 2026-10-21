"""First-run setup, sign-in and /me through the real app on Postgres."""

from typing import TYPE_CHECKING

import pytest
import sqlalchemy
from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.platform.database import get_engine, get_session_factory

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = pytest.mark.integration

AUTH = "/api/v1/auth"


@pytest.fixture
def client(postgres_url: str, postgres_sync_url: str) -> Iterator[TestClient]:
    """An in-process client on the real app, real hashing and a clean users table."""
    get_session_factory.cache_clear()
    get_engine.cache_clear()
    try:
        with TestClient(create_app()) as c:
            yield c
    finally:
        get_session_factory.cache_clear()
        get_engine.cache_clear()
        engine = sqlalchemy.create_engine(postgres_sync_url)
        with engine.begin() as connection:
            connection.execute(sqlalchemy.text("DELETE FROM sessions"))
            connection.execute(sqlalchemy.text("DELETE FROM users"))
        engine.dispose()


def test_setup_then_login_then_me(client: TestClient) -> None:
    """The first account signs in at setup, signs out, and signs back in."""
    assert client.get(f"{AUTH}/status").json() == {"setup_required": True}

    setup = client.post(
        f"{AUTH}/setup",
        json={
            "username": "Admin",
            "display_name": "Admin",
            "password": "a long passphrase",
        },
    )
    assert setup.status_code == 201
    assert client.get(f"{AUTH}/me").json()["username"] == "admin"
    assert client.get(f"{AUTH}/status").json() == {"setup_required": False}

    assert client.post(f"{AUTH}/logout").status_code == 204
    assert client.get(f"{AUTH}/me").status_code == 401

    wrong = client.post(
        f"{AUTH}/login", json={"username": "admin", "password": "wrong passphrase"}
    )
    assert wrong.status_code == 401
    login = client.post(
        f"{AUTH}/login", json={"username": "ADMIN", "password": "a long passphrase"}
    )
    assert login.status_code == 200
    me = client.get(f"{AUTH}/me")
    assert me.status_code == 200
    assert me.json()["role"] == "admin"
    again = client.post(
        f"{AUTH}/setup",
        json={"username": "x1x", "display_name": "x", "password": "a long passphrase"},
    )
    assert again.status_code == 409
