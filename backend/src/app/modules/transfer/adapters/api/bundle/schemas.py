from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from app.modules.transfer.adapters.api.plan_schemas import (
    PlanBlockerResponse,
    PlannedEntityResponse,
    blockers_from_domain,
    entities_from_domain,
)
from app.modules.transfer.domain.entity_kind import EntityKind
from app.platform.request_model import RequestModel

if TYPE_CHECKING:
    from app.modules.transfer.application.pipeline import AppliedBundle
    from app.modules.transfer.domain.plan import Plan

BUNDLE_EXAMPLE: dict[str, Any] = {
    "format": "menagerist-bundle",
    "version": 3,
    "presets": [
        {
            "ref": "01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e30",
            "kind": "choice_list",
            "label": "Condition grades",
            "description": None,
            "definition": {"options": ["Mint", "Near Mint", "Good"]},
        }
    ],
    "relationship_types": [
        {
            "ref": "01978c3e-9a40-7c11-b3d2-5e7a0f4c8d62",
            "slug": "wrote",
            "label": "Wrote",
            "reverse_label": "Written by",
            "description": None,
            "directional": True,
            "attributes_schema": None,
        }
    ],
    "item_types": [
        {
            "ref": "01978c3e-7d1f-7a4e-8b55-0c6f1d2e9a41",
            "slug": "record",
            "label": "Record",
            "description": None,
            "attributes_schema": {
                "type": "object",
                "properties": {
                    "condition": {
                        "type": "string",
                        "title": "Condition",
                        "x-menagerist": {
                            "kind": "choice",
                            "list": {"$preset": "01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e30"},
                        },
                    }
                },
            },
            "icon": None,
            "colour": None,
        }
    ],
    "items": [
        {
            "ref": "01978c3e-b1c2-7e08-a9d4-6f3b2c1d0e57",
            "type_ref": "01978c3e-7d1f-7a4e-8b55-0c6f1d2e9a41",
            "name": "Kind of Blue",
            "description": None,
            "attributes": {"condition": "Near Mint"},
            "tags": ["jazz"],
            "extra_schema": None,
        },
        {
            "ref": "01978c3e-d4e5-7f19-8c3a-7a4b5c6d7e80",
            "type_ref": "01978c3e-7d1f-7a4e-8b55-0c6f1d2e9a41",
            "name": "A Love Supreme",
            "description": None,
            "attributes": {},
            "tags": [],
            "extra_schema": None,
        },
    ],
    "connections": [
        {
            "source_ref": "01978c3e-d4e5-7f19-8c3a-7a4b5c6d7e80",
            "target_ref": "01978c3e-b1c2-7e08-a9d4-6f3b2c1d0e57",
            "type_ref": "01978c3e-9a40-7c11-b3d2-5e7a0f4c8d62",
            "attributes": {},
        }
    ],
    "collections": [
        {
            "ref": "01978c3e-f6a7-7b2c-9d4e-8b5c6d7e8f91",
            "name": "Jazz shelf",
            "description": None,
            "item_refs": ["01978c3e-b1c2-7e08-a9d4-6f3b2c1d0e57"],
            "definition": None,
        }
    ],
}


class BundlePresetEntry(BaseModel):
    """One saved list, field or field group in a `menagerist-bundle` file."""

    model_config = ConfigDict(
        extra="forbid", json_schema_extra={"examples": [BUNDLE_EXAMPLE["presets"][0]]}
    )

    ref: str = Field(description="Its id within the file; an export uses the id.")
    kind: str = Field(description="`field`, `field_set` or `choice_list`.")
    label: str = Field(description="Its name.")
    description: str | None = Field(default=None, description="What it is for.")
    definition: dict[str, Any] = Field(description="Its definition, by kind.")


_SCHEMA_DESCRIPTION = (
    "Its fields. A field that uses a saved list names it as "
    + '`{"$preset": ref}`, where `ref` is a preset in the same file.'
)


