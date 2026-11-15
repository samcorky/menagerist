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
    "version": 1,
    "presets": [
        {
            "ref": "01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e30",
            "kind": "choice_list",
            "label": "Condition grades",
            "description": None,
            "definition": {"options": ["Mint", "Near Mint", "Good"]},
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


class BundleFile(RequestModel):
    """A bundle file to import. `format` says which reader takes it.

    A `menagerist-bundle` file has `version` 1 and the presets it holds.
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
