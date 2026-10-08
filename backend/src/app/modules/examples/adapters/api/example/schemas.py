import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from app.modules.examples.application.install_example_pack import installation_counts
from app.modules.examples.domain.installation import InstallationStatus

if TYPE_CHECKING:
    from app.modules.examples.application.install_example_pack import InstallResult
    from app.modules.examples.application.list_example_entities import ExampleEntities
    from app.modules.examples.application.list_example_packs import ExamplePackStatus
    from app.modules.examples.application.removal import KeptEntity
    from app.modules.examples.application.uninstall_example_pack import UninstallResult
    from app.modules.examples.domain.pack import PackCounts

_COUNTS_EXAMPLE: dict[str, Any] = {
    "presets": 1,
    "relationship_types": 2,
    "item_types": 3,
    "items": 12,
    "connections": 14,
    "collections": 2,
}
_KEPT_EXAMPLE: dict[str, Any] = {
    "kind": "item",
    "label": "Blue (my copy)",
    "reason": "edited",
}


class PackCountsResponse(BaseModel):
    """How many of each thing an example set contains."""

    model_config = ConfigDict(json_schema_extra={"examples": [_COUNTS_EXAMPLE]})

    presets: int
    relationship_types: int
    item_types: int
    items: int
    connections: int
    collections: int

    @classmethod
    def from_domain(cls, counts: PackCounts) -> PackCountsResponse:
        """Build from the domain counts."""
        return cls(
            presets=counts.presets,
            relationship_types=counts.relationship_types,
            item_types=counts.item_types,
            items=counts.items,
            connections=counts.connections,
            collections=counts.collections,
        )


class InstallationResponse(BaseModel):
    """An example set that is installed on this server."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "status": "installed",
                    "installed_at": "2026-10-06T10:14:44.465954Z",
                    "counts": _COUNTS_EXAMPLE,
                }
            ]
        }
    )

    status: InstallationStatus
    installed_at: datetime | None
    counts: PackCountsResponse


class ExamplePackResponse(BaseModel):
    """A shipped example set and whether it is installed."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "vinyl",
                    "name": "Vinyl and signed items",
                    "description": "Records, artists and signings.",
                    "counts": _COUNTS_EXAMPLE,
                    "installation": {
                        "status": "installed",
                        "installed_at": "2026-10-06T10:14:44.465954Z",
                        "counts": _COUNTS_EXAMPLE,
                    },
                }
            ]
        }
    )

    id: str
    name: str
    description: str
    counts: PackCountsResponse
    installation: InstallationResponse | None

    @classmethod
    def from_status(cls, status: ExamplePackStatus) -> ExamplePackResponse:
        """Build from a list-query result."""
        installation = status.installation
        return cls(
            id=status.summary.id,
            name=status.summary.name,
            description=status.summary.description,
            counts=PackCountsResponse.from_domain(status.summary.counts),
            installation=None
            if installation is None
            else InstallationResponse(
                status=installation.status,
                installed_at=installation.installed_at,
                counts=PackCountsResponse.from_domain(
                    installation_counts(installation)
                ),
            ),
        )


class InstallResultResponse(BaseModel):
    """What adding an example set created."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"pack_id": "vinyl", "created": _COUNTS_EXAMPLE}]
        }
    )

    pack_id: str
    created: PackCountsResponse

    @classmethod
    def from_domain(cls, result: InstallResult) -> InstallResultResponse:
        """Build from the install result."""
        return cls(
            pack_id=result.pack_id,
            created=PackCountsResponse.from_domain(result.created),
        )


class KeptEntityResponse(BaseModel):
    """Something removal left in place, and why."""

    model_config = ConfigDict(json_schema_extra={"examples": [_KEPT_EXAMPLE]})

    kind: str
    label: str
    reason: str

    @classmethod
    def from_domain(cls, kept: KeptEntity) -> KeptEntityResponse:
        """Build from a kept entity."""
        return cls(kind=kept.kind.value, label=kept.label, reason=kept.reason)


class UninstallResultResponse(BaseModel):
    """What removing an example set did."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "pack_id": "vinyl",
                    "removed": _COUNTS_EXAMPLE,
                    "kept": [_KEPT_EXAMPLE],
                }
            ]
        }
    )

    pack_id: str
    removed: PackCountsResponse
    kept: list[KeptEntityResponse]

    @classmethod
    def from_domain(cls, result: UninstallResult) -> UninstallResultResponse:
        """Build from the uninstall result."""
        return cls(
            pack_id=result.pack_id,
            removed=PackCountsResponse.from_domain(result.removed),
            kept=[KeptEntityResponse.from_domain(k) for k in result.kept],
        )


class ExampleEntitiesResponse(BaseModel):
    """The items, item types and collections that example sets currently own."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "item_ids": ["0198f1c2-7b1e-7c3a-9d4e-2f6a8b0c1d23"],
                    "item_type_ids": ["0198f1c2-7b1e-7c3a-9d4e-2f6a8b0c1d24"],
                    "collection_ids": ["0198f1c2-7b1e-7c3a-9d4e-2f6a8b0c1d25"],
                }
            ]
        }
    )

    item_ids: list[uuid.UUID]
    item_type_ids: list[uuid.UUID]
    collection_ids: list[uuid.UUID]

    @classmethod
    def from_domain(cls, entities: ExampleEntities) -> ExampleEntitiesResponse:
        """Build from the list-entities query result."""
        return cls(
            item_ids=entities.item_ids,
            item_type_ids=entities.item_type_ids,
            collection_ids=entities.collection_ids,
        )
