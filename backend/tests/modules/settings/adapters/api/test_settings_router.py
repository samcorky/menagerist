from collections.abc import Callable
from typing import TYPE_CHECKING
from uuid import uuid7

import pytest
from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.entrypoints.api.shared.access_guard import get_access_guard
from app.modules.settings.adapters.api.dependencies import (
    get_get_settings_schema_use_case,
    get_list_settings_use_case,
    get_reset_setting_use_case,
    get_settings_catalogue,
    get_update_settings_use_case,
)
from app.modules.settings.adapters.persistence.in_memory_setting_value_repository import (  # noqa: E501
    InMemorySettingValueRepository,
)
from app.modules.settings.adapters.persistence.unit_of_work import (
    create_in_memory_settings_uow,
)
from app.modules.settings.adapters.platform.deployment_catalogue import build_catalogue
from app.modules.settings.application.get_settings_schema import GetSettingsSchema
from app.modules.settings.application.list_settings import ListSettings
from app.modules.settings.application.reset_setting import ResetSetting
from app.modules.settings.application.update_settings import UpdateSettings
from app.platform.config import BackupSettings
from app.platform.config._discovery import discover

if TYPE_CHECKING:
    from fastapi import FastAPI

type AsUser = Callable[..., None]


def make_client(as_user: AsUser, role: str = "admin") -> TestClient:
    """The app wired to an in-memory store and the backup settings catalogue."""
    app: FastAPI = create_app()
    catalogue = build_catalogue(
        discover([BackupSettings]), {BackupSettings: BackupSettings()}
    )
    repo = InMemorySettingValueRepository()
    guard = get_access_guard()
    app.dependency_overrides[get_settings_catalogue] = lambda: catalogue
    app.dependency_overrides[get_list_settings_use_case] = lambda: ListSettings(
        repo, guard, catalogue
    )
    app.dependency_overrides[get_get_settings_schema_use_case] = lambda: (
        GetSettingsSchema(catalogue, guard)
    )
    app.dependency_overrides[get_update_settings_use_case] = lambda: UpdateSettings(
        create_in_memory_settings_uow(repo), guard, catalogue
    )
    app.dependency_overrides[get_reset_setting_use_case] = lambda: ResetSetting(
        create_in_memory_settings_uow(repo), guard, catalogue
    )
    as_user(app, uuid7(), role)
    return TestClient(app)


def test_list_returns_every_tunable_with_its_source(as_user: AsUser) -> None:
    """Defaults come back with their metadata and an unlocked default source."""
    client = make_client(as_user)
    response = client.get("/api/v1/settings/instance")
    assert response.status_code == 200
    by_key = {item["key"]: item for item in response.json()}
    assert set(by_key) == {
        "backup.keep_last",
        "backup.schedule",
        "backup.user_export_ttl_hours",
    }
    keep = by_key["backup.keep_last"]
    assert keep["value"] == 7
    assert keep["source"] == "default"
    assert keep["locked"] is False
    assert keep["env_name"] == "MENAGERIST_BACKUP_KEEP_LAST"
    assert keep["title"] == "Backups to keep"
    assert response.headers["cache-control"] == "private, no-store"


def test_patch_saves_and_the_next_read_shows_it(as_user: AsUser) -> None:
    """A change is returned resolved and visible on the following list."""
    client = make_client(as_user)
    response = client.patch(
        "/api/v1/settings/instance",
        json={"values": {"backup.keep_last": 12, "backup.schedule": ""}},
    )
    assert response.status_code == 200
    assert {(i["key"], i["value"], i["source"]) for i in response.json()} == {
        ("backup.keep_last", 12, "instance"),
        ("backup.schedule", "", "instance"),
    }
    listed = {i["key"]: i for i in client.get("/api/v1/settings/instance").json()}
    assert listed["backup.keep_last"]["value"] == 12
    assert listed["backup.user_export_ttl_hours"]["source"] == "default"


def test_patch_with_a_bad_value_saves_nothing_and_explains(as_user: AsUser) -> None:
    """One invalid value fails the whole patch with a problem body."""
    client = make_client(as_user)
    response = client.patch(
        "/api/v1/settings/instance",
        json={"values": {"backup.schedule": "", "backup.keep_last": 0}},
    )
    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["title"] == "InvalidSettingValueError"
    assert "backup.keep_last" in response.json()["detail"]
    after = {i["key"]: i for i in client.get("/api/v1/settings/instance").json()}
    assert after["backup.schedule"]["source"] == "default"


