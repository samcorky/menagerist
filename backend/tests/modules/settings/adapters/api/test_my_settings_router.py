"""`/me/settings`: a person's own preferences over HTTP."""

from collections.abc import Callable
from typing import TYPE_CHECKING, Annotated, Literal
from uuid import UUID, uuid7

import pytest
from pydantic import Field
from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.entrypoints.api.shared.access_guard import get_access_guard
from app.entrypoints.api.shared.dependencies import get_current_actor
from app.entrypoints.api.shared.settings_reader import get_settings_catalogue
from app.modules.settings.adapters.api.dependencies import (
    get_get_my_settings_schema_use_case,
    get_list_my_settings_use_case,
    get_reset_my_setting_use_case,
    get_update_my_settings_use_case,
)
from app.modules.settings.adapters.persistence.in_memory_setting_value_repository import (  # noqa: E501
    InMemorySettingValueRepository,
)
from app.modules.settings.adapters.persistence.unit_of_work import (
    create_in_memory_settings_uow,
)
from app.modules.settings.adapters.platform.deployment_catalogue import build_catalogue
from app.modules.settings.application.get_my_settings_schema import GetMySettingsSchema
from app.modules.settings.application.list_my_settings import ListMySettings
from app.modules.settings.application.reset_my_setting import ResetMySetting
from app.modules.settings.application.update_my_settings import UpdateMySettings
from app.platform.config import DateTimeSettings, MenageristBaseSettings
from app.platform.config._discovery import discover
from app.platform.config._markers import Scope, Tunable
from app.shared_kernel.actor import Actor

if TYPE_CHECKING:
    from fastapi import FastAPI

BASE = "/api/v1/me/settings"

type AsUser = Callable[..., None]


class Home(MenageristBaseSettings, group="home"):
    """A hidden per-person list, changed outside the Preferences page."""

    collections: Annotated[list[str], Tunable(scope=Scope.USER, hidden=True)] = Field(
        default_factory=list, title="Home collections", description="Shown."
    )


class Server(MenageristBaseSettings, group="server_example"):
    """An instance setting, which `/me/settings` must not reach."""

    mode: Annotated[Literal["a", "b"], Tunable()] = Field(
        default="a", title="Mode", description="Instance."
    )


def make_app(repo: InMemorySettingValueRepository) -> FastAPI:
    """The app wired to an in-memory store and the calendar, home and server groups."""
    app: FastAPI = create_app()
    groups: list[type[MenageristBaseSettings]] = [DateTimeSettings, Home, Server]
    catalogue = build_catalogue(discover(groups), {g: g() for g in groups})
    guard = get_access_guard()
    app.dependency_overrides[get_settings_catalogue] = lambda: catalogue
    app.dependency_overrides[get_list_my_settings_use_case] = lambda: ListMySettings(
        repo, guard, catalogue
    )
    app.dependency_overrides[get_get_my_settings_schema_use_case] = lambda: (
        GetMySettingsSchema(catalogue, guard)
    )
    app.dependency_overrides[get_update_my_settings_use_case] = lambda: (
        UpdateMySettings(create_in_memory_settings_uow(repo), guard, catalogue)
    )
    app.dependency_overrides[get_reset_my_setting_use_case] = lambda: ResetMySetting(
        create_in_memory_settings_uow(repo), guard, catalogue
    )
    return app


@pytest.fixture
def repo() -> InMemorySettingValueRepository:
    """One store shared by every person in a test."""
    return InMemorySettingValueRepository()


def client_for(
    as_user: AsUser, repo: InMemorySettingValueRepository, user: UUID | None = None
) -> TestClient:
    """A client signed in as `user` (a new person by default)."""
    app = make_app(repo)
    as_user(app, user or uuid7(), "member")
    return TestClient(app)


def test_list_returns_own_settings_including_hidden(
    as_user: AsUser, repo: InMemorySettingValueRepository
) -> None:
    """Every per-person setting, with labels in its schema and hidden ones marked."""
    response = client_for(as_user, repo).get(BASE)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    by_key = {item["key"]: item for item in response.json()}
    assert set(by_key) == {
        "datetime.time_zone",
        "datetime.date_order",
        "datetime.clock",
        "datetime.first_day",
        "home.collections",
    }
    assert by_key["datetime.first_day"]["value"] == "automatic"
    assert by_key["datetime.first_day"]["source"] == "default"
    assert by_key["datetime.first_day"]["hidden"] is False
    assert by_key["home.collections"]["hidden"] is True