class BundleItemTypeEntry(BaseModel):
    """One item type in a `menagerist-bundle` file of version 2."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [BUNDLE_EXAMPLE["item_types"][0]]},
    )

    ref: str = Field(description="Its id within the file; an export uses the id.")
    slug: str = Field(description="Its short name, as used in URLs.")
    label: str = Field(description="Its name.")
    description: str | None = Field(default=None, description="What it is for.")
    attributes_schema: dict[str, Any] | None = Field(
        default=None,
        description=_SCHEMA_DESCRIPTION,
    )
    icon: str | None = Field(default=None, description="Its icon name.")
    colour: str | None = Field(default=None, description="Its colour name.")


class BundleRelationshipTypeEntry(BaseModel):
    """One connection type in a `menagerist-bundle` file of version 2."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [BUNDLE_EXAMPLE["relationship_types"][0]]},
    )

    ref: str = Field(description="Its id within the file; an export uses the id.")
    slug: str = Field(description="Its short name, as used in URLs.")
    label: str = Field(description="Its name.")
    reverse_label: str | None = Field(
        default=None, description="Its name read from the other end."
    )
    description: str | None = Field(default=None, description="What it is for.")
    directional: bool = Field(
        default=True, description="Whether it reads one way, not both."
    )
    attributes_schema: dict[str, Any] | None = Field(
        default=None, description="Its fields, as an item type's are."
    )


class BundleItemEntry(BaseModel):
    """One item in a `menagerist-bundle` file of version 3."""

    model_config = ConfigDict(
        extra="forbid", json_schema_extra={"examples": [BUNDLE_EXAMPLE["items"][0]]}
    )

    ref: str = Field(description="Its id within the file; an export uses the id.")
    type_ref: str | None = Field(
        default=None,
        description="The `ref` of its item type in the same file; none for no type.",
    )
    name: str = Field(description="Its name.")
    description: str | None = Field(default=None, description="Its notes.")
    attributes: dict[str, Any] = Field(
        default_factory=dict, description="Its field values, by field key."
    )
    tags: list[str] = Field(default_factory=list, description="Its tags.")
    extra_schema: dict[str, Any] | None = Field(
        default=None, description="Fields only this item has."
    )


class BundleConnectionEntry(BaseModel):
    """One connection between two items in a `menagerist-bundle` file."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [BUNDLE_EXAMPLE["connections"][0]]},
    )

    source_ref: str = Field(description="The `ref` of the item it starts from.")
    target_ref: str = Field(description="The `ref` of the item it points to.")
    type_ref: str = Field(description="The `ref` of its connection type.")
    attributes: dict[str, Any] = Field(
        default_factory=dict, description="Its field values, by field key."
    )


class BundleCollectionEntry(BaseModel):
    """One collection in a `menagerist-bundle` file of version 3.

    It has either `item_refs` (a manual collection) or a `definition` (a smart one).
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [BUNDLE_EXAMPLE["collections"][0]]},
    )

    ref: str = Field(description="Its id within the file; an export uses the id.")
    name: str = Field(description="Its name.")
    description: str | None = Field(default=None, description="What it is for.")
    item_refs: list[str] = Field(
        default_factory=list, description="The `ref`s of the items in a manual one."
    )
    definition: dict[str, Any] | None = Field(
        default=None, description="The rule of a smart collection."
    )


