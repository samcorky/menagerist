from typing import TYPE_CHECKING

import pytest

from app.modules.graph.adapters.persistence.node_type_repository import (
    SqlAlchemyNodeTypeRepository,
)
from app.modules.graph.domain.node_type import NodeType

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "cover_file": {
            "title": "Cover file",
            "type": "string",
            "allOf": [{"pattern": "^cover-"}, {"pattern": r"\.jpg$"}],
            "x-menagerist": {"kind": "text"},
        },
        "label": {"title": "Label", "type": "string", "pattern": "^café 🎵"},
    },
}


async def test_constraint_patterns_round_trip_through_jsonb(
    db_session: AsyncSession,
) -> None:
    """Backslashes, unicode and `allOf` order survive the JSONB column unchanged."""
    repository = SqlAlchemyNodeTypeRepository(db_session)
    node_type = NodeType.create(slug="record", label="Record")
    node_type.attributes_schema = _SCHEMA
    await repository.add(node_type)
    await db_session.flush()
    db_session.expire_all()

    stored = await repository.get(node_type.id)

    assert stored is not None
    assert stored.attributes_schema == _SCHEMA
    cover = stored.attributes_schema["properties"]["cover_file"]
    assert [p["pattern"] for p in cover["allOf"]] == ["^cover-", r"\.jpg$"]
