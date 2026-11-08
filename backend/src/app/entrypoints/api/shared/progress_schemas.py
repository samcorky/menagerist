"""API response models for progress snapshots, shared by every module that reports."""

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from pydantic.config import JsonDict

# Declared here, not imported from the shared kernel, because a `type` alias is
# served as a separate schema and a description beside its `$ref` breaks the
# `no-$ref-siblings` rule. `test_progress_schemas.py` keeps them in step.
PhaseStateName = Literal["waiting", "running", "done"]
UnitName = Literal["count", "bytes"]
OutcomeName = Literal["running", "succeeded", "failed"]

PHASE_EXAMPLE: JsonDict = {
    "key": "media",
    "label": "Restoring photos and files",
    "state": "running",
    "done": 1240,
    "total": 2000,
    "unit": "count",
}

SNAPSHOT_EXAMPLE: JsonDict = {
    "phases": [
        {
            "key": "verify",
            "label": "Checking the backup",
            "state": "done",
            "done": 2097152,
            "total": 2097152,
            "unit": "bytes",
        },
        {
            "key": "database",
            "label": "Restoring your collection",
            "state": "done",
            "done": 4210,
            "total": 4210,
            "unit": "count",
        },
        PHASE_EXAMPLE,
    ],
    "message": "Restoring photos and files",
    "percent": 81,
    "outcome": "running",
}


class PhaseProgressResponse(BaseModel):
    """One planned stage of an operation and how far it has got."""

    model_config = ConfigDict(
        from_attributes=True, json_schema_extra={"examples": [PHASE_EXAMPLE]}
    )

    key: str = Field(description="Stable identifier of the phase within its plan.")
    label: str = Field(description="What the phase is doing, in plain words.")
    state: PhaseStateName = Field(
        description="Whether the phase is waiting, running or done."
    )
    done: int = Field(description="Units finished so far in this phase.")
    total: int | None = Field(
        description="Units in the phase, or null while the total is not known yet."
    )
    unit: UnitName = Field(
        description=(
            "What `done` and `total` count: `count` for items such as files or rows, "
            + "`bytes` for data read."
        )
    )


class ProgressSnapshotResponse(BaseModel):
    """How a long operation is getting on: phases, an overall percentage, a note."""

    model_config = ConfigDict(
        from_attributes=True, json_schema_extra={"examples": [SNAPSHOT_EXAMPLE]}
    )

    phases: list[PhaseProgressResponse] = Field(
        description="Every planned phase in order, each with its own progress."
    )
    message: str | None = Field(
        description=(
            "What is happening now, or why the operation failed. "
            + "Null when there is nothing to add."
        )
    )
    percent: int = Field(
        description="Overall completion from 0 to 100, weighting each phase."
    )
    outcome: OutcomeName = Field(
        description="Whether the operation is running, has succeeded or has failed."
    )
