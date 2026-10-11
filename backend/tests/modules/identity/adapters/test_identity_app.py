"""The `identity` CLI: same use cases as the API, run as the system actor."""

import getpass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from app.modules.identity.adapters.cli import identity_app
from app.modules.identity.adapters.cli.identity_app import (
    PASSWORD_ENV_VAR,
    create_admin,
    list_accounts,
    reset_password,
)
from app.modules.identity.adapters.security.in_memory_password_hasher import (
    InMemoryPasswordHasher,
)
from app.modules.identity.domain.session import Session
from app.modules.identity.domain.user import Role
from app.modules.identity.ports.existing_data_claim import ClaimReport
from app.modules.identity.ports.unit_of_work import IdentityRepos

if TYPE_CHECKING:
    import uuid

    from tests.modules.identity.conftest import MakeUser, World

PASSWORD = "a very secret passphrase"


class _Session:
    """Stands in for an `AsyncSession`; the in-memory unit of work ignores it."""

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None


class _SpyClaim:
    def __init__(self) -> None:
        self.owners: list[uuid.UUID] = []

    async def claim(self, owner_id: uuid.UUID) -> ClaimReport:
        self.owners.append(owner_id)
        return ClaimReport(counts={"items": 3, "examples": 1})


@pytest.fixture
def claim(monkeypatch: pytest.MonkeyPatch) -> _SpyClaim:
    """Record who the CLI claims existing content for."""
    spy = _SpyClaim()
    monkeypatch.setattr(identity_app, "_claim_builder", lambda _session: spy)
    return spy


@pytest.fixture(autouse=True)
def _wired(monkeypatch: pytest.MonkeyPatch, world: World) -> None:
    """Run the commands over the in-memory world and its fast hasher."""
    monkeypatch.delenv(PASSWORD_ENV_VAR, raising=False)
    repos = IdentityRepos(users=world.users, sessions=world.sessions)
    monkeypatch.setattr("app.platform.database.get_session_factory", lambda: _Session)
    monkeypatch.setattr(
        "app.modules.identity.adapters.persistence.unit_of_work"
        + ".create_identity_uow_on_session",
        lambda _session: world.uow,
    )
    monkeypatch.setattr(
        "app.modules.identity.adapters.persistence.unit_of_work.build_identity_repos",
        lambda _session: repos,
    )
    monkeypatch.setattr(
        "app.modules.identity.adapters.api.dependencies.get_password_hasher",
        InMemoryPasswordHasher,
    )


def _prompts(monkeypatch: pytest.MonkeyPatch, *answers: str) -> list[str]:
    asked: list[str] = []
    remaining = list(answers)

    def fake(prompt: str = "") -> str:
        asked.append(prompt)
        return remaining.pop(0)

    monkeypatch.setattr(getpass, "getpass", fake)
    return asked


