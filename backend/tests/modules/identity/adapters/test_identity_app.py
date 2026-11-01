"""The `identity` CLI: same use cases as the API, run as the system actor."""

import asyncio
import getpass
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from pydantic import SecretStr

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.modules.identity.adapters.cli import identity_app
from app.modules.identity.adapters.cli.identity_app import (
    create_admin,
    list_accounts,
    reset_password,
    set_display_name,
    unlock,
)
from app.modules.identity.adapters.security.in_memory_password_hasher import (
    InMemoryPasswordHasher,
)
from app.modules.identity.application.sign_in_throttle import ip_key, username_key
from app.modules.identity.domain.session import Session
from app.modules.identity.domain.user import Role, User
from app.modules.identity.ports.existing_data_claim import ClaimReport
from app.modules.identity.ports.unit_of_work import IdentityRepos
from app.platform.cli_output import OutputFormat, emit_result, set_format
from app.platform.config import IdentityCliSettings, IdentitySettings
from app.shared_kernel.access_guard import DenyAllAccessGuard

if TYPE_CHECKING:
    import uuid
    from collections.abc import Iterator

    from tests.modules.identity.conftest import MakeUser, World

PASSWORD = "a very secret passphrase"
PASSWORD_ENV_VAR = "MENAGERIST_IDENTITY_INITIAL_PASSWORD"


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
def _automatic_format() -> Iterator[None]:
    """Leave the output format as the test found it."""
    set_format(OutputFormat.AUTO)
    yield
    set_format(OutputFormat.AUTO)


@pytest.fixture(autouse=True)
def _wired(monkeypatch: pytest.MonkeyPatch, world: World) -> None:
    """Run the commands over the in-memory world and its fast hasher."""
    monkeypatch.delenv(PASSWORD_ENV_VAR, raising=False)
    monkeypatch.setattr(identity_app, "_guard", get_access_guard())
    monkeypatch.setattr(
        "app.platform.config.identity_cli.SECRETS_DIR", Path("/nonexistent-secrets")
    )
    repos = IdentityRepos(
        users=world.users,
        sessions=world.sessions,
        attempts=world.attempts,
        tokens=world.tokens,
    )
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
) -> None:
    """With no accounts it is first-run setup: an admin, and the claim runs."""
    asked = _prompts(monkeypatch, PASSWORD, PASSWORD)

    result = create_admin(username="Sam")

    admin = next(iter(world.users._users.values()))
    assert (admin.username, admin.role, admin.password_expired) == (
        "sam",
        Role.ADMIN,
        False,
    )
    assert claim.owners == [admin.id]
    assert asked == ["Password: ", "Confirm password: "]
    assert "Created administrator 'sam'" in str(result["message"])
    assert "3 items, 1 examples" in str(result["message"])
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

    result = create_admin(username="sam")

    stored = next(iter(world.users._users.values())).password_hash
    out = capsys.readouterr()
    everything = out.out + out.err + caplog.text + str(result)
    assert PASSWORD not in everything
    assert stored not in everything
    assert stored != PASSWORD


