"""The progress response models match the shared kernel's vocabulary."""

from typing import get_args

from app.entrypoints.api.shared.progress_schemas import (
    OutcomeName,
    PhaseStateName,
    ProgressSnapshotResponse,
    UnitName,
)
from app.shared_kernel.progress import (
    Outcome,
    PhaseState,
    PhaseStatus,
    ProgressSnapshot,
    Unit,
)


def test_the_response_values_match_the_shared_kernel() -> None:
    """The response declares its own enums, so they must not drift."""
    assert get_args(PhaseStateName) == get_args(PhaseStatus.__value__)
    assert get_args(UnitName) == get_args(Unit.__value__)
    assert get_args(OutcomeName) == get_args(Outcome.__value__)


def test_a_snapshot_converts_to_its_response() -> None:
    """The response is built straight from the shared-kernel snapshot."""
    snapshot = ProgressSnapshot(
        phases=(
            PhaseState(
                key="media",
                label="Saving",
                state="running",
                done=1,
                total=2,
                unit="count",
            ),
        ),
        message=None,
        percent=50,
        outcome="running",
    )
    body = ProgressSnapshotResponse.model_validate(snapshot).model_dump(mode="json")
    assert body["percent"] == 50
    assert body["phases"][0] == {
        "key": "media",
        "label": "Saving",
        "state": "running",
        "done": 1,
        "total": 2,
        "unit": "count",
    }


def test_every_property_is_described() -> None:
    """The API style lint wants a description on each property."""
    schema = ProgressSnapshotResponse.model_json_schema()
    defs = schema["$defs"]["PhaseProgressResponse"]["properties"]
    for properties in (schema["properties"], defs):
        missing = [
            name for name, spec in properties.items() if "description" not in spec
        ]
        assert missing == []
