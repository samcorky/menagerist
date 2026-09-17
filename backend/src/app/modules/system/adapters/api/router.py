from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.modules.system.adapters.api.dependencies import (
    get_get_health_ready_use_case,
    get_get_health_use_case,
    get_get_version_use_case,
)
from app.modules.system.application.get_health import GetHealth, GetHealthQuery
from app.modules.system.application.get_health_ready import (
    GetHealthReady,
    GetHealthReadyQuery,
)
from app.modules.system.application.get_version import GetVersion, GetVersionQuery
from app.modules.system.domain.readiness import (
    CheckObservation as DomainCheckObservation,
    CheckStatus,
    ReadinessReport,
)
from app.shared_kernel.actor import SYSTEM_ACTOR

router = APIRouter(tags=["System"])

_EXAMPLE_ISO = "2026-01-01T00:00:00.000000+00:00"


class HealthJSONResponse(JSONResponse):
    """JSONResponse with Content-Type: application/health+json."""

    media_type = "application/health+json"


class HealthResponse(BaseModel):
    """Liveness status."""

    status: Annotated[
        Literal["pass"],
        Field(description="Status of the application.", examples=["pass"]),
    ] = "pass"


class CheckObservation(BaseModel):
    """Single health check observation (IETF draft-inadarei-api-health-check-06)."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    component_type: Annotated[
        str,
        Field(
            description="Component category for this observation.",
            examples=["datastore"],
        ),
    ]
    observed_value: Annotated[
        float | str,
        Field(
            description="Measured quantity or descriptor.",
            examples=[1.23],
        ),
    ]
    observed_unit: Annotated[
        str,
        Field(
            description="Unit of the observed value.",
            examples=["ms", "percent", "version", "revision"],
        ),
    ]
    status: Annotated[
        Literal["pass", "warn", "fail"],
        Field(
            description="Pass/warn/fail result of this individual check.",
            examples=["pass"],
        ),
    ]
    time: Annotated[
        str,
        Field(
            description="ISO 8601 timestamp when this observation was taken.",
            examples=[_EXAMPLE_ISO],
        ),
    ]
    output: Annotated[
        str | None,
        Field(
            default=None,
            description="Human-readable error detail, set only when status is fail.",
            examples=["connection refused"],
        ),
    ] = None

    @classmethod
    def from_domain(cls, observation: DomainCheckObservation) -> CheckObservation:
        """Build the API schema from the domain observation."""
        return cls(
            component_type=observation.component_type,
            observed_value=observation.observed_value,
            observed_unit=observation.observed_unit,
            status=observation.status.value,
            time=observation.time.isoformat(),
            output=observation.output,
        )


class ReadyResponse(BaseModel):
    """Readiness status (IETF draft-inadarei-api-health-check-06)."""

    status: Annotated[
        Literal["pass", "warn", "fail"],
        Field(
            description="Overall readiness — fail beats warn beats pass.",
            examples=["pass"],
        ),
    ]
    checks: Annotated[
        dict[str, CheckObservation],
        Field(description="Named check observations keyed by component:metric."),
    ]

    @classmethod
    def from_domain(cls, report: ReadinessReport) -> ReadyResponse:
        """Build the API schema from the domain readiness report."""
        return cls(
            status=report.status.value,
            checks={
                key: CheckObservation.from_domain(observation)
                for key, observation in report.checks.items()
            },
        )


class VersionResponse(BaseModel):
    """Build and version metadata."""

    name: Annotated[
        str,
        Field(description="Distribution package name.", examples=["menagerist"]),
    ]
    current_version: Annotated[
        str,
        Field(description="Current version of the application.", examples=["1.2.3"]),
    ]
    commit_sha: Annotated[
        str | None,
        Field(
            default=None,
            description="Full git commit SHA captured at build time.",
            examples=["a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"],
        ),
    ] = None
    short_sha: Annotated[
        str | None,
        Field(
            default=None,
            description="Abbreviated git commit SHA.",
            examples=["a1b2c3d"],
        ),
    ] = None
    branch: Annotated[
        str | None,
        Field(
            default=None,
            description="Git branch at build time.",
            examples=["main"],
        ),
    ] = None
    dirty: Annotated[
        bool | None,
        Field(
            default=None,
            description="True if uncommitted changes existed at build time.",
            examples=[False],
        ),
    ] = None
    build_timestamp: Annotated[
        datetime | None,
        Field(
            default=None,
            description="UTC timestamp when the package was built.",
            examples=[_EXAMPLE_ISO],
        ),
    ] = None
    migration_head: Annotated[
        list[str],
        Field(
            description="Alembic head revision(s) bundled with this build.",
            examples=[["a1b2c3d4e5f6"]],
        ),
    ]


def _check_ex(
    unit: str,
    value: float | str = "unknown",
    *,
    status: str = "fail",
    output: str | None = None,
) -> dict[str, object]:
    result: dict[str, object] = {
        "componentType": "datastore",
        "observedValue": value,
        "observedUnit": unit,
        "status": status,
        "time": _EXAMPLE_ISO,
    }
    if output is not None:
        result["output"] = output
    return result


_ERR = "connection refused"

_RESPONSE_200: dict[str, object] = {
    "content": {
        "application/health+json": {
            "example": {
                "status": "pass",
                "checks": {
                    "database:responseTime": _check_ex("ms", 1.23, status="pass"),
                    "database:version": _check_ex("version", "18.2.1", status="pass"),
                    "database:migrationRevision": _check_ex(
                        "revision", "a1b2c3d4e5f6", status="pass"
                    ),
                    "database:poolUtilization": _check_ex(
                        "percent", 20.0, status="pass"
                    ),
                },
            }
        }
    },
}

_RESPONSE_503: dict[str, object] = {
    "description": "One or more dependency checks failed.",
    "content": {
        "application/health+json": {
            "example": {
                "status": "fail",
                "checks": {
                    "database:responseTime": _check_ex("ms", output=_ERR),
                    "database:version": _check_ex("version", output=_ERR),
                    "database:migrationRevision": _check_ex("revision", output=_ERR),
                    "database:poolUtilization": _check_ex(
                        "percent", 0.0, status="pass"
                    ),
                },
            }
        }
    },
}


@router.get(
    "/health",
    summary="Liveness check",
    operation_id="get_health",
    response_class=HealthJSONResponse,
)
async def get_health(
    use_case: Annotated[GetHealth, Depends(get_get_health_use_case)],
) -> HealthResponse:
    """Report that the process is up and able to accept requests."""
    await use_case.handle(GetHealthQuery(), SYSTEM_ACTOR)
    return HealthResponse()


@router.get(
    "/health/ready",
    summary="Readiness check",
    operation_id="get_health_ready",
    response_model=ReadyResponse,
    response_class=HealthJSONResponse,
    response_model_exclude_none=True,
    responses={200: _RESPONSE_200, 503: _RESPONSE_503},
)
async def get_health_ready(
    response: Response,
    use_case: Annotated[GetHealthReady, Depends(get_get_health_ready_use_case)],
) -> ReadyResponse:
    """Report readiness by verifying all required dependencies are reachable."""
    report = await use_case.handle(GetHealthReadyQuery(), SYSTEM_ACTOR)
    if report.status is CheckStatus.FAIL:
        response.status_code = 503
    return ReadyResponse.from_domain(report)


@router.get(
    "/version",
    summary="Application version",
    operation_id="get_version",
    response_model_exclude_none=True,
)
async def get_version(
    use_case: Annotated[GetVersion, Depends(get_get_version_use_case)],
) -> VersionResponse:
    """Report the project version and build provenance of the running instance."""
    app_info = await use_case.handle(GetVersionQuery(), SYSTEM_ACTOR)
    return VersionResponse(
        name=app_info.name,
        current_version=app_info.version,
        commit_sha=app_info.commit_sha,
        short_sha=app_info.short_sha,
        branch=app_info.branch,
        dirty=app_info.dirty,
        build_timestamp=app_info.build_timestamp,
        migration_head=list(app_info.migration_head),
    )