def test_password_can_come_from_the_environment(
    world: World,
    claim: _SpyClaim,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`MENAGERIST_IDENTITY_INITIAL_PASSWORD` skips the prompt and is not echoed."""
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
) -> None:
    """On a server with accounts it adds an admin who must change the password."""
    existing = make_user("alice")
    world.users._users[existing.id] = existing
    monkeypatch.setenv(PASSWORD_ENV_VAR, PASSWORD)

    result = create_admin(username="bob")

    bob = next(u for u in world.users._users.values() if u.username == "bob")
    assert (bob.role, bob.password_expired) == (Role.ADMIN, True)
    assert claim.owners == []
    assert "must change the password" in str(result["message"])


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

    result = reset_password(username="ALICE")

    assert alice.password_hash != old_hash
    assert alice.password_expired is True
    assert world.sessions._sessions == {}
    out = capsys.readouterr()
    assert "Password reset for 'alice'" in str(result["message"])
    assert PASSWORD not in out.out + out.err + str(result)


def test_reset_password_prompts_even_when_a_bootstrap_password_is_configured(
    world: World, make_user: MakeUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A password left in the environment is never applied silently."""
    alice = make_user("alice")
    world.users._users[alice.id] = alice
    monkeypatch.setenv(PASSWORD_ENV_VAR, "bootstrap-password-1")
    asked = _prompts(monkeypatch, PASSWORD, PASSWORD)

    reset_password(username="alice")

    assert asked == ["Password: ", "Confirm password: "]


def test_reset_password_reads_settings_only_with_the_explicit_flag(
    world: World,
    make_user: MakeUser,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--from-settings` uses the configured password and does not prompt."""
    alice = make_user("alice")
    old_hash = alice.password_hash
    world.users._users[alice.id] = alice
    monkeypatch.setenv(PASSWORD_ENV_VAR, PASSWORD)
    monkeypatch.setattr(getpass, "getpass", lambda _p="": pytest.fail("prompted"))

    reset_password(username="alice", from_settings=True)

    assert alice.password_hash != old_hash
    assert alice.password_expired is True
    out = capsys.readouterr()
    assert PASSWORD not in out.out + out.err


def test_reset_password_for_an_unknown_account_fails(
    world: World, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A missing account is reported and nothing is written."""
    _prompts(monkeypatch, PASSWORD, PASSWORD)

    with pytest.raises(SystemExit) as stop:
        reset_password(username="nobody")

    assert stop.value.code == 1
    assert "does not exist" in capsys.readouterr().err
    assert not world.uow.committed


def test_password_can_come_from_a_secret_file(
    world: World,
    claim: _SpyClaim,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A `menagerist_identity_initial_password` secrets-directory file is read."""
    (tmp_path / "menagerist_identity_initial_password").write_text(PASSWORD)
    monkeypatch.setattr("app.platform.config.identity_cli.SECRETS_DIR", tmp_path)
    monkeypatch.setattr(getpass, "getpass", lambda _p="": pytest.fail("prompted"))

    create_admin(username="sam")

    assert next(iter(world.users._users.values())).username == "sam"
    out = capsys.readouterr()
    assert PASSWORD not in out.out + out.err


def test_the_prompt_is_the_fallback_without_env_or_secret_file(
    world: World, claim: _SpyClaim, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no env var or secret file the hidden, confirmed prompt is used."""
    asked = _prompts(monkeypatch, PASSWORD, PASSWORD)

    create_admin(username="sam")

    assert asked == ["Password: ", "Confirm password: "]


def test_the_cli_settings_never_show_the_password() -> None:
    """The secret is masked in the settings object's repr."""
    settings = IdentityCliSettings(initial_password=SecretStr(PASSWORD))

    assert PASSWORD not in repr(settings)
    assert PASSWORD not in str(settings)


def test_server_settings_do_not_carry_the_initial_password() -> None:
    """The password setting exists only for the CLI."""
    assert "initial_password" not in IdentitySettings.model_fields


def _seed(world: World, make_user: MakeUser) -> tuple[User, User]:
    alice = make_user("alice", role=Role.ADMIN)
    alice.record_sign_in(datetime(2026, 10, 11, 8, 30, tzinfo=UTC))
    bob = make_user("bob")
    bob.disabled = True
    world.users._users[alice.id] = alice
    world.users._users[bob.id] = bob
    return alice, bob


def test_list_returns_accounts_but_never_hashes(
    world: World, make_user: MakeUser
) -> None:
    """Username, name, role, status and last sign-in; no secrets."""
    alice, bob = _seed(world, make_user)

    report = list_accounts()

    assert (report.title, report.empty) == ("Accounts", "No accounts yet.")
    rows = {row["username"]: row for row in report.value}  # type: ignore[attr-defined]
    assert rows["alice"]["role"] == "admin"
    assert rows["alice"]["status"] == "active"
    assert rows["alice"]["last_login_at"] == datetime(2026, 10, 11, 8, 30, tzinfo=UTC)
    assert rows["bob"]["role"] == "member"
    assert rows["bob"]["status"] == "disabled"
    assert rows["bob"]["last_login_at"] is None
    assert rows["bob"]["locked_until"] is None
    shown = str(report.value)
    assert alice.password_hash not in shown
    assert bob.password_hash not in shown
    assert "hash" not in shown


def test_list_marks_a_locked_username(world: World, make_user: MakeUser) -> None:
    """A username that is locked out carries the time its lock ends."""
    _seed(world, make_user)
    now = datetime.now(UTC)
    for _ in range(5):
        asyncio.run(
            world.attempts.record_failure(
                username_key("bob"), limit=5, window=timedelta(minutes=15), now=now
            )
        )

    rows = {row["username"]: row for row in list_accounts().value}  # type: ignore[attr-defined]

    assert rows["bob"]["locked_until"] is not None
    assert rows["alice"]["locked_until"] is None


def test_list_renders_as_plain_columns_and_as_json(
    world: World, make_user: MakeUser, capsys: pytest.CaptureFixture[str]
) -> None:
    """Piped output is aligned text; `--json` is a parseable array."""
    alice, _bob = _seed(world, make_user)
    report = list_accounts()

    emit_result(report)
    plain = capsys.readouterr().out
    assert plain.splitlines()[0].startswith("USERNAME")
    assert "alice" in plain
    assert "-" in next(line for line in plain.splitlines() if "bob" in line)

    set_format(OutputFormat.JSON)
    emit_result(report)
    out = capsys.readouterr().out
    rows = {row["username"]: row for row in json.loads(out)}
    assert rows["alice"]["last_login_at"] == "2026-10-11T08:30:00+00:00"
    assert alice.password_hash not in out


def test_set_display_name_renames_the_account(
    world: World, make_user: MakeUser
) -> None:
    """The system actor renames an account by username."""
    alice = make_user("alice")
    world.users._users[alice.id] = alice

    result = set_display_name(username="ALICE", display_name="  Alice Example ")

    assert alice.display_name == "Alice Example"
    assert "Alice Example" in str(result["message"])


def test_set_display_name_reports_unknown_accounts_and_bad_names(
    world: World, make_user: MakeUser, capsys: pytest.CaptureFixture[str]
) -> None:
    """Refusals become a message and exit code 1."""
    alice = make_user("alice")
    world.users._users[alice.id] = alice
    with pytest.raises(SystemExit) as stop:
        set_display_name(username="nobody", display_name="X")
    assert stop.value.code == 1
    with pytest.raises(SystemExit):
        set_display_name(username="alice", display_name="   ")
    assert alice.display_name == "Alice"
    assert capsys.readouterr().err.strip()


def test_unlock_clears_the_username_lock_only(
    world: World, make_user: MakeUser
) -> None:
    """Unlocking lifts the username counter and leaves the address one alone."""
    alice = make_user("alice")
    alice.disable()
    world.users._users[alice.id] = alice
    now = datetime.now(UTC)
    ip = ip_key("203.0.113.9")
    for key in (username_key("alice"), ip):
        asyncio.run(
            world.attempts.record_failure(
                key, limit=1, window=timedelta(minutes=15), now=now
            )
        )

    result = unlock(username="Alice")

    assert username_key("alice") not in world.attempts.windows
    assert ip in world.attempts.windows
    assert alice.disabled is True
    assert "cleared for 'alice'" in str(result["message"])


def test_unlock_for_an_unknown_account_fails(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    """A missing account is reported with exit code 1."""
    with pytest.raises(SystemExit) as stop:
        unlock(username="nobody")

    assert stop.value.code == 1
    assert "does not exist" in capsys.readouterr().err


def test_commands_fail_closed_when_authorisation_is_not_wired(
    world: World, make_user: MakeUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without the entrypoint's wiring the CLI refuses, as the default denies."""
    alice = make_user("alice")
    world.users._users[alice.id] = alice
    monkeypatch.setattr(identity_app, "_guard", DenyAllAccessGuard())

    with pytest.raises(SystemExit):
        unlock(username="alice")
