import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.modules.identity.domain.api_token import MAX_TOKEN_NAME_LENGTH, ApiToken
from app.modules.identity.domain.errors import InvalidApiTokenRequestError

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)
LATER = NOW + timedelta(days=90)


def _create(**overrides: object) -> ApiToken:
    args: dict[str, object] = {
        "token_id": uuid.uuid7(),
        "user_id": uuid.uuid7(),
        "name": "  Backup script  ",
        "secret_hash": "ab" * 32,
        "grants": ["graph:item:read", "graph:item:write"],
        "now": NOW,
        "expires_at": LATER,
    }
    args.update(overrides)
    return ApiToken.create(**args)  # type: ignore[arg-type]


def test_create_strips_name_and_stores_fields() -> None:
    """The name is stripped and every field is stored."""
    token_id = uuid.uuid7()
    user_id = uuid.uuid7()
    token = _create(token_id=token_id, user_id=user_id)
    assert token.id == token_id
    assert token.user_id == user_id
    assert token.name == "Backup script"
    assert token.secret_hash == "ab" * 32
    assert token.grants == frozenset({"graph:item:read", "graph:item:write"})
    assert token.created_at == NOW
    assert token.expires_at == LATER
    assert token.last_used_at is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"name": ""},
        {"name": "   "},
        {"name": "x" * (MAX_TOKEN_NAME_LENGTH + 1)},
        {"grants": []},
        {"expires_at": NOW - timedelta(seconds=1)},
        {"expires_at": NOW},
    ],
)
def test_create_rejects_invalid_requests(overrides: dict[str, object]) -> None:
    """Bad names, missing grants and non-future expiry are refused."""
    with pytest.raises(InvalidApiTokenRequestError):
        _create(**overrides)


def test_create_accepts_maximum_name_length() -> None:
    """A name of exactly the maximum length is fine."""
    assert len(_create(name="x" * MAX_TOKEN_NAME_LENGTH).name) == MAX_TOKEN_NAME_LENGTH


def test_is_expired_exactly_at_expiry() -> None:
    """A token is expired at its expiry instant, not before."""
    token = _create()
    assert not token.is_expired(LATER - timedelta(seconds=1))
    assert token.is_expired(LATER)
    assert token.is_expired(LATER + timedelta(seconds=1))


def test_used_records_time() -> None:
    """`used` sets `last_used_at`."""
    token = _create()
    token.used(NOW + timedelta(minutes=5))
    assert token.last_used_at == NOW + timedelta(minutes=5)