def test_patch_rejects_unknown_keys_and_malformed_bodies(as_user: AsUser) -> None:
    """Unknown keys are 404; a body that is not an object is a request error."""
    client = make_client(as_user)
    unknown = client.patch(
        "/api/v1/settings/instance", json={"values": {"nope.nothing": 1}}
    )
    assert unknown.status_code == 404
    assert client.patch("/api/v1/settings/instance", json=[1]).status_code == 422
    assert client.patch("/api/v1/settings/instance", json={}).status_code == 422
    extra = client.patch(
        "/api/v1/settings/instance", json={"values": {}, "backup.keep_last": 3}
    )
    assert extra.status_code == 422


def test_an_empty_patch_is_harmless(as_user: AsUser) -> None:
    """Naming no settings changes nothing."""
    response = make_client(as_user).patch(
        "/api/v1/settings/instance", json={"values": {}}
    )
    assert (response.status_code, response.json()) == (200, [])


def test_reset_returns_the_default_and_is_idempotent(as_user: AsUser) -> None:
    """Deleting the saved value restores the default, twice over."""
    client = make_client(as_user)
    client.patch("/api/v1/settings/instance", json={"values": {"backup.keep_last": 12}})
    first = client.delete("/api/v1/settings/instance/backup.keep_last")
    again = client.delete("/api/v1/settings/instance/backup.keep_last")
    assert first.status_code == again.status_code == 200
    assert (first.json()["value"], first.json()["source"]) == (7, "default")
    assert again.json()["value"] == 7
    assert client.delete("/api/v1/settings/instance/nope.nothing").status_code == 404


def test_a_deployment_pin_locks_the_setting(
    as_user: AsUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the variable set, the list shows it locked and changes are a 409."""
    monkeypatch.setenv("MENAGERIST_BACKUP_KEEP_LAST", "30")
    client = make_client(as_user)
    keep = {i["key"]: i for i in client.get("/api/v1/settings/instance").json()}[
        "backup.keep_last"
    ]
    assert (keep["value"], keep["source"], keep["locked"]) == (30, "env", True)
    patch = client.patch(
        "/api/v1/settings/instance", json={"values": {"backup.keep_last": 5}}
    )
    assert patch.status_code == 409
    assert "MENAGERIST_BACKUP_KEEP_LAST" in patch.json()["detail"]
    reset = client.delete("/api/v1/settings/instance/backup.keep_last")
    assert reset.status_code == 409


def test_the_schema_has_a_property_per_setting_and_an_etag(as_user: AsUser) -> None:
    """Hints for the form are present and unchanged requests revalidate to 304."""
    client = make_client(as_user)
    response = client.get("/api/v1/settings/schema")
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "object"
    schedule = body["properties"]["backup.schedule"]
    assert schedule["x-menagerist"] == {"kind": "cron"}
    assert body["properties"]["backup.user_export_ttl_hours"]["x-menagerist"] == {
        "unit": "hours"
    }
    etag = response.headers["etag"]
    cached = client.get("/api/v1/settings/schema", headers={"If-None-Match": etag})
    assert cached.status_code == 304
    stale = client.get("/api/v1/settings/schema", headers={"If-None-Match": '"old"'})
    assert stale.status_code == 200
    anything = client.get("/api/v1/settings/schema", headers={"If-None-Match": "*"})
    assert anything.status_code == 304


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "/api/v1/settings/schema", None),
        ("GET", "/api/v1/settings/instance", None),
        ("PATCH", "/api/v1/settings/instance", {"values": {"backup.keep_last": 3}}),
        ("DELETE", "/api/v1/settings/instance/backup.keep_last", None),
    ],
)
def test_members_are_refused_everywhere(
    as_user: AsUser, method: str, path: str, body: dict[str, dict[str, int]] | None
) -> None:
    """Settings are administrator-only."""
    client = make_client(as_user, role="member")
    response = client.request(method, path, json=body)
    assert response.status_code == 403