def test_first_admin_goes_through_setup_and_claims_existing_data(
    world: World,
    claim: _SpyClaim,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """With no accounts it is first-run setup: an admin, and the claim runs."""
    asked = _prompts(monkeypatch, PASSWORD, PASSWORD)

    create_admin(username="Sam")

    admin = next(iter(world.users._users.values()))
    assert (admin.username, admin.role, admin.password_expired) == (
        "sam",
        Role.ADMIN,
        False,
    )
    assert claim.owners == [admin.id]
    assert asked == ["Password: ", "Confirm password: "]
    out = capsys.readouterr()
    assert "Created administrator 'sam'" in out.out
    assert "3 items, 1 examples" in out.out
    assert world.uow.committed


def test_password_is_never_echoed_or_stored_in_clear(
    world: World,
    claim: _SpyClaim,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Neither the password nor its hash appears in output or logs."""
    _prompts(monkeypatch, PASSWORD, PASSWORD)

    create_admin(username="sam")

    stored = next(iter(world.users._users.values())).password_hash
    out = capsys.readouterr()
    everything = out.out + out.err + caplog.text
    assert PASSWORD not in everything
    assert stored not in everything
    assert stored != PASSWORD


def test_password_can_come_from_the_environment(
    world: World,
    claim: _SpyClaim,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`MENAGERIST_INITIAL_PASSWORD` skips the prompt and is not echoed."""
    monkeypatch.setenv(PASSWORD_ENV_VAR, PASSWORD)
    monkeypatch.setattr(getpass, "getpass", lambda _p="": pytest.fail("prompted"))

    create_admin(username="sam", display_name="Sam C")

    admin = next(iter(world.users._users.values()))
    assert admin.display_name == "Sam C"
    out = capsys.readouterr()
    assert PASSWORD not in out.out + out.err


def test_mismatched_confirmation_creates_nothing(
    world: World,
    claim: _SpyClaim,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Two different entries are refused before anything is written."""
    _prompts(monkeypatch, PASSWORD, "something else entirely")

    with pytest.raises(SystemExit) as stop:
        create_admin(username="sam")

    assert stop.value.code == 1
    assert "do not match" in capsys.readouterr().err
    assert world.users._users == {}
    assert claim.owners == []


def test_a_weak_password_is_refused_with_a_message(
    world: World,
    claim: _SpyClaim,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Application errors become a plain message and exit code 1."""
    monkeypatch.setenv(PASSWORD_ENV_VAR, "short")

    with pytest.raises(SystemExit) as stop:
        create_admin(username="sam")

    assert stop.value.code == 1
    assert "password" in capsys.readouterr().err.lower()
    assert world.users._users == {}


def test_a_further_admin_has_an_expired_password_and_claims_nothing(
    world: World,
    make_user: MakeUser,
    claim: _SpyClaim,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """On a server with accounts it adds an admin who must change the password."""
    existing = make_user("alice")
    world.users._users[existing.id] = existing
    monkeypatch.setenv(PASSWORD_ENV_VAR, PASSWORD)

    create_admin(username="bob")

    bob = next(u for u in world.users._users.values() if u.username == "bob")
    assert (bob.role, bob.password_expired) == (Role.ADMIN, True)
    assert claim.owners == []
    assert "must change the password" in capsys.readouterr().out


def test_a_taken_username_is_refused(
    world: World,
    make_user: MakeUser,
    claim: _SpyClaim,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A clash is reported, not raised as a traceback."""
    existing = make_user("alice")
    world.users._users[existing.id] = existing
    monkeypatch.setenv(PASSWORD_ENV_VAR, PASSWORD)

    with pytest.raises(SystemExit) as stop:
        create_admin(username="Alice")

    assert stop.value.code == 1
    assert capsys.readouterr().err.strip()


def test_reset_password_sets_an_expired_password_and_ends_sessions(
    world: World,
    make_user: MakeUser,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The system actor passes the admin gate; sessions go; a change is forced."""
    alice = make_user("alice")
    old_hash = alice.password_hash
    world.users._users[alice.id] = alice
    session = Session.create(
        user_id=alice.id,
        token_hash="hash",
        now=datetime.now(UTC),
        ttl=timedelta(hours=1),
    )
    world.sessions._sessions[session.id] = session
    _prompts(monkeypatch, PASSWORD, PASSWORD)

    reset_password(username="ALICE")

    assert alice.password_hash != old_hash
    assert alice.password_expired is True
    assert world.sessions._sessions == {}
    out = capsys.readouterr()
    assert "Password reset for 'alice'" in out.out
    assert PASSWORD not in out.out + out.err


def test_reset_password_for_an_unknown_account_fails(
    world: World, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A missing account is reported and nothing is written."""
    monkeypatch.setenv(PASSWORD_ENV_VAR, PASSWORD)

    with pytest.raises(SystemExit) as stop:
        reset_password(username="nobody")

    assert stop.value.code == 1
    assert "does not exist" in capsys.readouterr().err
    assert not world.uow.committed


def test_list_prints_accounts_but_never_hashes(
    world: World, make_user: MakeUser, capsys: pytest.CaptureFixture[str]
) -> None:
    """Username, display name, role and disabled flag; no secrets."""
    alice = make_user("alice", role=Role.ADMIN)
    bob = make_user("bob")
    bob.disabled = True
    world.users._users[alice.id] = alice
    world.users._users[bob.id] = bob

    list_accounts()

    out = capsys.readouterr().out
    lines = {line.split("\t")[0]: line.split("\t") for line in out.splitlines()}
    assert lines["alice"] == ["alice", "Alice", "admin", "active"]
    assert lines["bob"] == ["bob", "Bob", "member", "disabled"]
    assert alice.password_hash not in out
    assert bob.password_hash not in out
