import uuid
from collections.abc import Mapping  # noqa: TC003
from dataclasses import dataclass
from datetime import UTC, datetime

from app.modules.transfer.domain.entity_kind import EntityKind
from app.shared_kernel.mixins import Identifiable, Owned, Timestamped


@dataclass(kw_only=True, eq=False)
class SourceLink(Identifiable, Owned, Timestamped):
    """Where an entity came from: a source's key for it, and what was imported.

    `fields` holds a hash per field as last imported, so a later import can tell
    which fields the person has edited and which the source has changed. It is a
    map, not a snapshot, so values can be added alongside the hashes later.
    """

    source: str
    kind: EntityKind
    key: str
    entity_id: uuid.UUID
    fields: dict[str, str]
    imported_at: datetime

    @classmethod
    def create(
        cls,
        owner_id: uuid.UUID,
        source: str,
        kind: EntityKind,
        key: str,
        entity_id: uuid.UUID,
        fields: Mapping[str, str],
    ) -> SourceLink:
        """Link `owner_id`'s `entity_id` to `key` in `source`, generating its id."""
        now = datetime.now(UTC)
        return cls(
            id=uuid.uuid7(),
            owner_id=owner_id,
            source=source,
            kind=kind,
            key=key,
            entity_id=entity_id,
            fields=dict(fields),
            imported_at=now,
            created_at=now,
            updated_at=now,
        )

    def record_import(self, entity_id: uuid.UUID, fields: Mapping[str, str]) -> None:
        """Point the link at `entity_id` and record what was imported into it."""
        self.entity_id = entity_id
        self.fields = dict(fields)
        self.imported_at = datetime.now(UTC)
        self.touch()

    def changed_fields(self, current: Mapping[str, str]) -> frozenset[str]:
        """Return the fields whose hash in `current` differs from the last import.

        A field present on only one side counts as changed.
        """
        keys = self.fields.keys() | current.keys()
        return frozenset(k for k in keys if self.fields.get(k) != current.get(k))
