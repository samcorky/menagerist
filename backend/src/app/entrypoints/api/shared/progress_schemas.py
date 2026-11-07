"""API response models for progress snapshots, shared by every module that reports."""

from pydantic import BaseModel, ConfigDict

from app.shared_kernel.progress import Outcome, PhaseStatus, Unit


class PhaseProgressResponse(BaseModel):
    """One planned stage of an operation and how far it has got."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "key": "media",
                    "label": "Restoring photos and files",
                    "state": "running",
                    "done": 1240,
                    "total": 2000,
                    "unit": "count",
                }
            ]
        },
    )

    key: str
    label: str
    state: PhaseStatus
    done: int
    total: int | None
    unit: Unit


class ProgressSnapshotResponse(BaseModel):
    """How a long operation is getting on: phases, an overall percentage, a note."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
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
                        {
                            "key": "media",
                            "label": "Restoring photos and files",
                            "state": "running",
                            "done": 1240,
                            "total": 2000,
                            "unit": "count",
                        },
                    ],
                    "message": "Restoring photos and files",
                    "percent": 81,
                    "outcome": "running",
                }
            ]
        },
    )

    phases: list[PhaseProgressResponse]
    message: str | None
    percent: int
    outcome: Outcome
