"""Tests for the optional `extra` component of `etag_from_entity`."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from app.shared_kernel.etag import etag_from_entity


@dataclass
class _Entity:
    id: uuid.UUID
    updated_at: datetime


def test_extra_changes_the_etag_and_none_matches_the_plain_form() -> None:
    """Different extras give different tags; no extra equals the id+time tag."""
    entity = _Entity(id=uuid.uuid7(), updated_at=datetime(2026, 1, 1, tzinfo=UTC))

    plain = etag_from_entity(entity)

    assert etag_from_entity(entity, None) == plain
    assert etag_from_entity(entity, "1") != plain
    assert etag_from_entity(entity, "1") != etag_from_entity(entity, "2")
    assert etag_from_entity(entity, "1") == etag_from_entity(entity, "1")
    assert plain.startswith('W/"')