def test_patch_saves_for_the_signed_in_person_only(
    as_user: AsUser, repo: InMemorySettingValueRepository
) -> None:
    """A change shows for its owner and never for another person."""
    alice = client_for(as_user, repo)
    bob = client_for(as_user, repo)

    response = alice.patch(
        BASE,
        json={"values": {"datetime.first_day": "monday", "home.collections": ["x"]}},
    )

    assert response.status_code == 200
    assert sorted((i["key"], i["value"], i["source"]) for i in response.json()) == [
        ("datetime.first_day", "monday", "user"),
        ("home.collections", ["x"], "user"),
    ]
    theirs = {i["key"]: i["value"] for i in bob.get(BASE).json()}
    assert (theirs["datetime.first_day"], theirs["home.collections"]) == (
        "automatic",
        [],
    )


def test_patch_refuses_an_instance_setting_and_a_bad_value(
    as_user: AsUser, repo: InMemorySettingValueRepository
) -> None:
    """Instance keys are unknown here, and an invalid value saves nothing."""
    client = client_for(as_user, repo)

    instance = client.patch(BASE, json={"values": {"server_example.mode": "b"}})
    invalid = client.patch(BASE, json={"values": {"datetime.first_day": "friday"}})

    assert instance.status_code == 404
    assert invalid.status_code == 400
    listed = {i["key"]: i["value"] for i in client.get(BASE).json()}
    assert listed["datetime.first_day"] == "automatic"


def test_reset_returns_the_default(
    as_user: AsUser, repo: InMemorySettingValueRepository
) -> None:
    """Reset removes the person's value; resetting again is harmless."""
    client = client_for(as_user, repo)
    client.patch(BASE, json={"values": {"datetime.first_day": "sunday"}})

    first = client.delete(f"{BASE}/datetime.first_day")
    again = client.delete(f"{BASE}/datetime.first_day")

    assert (first.json()["value"], first.json()["source"]) == ("automatic", "default")
    assert again.status_code == 200
    assert client.delete(f"{BASE}/server_example.mode").status_code == 404


def test_schema_leaves_out_hidden_settings_and_carries_labels(
    as_user: AsUser, repo: InMemorySettingValueRepository
) -> None:
    """The form schema has the visible settings, their labels and an ETag."""
    client = client_for(as_user, repo)

    response = client.get(f"{BASE}/schema")
    cached = client.get(
        f"{BASE}/schema", headers={"If-None-Match": response.headers["etag"]}
    )

    properties = response.json()["properties"]
    assert "home.collections" not in properties
    assert "datetime.first_day" in properties
    labels = properties["datetime.first_day"]["x-menagerist"]["labels"]
    assert labels["automatic"] == "Automatic (from your region)"
    assert cached.status_code == 304


@pytest.mark.parametrize(
    ("method", "path"),
    [("get", BASE), ("get", f"{BASE}/schema"), ("delete", f"{BASE}/calendar.x")],
)
def test_an_api_token_is_refused(
    repo: InMemorySettingValueRepository, method: str, path: str
) -> None:
    """Own-account routes refuse tokens, even ones with every grant."""
    app = make_app(repo)
    token = Actor(id=uuid7(), roles=frozenset({"admin"}), grants=frozenset({"*"}))
    app.dependency_overrides[get_current_actor] = lambda: token

    response = getattr(TestClient(app), method)(path)

    assert response.status_code == 403


def test_an_env_default_is_reported(
    as_user: AsUser,
    repo: InMemorySettingValueRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The deployment's default shows as `env_default` and can still be changed."""
    monkeypatch.setenv("MENAGERIST_DATETIME_FIRST_DAY", "sunday")
    client = client_for(as_user, repo)

    listed = {i["key"]: i for i in client.get(BASE).json()}["datetime.first_day"]
    changed = client.patch(BASE, json={"values": {"datetime.first_day": "monday"}})

    assert (listed["value"], listed["source"], listed["locked"]) == (
        "sunday",
        "env_default",
        False,
    )
    assert changed.status_code == 200
