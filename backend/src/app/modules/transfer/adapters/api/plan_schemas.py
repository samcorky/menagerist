"""The API shape of a `Plan`, shared by every install that offers a dry run."""

from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from app.modules.transfer.domain.plan import Plan


class PlanAction(StrEnum):
    """What installing would do with one entity."""

    CREATE = "create"
    UNCHANGED = "unchanged"
    CONFLICT = "conflict"


class PlannedEntityResponse(BaseModel):
    """One entity of what is being installed, and what installing would do with it."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "kind": "item_type",
                    "ref": "album",
                    "label": "Album",
                    "action": "conflict",
                    "reason": "You already have an item type called 'album'. "
                    + "Rename or remove it, then try again.",
                }
            ]
        }
    )

    kind: str = Field(
        description="What sort of thing it is, such as `item_type` or `item`."
    )
    ref: str = Field(description="The entity's id within what is installed.")
    label: str = Field(description="Its name, as it would be shown.")
    action: PlanAction
    reason: str | None = Field(
        default=None, description="Why it is unchanged or conflicts."
    )


class PlanBlockerResponse(BaseModel):
    """Something that stops the whole install."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"code": "RequirementsNotMetError", "reason": "Add Vinyl first."}
            ]
        }
    )

    code: str = Field(description="The problem `title` installing would return for it.")
    reason: str = Field(description="The problem `detail` installing would return.")


def entities_from_domain(plan: Plan) -> list[PlannedEntityResponse]:
    """Build the response for each of the plan's entities, in plan order."""
    return [
        PlannedEntityResponse(
            kind=e.kind.value,
            ref=e.ref,
            label=e.label,
            action=PlanAction(e.action.value),
            reason=e.reason,
        )
        for e in plan.entities
    ]


def blockers_from_domain(plan: Plan) -> list[PlanBlockerResponse]:
    """Build the response for each of the plan's blockers."""
    return [PlanBlockerResponse(code=b.code, reason=b.reason) for b in plan.blockers]
