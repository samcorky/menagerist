"""The API shape of a `Plan`, shared by every install that offers a dry run."""

import uuid
from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from app.modules.transfer.domain.plan import Plan


class PlanAction(StrEnum):
    """What installing would do with one entity.

    `ambiguous` rows are skipped, with the reason, while the rest is installed.
    """

    CREATE = "create"
    UNCHANGED = "unchanged"
    SKIP = "skip"
    CONFLICT = "conflict"
    AMBIGUOUS = "ambiguous"


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
                    "matched_id": None,
                    "matched_name": None,
                    "changed": [],
                    "deleted": False,
                },
                {
                    "kind": "item",
                    "ref": "row-14",
                    "label": "Alien #1",
                    "action": "unchanged",
                    "reason": "Already imported.",
                    "matched_id": "0192f4a8-5c3e-7d21-9a6b-3e8f1c2d4b5a",
                    "matched_name": "Alien #1",
                    "changed": ["attributes.signed_on"],
                    "source_key": "A14",
                    "deleted": False,
                },
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
        default=None,
        description="Why it is unchanged, left out, conflicts or is ambiguous.",
    )
    matched_id: uuid.UUID | None = Field(
        default=None,
        description="The id of the item you have that this one was recognised as.",
    )
    matched_name: str | None = Field(
        default=None, description="That item's name, as it is now."
    )
    changed: list[str] = Field(
        description="Fields whose value in the file differs from what was last "
        + "imported: `name`, `description`, `tags` or `attributes.<key>`.",
    )
    source_key: str | None = Field(
        default=None,
        description="The key it has in its source, such as the row's key column; "
        + "send it in `restore` to bring back one deleted after importing.",
    )
    deleted: bool = Field(
        description="Whether it is left out because you deleted it after importing "
        + "it; sending its `source_key` in `restore` brings it back."
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
            matched_id=e.matched_id,
            matched_name=e.matched_name,
            changed=list(e.changed),
            source_key=e.source_key,
            deleted=e.deleted,
        )
        for e in plan.entities
    ]


def blockers_from_domain(plan: Plan) -> list[PlanBlockerResponse]:
    """Build the response for each of the plan's blockers."""
    return [PlanBlockerResponse(code=b.code, reason=b.reason) for b in plan.blockers]
