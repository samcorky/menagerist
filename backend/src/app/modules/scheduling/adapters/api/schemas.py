"""Response bodies for the scheduling API."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.scheduling.application.preview_schedule import SchedulePreview  # noqa: TC001


class SchedulePreviewResponse(BaseModel):
    """When a schedule would next run."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "timezone": "Europe/London",
                    "runs": [
                        "2026-10-29T03:00:00Z",
                        "2026-10-30T03:00:00Z",
                        "2026-10-31T03:00:00Z",
                    ],
                }
            ]
        }
    )

    timezone: str = Field(
        description="The instance timezone the schedule is read in (an IANA name)."
    )
    runs: list[datetime] = Field(
        description="The next runs as UTC instants, soonest first. Empty when off."
    )

    @classmethod
    def from_domain(cls, preview: SchedulePreview) -> SchedulePreviewResponse:
        """Build the response for a preview."""
        return cls(timezone=preview.timezone, runs=preview.runs)
