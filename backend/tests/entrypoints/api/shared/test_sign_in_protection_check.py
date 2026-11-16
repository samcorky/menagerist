"""Sign-in protection diagnostics warn per condition and never fail readiness."""

import socket
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import time_machine
from structlog.testing import capture_logs

from app.entrypoints.api.shared.bridges.sign_in_protection_check import (
    ACCOUNTS_KEY,
    ADDRESSES_KEY,
    ALL_KEYS,
    NAMES_KEY,
    SignInProtectionCheck,
)
from app.modules.identity.application.assess_sign_in_protection import (
    AssessSignInProtection,
    SignInProtection,
)
from app.modules.system.adapters.platform.readiness_check_registry import (
    ReadinessCheckRegistry,
)
from app.modules.system.domain.readiness import CheckObservation, CheckStatus

if TYPE_CHECKING:
    import pytest

NOW = datetime(2026, 11, 16, 12, tzinfo=UTC)


def _text(rows: dict[str, CheckObservation], key: str) -> str:
    """Return a row's output, which a warning row must have."""
    output = rows[key].output
    assert output is not None
    return output


def _check(
    monkeypatch: pytest.MonkeyPatch, protection: SignInProtection
) -> SignInProtectionCheck:
    monkeypatch.setattr(
        AssessSignInProtection, "handle", AsyncMock(return_value=protection)
    )
    return SignInProtectionCheck(MagicMock())


@time_machine.travel(NOW, tick=False)
async def test_nothing_locked_passes_on_every_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Three compact rows, all passing, with no output."""
    rows = await _check(monkeypatch, SignInProtection()).run()
    assert tuple(rows) == ALL_KEYS
    for row in rows.values():
        assert row.status is CheckStatus.PASS
        assert row.observed_value == 0
        assert row.observed_unit == "locked"
        assert row.output is None
        assert row.time == NOW


async def test_each_condition_warns_on_its_own_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Counts are shown, and the wording agrees with the number."""
    protection = SignInProtection(
        locked_accounts=2, unknown_names=1, locked_addresses=3
    )
    rows = await _check(monkeypatch, protection).run()

    assert rows[ACCOUNTS_KEY].status is CheckStatus.WARN
    assert rows[ACCOUNTS_KEY].observed_value == 2
    assert _text(rows, ACCOUNTS_KEY).startswith("2 accounts are locked")
    assert _text(rows, NAMES_KEY).startswith("1 locked sign-in name matches no account")
    assert rows[ADDRESSES_KEY].observed_value == 3
    assert _text(rows, ADDRESSES_KEY).startswith("3 client addresses are locked")
    assert "MENAGERIST_API_TRUSTED_PROXIES" in _text(rows, ADDRESSES_KEY)


async def test_a_single_lock_uses_the_singular(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One account or address reads naturally."""
    rows = await _check(
        monkeypatch, SignInProtection(locked_accounts=1, locked_addresses=1)
    ).run()
    assert _text(rows, ACCOUNTS_KEY).startswith("1 account is locked")
    assert _text(rows, ADDRESSES_KEY).startswith("1 client address is locked")
    assert "requests from it are refused" in _text(rows, ADDRESSES_KEY)
    assert rows[NAMES_KEY].status is CheckStatus.PASS


async def test_check_failure_warns_on_every_row_without_leaking_details() -> None:
    """Diagnostics failures cannot fail readiness or disclose connection details."""
    check = SignInProtectionCheck(
        MagicMock(side_effect=OSError("private connection details"))
    )
    rows = await check.run()
    assert tuple(rows) == ALL_KEYS
    for row in rows.values():
        assert row.status is CheckStatus.WARN
        assert row.observed_value == "unknown"
        assert row.output == "Sign-in protection could not be checked."


async def test_database_outage_is_a_one_line_warning() -> None:
    """An unreachable database logs without a traceback."""
    check = SignInProtectionCheck(
        MagicMock(side_effect=socket.gaierror(-2, "unknown host"))
    )
    with capture_logs() as logs:
        await check.run()
    (entry,) = [e for e in logs if e["event"] == "sign-in protection check failed"]
    assert entry["log_level"] == "warning"
    assert "exc_info" not in entry


async def test_warnings_keep_readiness_healthy(monkeypatch: pytest.MonkeyPatch) -> None:
    """Locks warn in the report; they never fail readiness."""
    check = _check(monkeypatch, SignInProtection(locked_addresses=1))
    report = await ReadinessCheckRegistry([check]).check()
    assert report.status is CheckStatus.WARN