class BundleFile(RequestModel):
    """A bundle file to import. `format` says which reader takes it.

    A `menagerist-bundle` file has `version` 1 and the presets it holds,
    `version` 2, which can also hold connection types and item types, or
    `version` 3, which can also hold items, connections and collections.
    """

    model_config = ConfigDict(json_schema_extra={"examples": [BUNDLE_EXAMPLE]})

    format: str = Field(
        description="The file format, such as `menagerist-bundle`.",
        examples=["menagerist-bundle"],
    )
    version: int = Field(description="The version of that format.", examples=[1])
    presets: list[BundlePresetEntry] = Field(
        default_factory=list, description="The saved lists, fields and groups."
    )
    relationship_types: list[BundleRelationshipTypeEntry] = Field(
        default_factory=list,
        description="The connection types; from version 2.",
    )
    item_types: list[BundleItemTypeEntry] = Field(
        default_factory=list,
        description="The item types, with their saved lists in `presets`; version 2.",
    )
    items: list[BundleItemEntry] = Field(
        default_factory=list, description="The items; from version 3."
    )
    connections: list[BundleConnectionEntry] = Field(
        default_factory=list, description="The connections between items; version 3."
    )
    collections: list[BundleCollectionEntry] = Field(
        default_factory=list, description="The collections; from version 3."
    )

    def data(self) -> dict[str, Any]:
        """Return the file as the codec reads it."""
        return self.model_dump(exclude_unset=True)


class BundleFileResponse(BaseModel):
    """A bundle file as exported, ready to save and import again."""

    model_config = ConfigDict(json_schema_extra={"examples": [BUNDLE_EXAMPLE]})

    format: str = Field(description="The file format, such as `menagerist-bundle`.")
    version: int = Field(description="The version of that format.")
    presets: list[BundlePresetEntry] = Field(
        description="The saved lists, fields and groups; each `ref` is its id."
    )
    relationship_types: list[BundleRelationshipTypeEntry] = Field(
        description="The connection types exported."
    )
    item_types: list[BundleItemTypeEntry] = Field(
        description="The item types exported."
    )
    items: list[BundleItemEntry] = Field(description="The items exported.")
    connections: list[BundleConnectionEntry] = Field(
        description="The connections between the items exported."
    )
    collections: list[BundleCollectionEntry] = Field(
        description="The collections exported."
    )


IMPORT_PLAN_EXAMPLE: dict[str, Any] = {
    "ready": True,
    "blockers": [],
    "entities": [
        {
            "kind": "preset",
            "ref": "01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e30",
            "label": "Condition grades",
            "action": "unchanged",
            "reason": "You already have one the same.",
        }
    ],
}


class ImportPlanResponse(BaseModel):
    """What importing a file would do, worked out without writing anything."""

    model_config = ConfigDict(json_schema_extra={"examples": [IMPORT_PLAN_EXAMPLE]})

    ready: bool = Field(description="Whether importing would go ahead.")
    blockers: list[PlanBlockerResponse] = Field(
        description="Problems with the whole file that stop the import."
    )
    entities: list[PlannedEntityResponse] = Field(
        description="Everything in the file, in the order importing makes it."
    )

    @classmethod
    def from_domain(cls, plan: Plan) -> ImportPlanResponse:
        """Build from the file's plan."""
        return cls(
            ready=plan.ready,
            blockers=blockers_from_domain(plan),
            entities=entities_from_domain(plan),
        )


IMPORT_RESULT_EXAMPLE: dict[str, Any] = {
    "created": 1,
    "skipped": 1,
    "presets_created": 1,
    "presets_skipped": 1,
}


class ImportResultResponse(BaseModel):
    """What importing a file created, and what you already had."""

    model_config = ConfigDict(json_schema_extra={"examples": [IMPORT_RESULT_EXAMPLE]})

    created: int = Field(description="Everything added.")
    skipped: int = Field(description="Everything you already had, so left as it is.")
    presets_created: int = Field(description="Saved lists, fields or groups added.")
    presets_skipped: int = Field(
        description="Saved lists, fields or groups you already had."
    )

    @classmethod
    def from_domain(cls, applied: AppliedBundle) -> ImportResultResponse:
        """Build from what applying the file did."""
        return cls(
            created=applied.total_created,
            skipped=applied.total_skipped,
            presets_created=applied.created.get(EntityKind.PRESET, 0),
            presets_skipped=applied.skipped.get(EntityKind.PRESET, 0),
        )
