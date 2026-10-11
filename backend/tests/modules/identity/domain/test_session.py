import uuid
from datetime import UTC, datetime, timedelta

from app.modules.identity.domain.session import Session

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)


def test_create_sets_expiry_from_ttl() -> None:
    """A session expires `ttl` after creation."""
    user_id = uuid.uuid7()
    session = Session.create(
        user_id=user_id, token_hash="ab" * 32, now=NOW, ttl=timedelta(hours=1)
    )
    assert session.user_id == user_id
    assert session.created_at == session.last_seen_at == NOW
    assert session.expires_at == NOW + timedelta(hours=1)


def test_is_expired_at_and_after_expiry() -> None:
    """Expiry is inclusive of the expiry instant."""
    session = Session.create(
        user_id=uuid.uuid7(), token_hash="h", now=NOW, ttl=timedelta(hours=1)
    )
    assert session.is_expired(NOW) is False
    assert session.is_expired(NOW + timedelta(hours=1)) is True


def test_seen_records_activity() -> None:
    """`seen` moves last_seen_at to the given instant."""
    session = Session.create(
        user_id=uuid.uuid7(), token_hash="h", now=NOW, ttl=timedelta(hours=1)
    )
    later = NOW + timedelta(minutes=5)

    session.seen(later)

    assert session.last_seen_at == later
