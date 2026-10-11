"""The start-up check that warns when no administrator exists."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from starlette.testclient import TestClient
from structlog.testing import capture_logs

from app.entrypoints.api import create_app, startup
from app.modules.identity.adapters.persistence.in_memory_session_repository import (
    InMemorySessionRepository,
)
from app.modules.identity.adapters.persistence.in_memory_sign_in_attempt_repository import (  # noqa: E501
    InMemorySignInAttemptRepository,
)
from app.modules.identity.adapters.persistence.in_memory_user_repository import (
    InMemoryUserRepository,
)
from app.modules.identity.domain.user import Role, User
from app.modules.identity.ports.unit_of_work import IdentityRepos

if TYPE_CHECKING:
    import pytest


class _Session:
    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None


def _wire(monkeypatch: pytest.MonkeyPatch, users: InMemoryUserRepository) -> None:
    repos = IdentityRepos(
        users=users,
        sessions=InMemorySessionRepository(),
        attempts=InMemorySignInAttemptRepository(),
    )
    monkeypatch.setattr(startup, "get_session_factory", lambda: _Session)
    monkeypatch.setattr(startup, "build_identity_repos", lambda _session: repos)


def _user(role: Role, *, disabled: bool = False) -> User:
    user = User.create(
        username=f"{role.value}-{disabled}",
        display_name="x",
        password_hash="h",
        now=datetime.now(UTC),
        role=role,
    )
    user.disabled = disabled
    return user


async def test_warns_once_when_there_is_no_administrator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty database logs the one warning, with the way out."""
    _wire(monkeypatch, InMemoryUserRepository())

    with capture_logs() as logs:
        await startup.warn_if_no_administrator()

    warnings = [entry for entry in logs if entry["log_level"] == "warning"]
    assert [entry["event"] for entry in warnings] == [startup.NO_ADMINISTRATOR_WARNING]
    assert "/setup" in startup.NO_ADMINISTRATOR_WARNING
    assert "menagerist identity create-admin" in startup.NO_ADMINISTRATOR_WARNING


async def test_members_and_disabled_administrators_do_not_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without an enabled administrator the warning still appears."""
    users = InMemoryUserRepository()
    await users.add(_user(Role.MEMBER))
    await users.add(_user(Role.ADMIN, disabled=True))
    _wire(monkeypatch, users)

    with capture_logs() as logs:
        await startup.warn_if_no_administrator()

    assert [entry["log_level"] for entry in logs] == ["warning"]


async def test_stays_quiet_when_an_administrator_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No warning once someone can administer the server."""
    users = InMemoryUserRepository()
    await users.add(_user(Role.ADMIN))
    _wire(monkeypatch, users)

    with capture_logs() as logs:
        await startup.warn_if_no_administrator()

    assert logs == []


async def test_an_unreachable_database_is_not_a_startup_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The check is skipped, with no warning, if the query fails."""

    def broken() -> object:
        raise ConnectionError("no database")

    monkeypatch.setattr(startup, "get_session_factory", broken)

    with capture_logs() as logs:
        await startup.warn_if_no_administrator()

    assert [entry["log_level"] for entry in logs] == ["debug"]


def test_the_application_lifespan_runs_the_check_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Starting the app calls the check a single time, before serving."""
    calls: list[str] = []

    async def fake() -> None:
        calls.append("checked")

    monkeypatch.setattr(startup, "warn_if_no_administrator", fake)

    with TestClient(create_app()) as client:
        assert calls == ["checked"]
        client.get("/api/health")

    assert calls == ["checked"]
