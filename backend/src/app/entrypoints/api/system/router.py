from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.platform.app_info import AppInfo, load_app_info

router = APIRouter(tags=["System"])


class HealthResponse(BaseModel):
    """Status of the application."""

    status: Annotated[
        Literal["pass"],
        Field(description="Status of the application.", examples=["pass"]),
    ] = "pass"


class VersionResponse(BaseModel):
    """Current version of the application."""

    current_version: Annotated[
        str,
        Field(description="Current version of the application.", examples=["1.2.3"]),
    ]


@router.get("/health", summary="Liveness check", operation_id="get_health")
def get_health() -> HealthResponse:
    """Report that the process is up and able to accept requests."""
    return HealthResponse()


@router.get("/version", summary="Application version", operation_id="get_version")
def get_version(
    app_info: Annotated[AppInfo, Depends(load_app_info)],
) -> VersionResponse:
    """Report the project version of the running instance."""
    return VersionResponse(current_version=app_info.version)
