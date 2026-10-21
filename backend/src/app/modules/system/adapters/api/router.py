from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.entrypoints.api.shared.dependencies import get_current_actor
from app.entrypoints.api.shared.http.csrf import verify_csrf
from app.entrypoints.api.shared.http.origin import own_origin
from app.entrypoints.api.shared.http.problem_response import error_response
from app.entrypoints.api.shared.permission_aware_route import PermissionAwareRoute
from app.modules.system.adapters.api.dependencies import (
    get_get_health_ready_detail_use_case,
    get_get_health_ready_use_case,
    get_get_health_use_case,
    get_get_version_detail_use_case,
    get_get_version_use_case,
    get_run_browser_check_use_case,
)
from app.modules.system.application.get_health import GetHealth, GetHealthQuery
from app.modules.system.application.get_health_ready import (
    GetHealthReady,
    GetHealthReadyQuery,
)
from app.modules.system.application.get_health_ready_detail import (
    GetHealthReadyDetail,
    GetHealthReadyDetailQuery,
)
from app.modules.system.application.get_version import GetVersion, GetVersionQuery
from app.modules.system.application.get_version_detail import (
    GetVersionDetail,
    GetVersionDetailQuery,
)
from app.modules.system.application.run_browser_check import (
    RunBrowserCheck,
    RunBrowserCheckQuery,
)
from app.modules.system.domain.browser_check import BrowserCheckResult, BrowserRequest
from app.modules.system.domain.readiness import (
    CheckObservation as DomainCheckObservation,
    CheckStatus,
    ReadinessReport,
)
from app.shared_kernel.actor import SYSTEM_ACTOR, Actor
from app.shared_kernel.errors import ForbiddenError

router = APIRouter(tags=["System"], route_class=PermissionAwareRoute)

_EXAMPLE_ISO = "2026-01-01T00:00:00.000000+00:00"


class HealthJSONResponse(JSONResponse):
    """JSONResponse with Content-Type: application/health+json."""

    media_type = "application/health+json"


class HealthResponse(BaseModel):
    """Liveness status."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"status": "pass"}]})

    status: Annotated[
        Literal["pass"],
        Field(description="Status of the application.", examples=["pass"]),
    ] = "pass"


class CheckObservation(BaseModel):
    """Single health check observation (IETF draft-inadarei-api-health-check-06)."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        json_schema_extra={
            "examples": [
                {
                    "componentType": "datastore",
                    "observedValue": 1.23,
                    "observedUnit": "ms",
                    "status": "pass",
                    "time": _EXAMPLE_ISO,
                }
            ]
        },
    )

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
            description="Human-readable detail, set only when status is fail or warn.",
            examples=["check failed"],
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
    """Readiness status: nothing but pass or fail."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"status": "pass"}]})

    status: Annotated[
        Literal["pass", "fail"],
        Field(
            description="Whether every required dependency is ready.",
            examples=["pass"],
        ),
    ]

    @classmethod
    def from_domain(cls, report: ReadinessReport) -> ReadyResponse:
        """Collapse the report to pass or fail (a warning is still ready)."""
        return cls(status="fail" if report.status is CheckStatus.FAIL else "pass")


class ReadyDetailResponse(BaseModel):
    """Full readiness report (IETF draft-inadarei-api-health-check-06)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "status": "pass",
                    "checks": {
                        "database:responseTime": [
                            {
                                "componentType": "datastore",
                                "observedValue": 1.23,
                                "observedUnit": "ms",
                                "status": "pass",
                                "time": _EXAMPLE_ISO,
                            }
                        ]
                    },
                }
            ]
        }
    )

    status: Annotated[
        Literal["pass", "warn", "fail"],
        Field(
            description="Overall readiness - fail beats warn beats pass.",
            examples=["pass"],
        ),
    ]
    checks: Annotated[
        dict[str, list[CheckObservation]],
        Field(description="Named check observation lists keyed by component:metric."),
    ]

    @classmethod
    def from_domain(cls, report: ReadinessReport) -> ReadyDetailResponse:
        """Build the API schema from the domain readiness report."""
        return cls(
            status=report.status.value,
            checks={
                key: [CheckObservation.from_domain(obs) for obs in observations]
                for key, observations in report.checks.items()
            },
        )


class VersionResponse(BaseModel):
    """Public application name and version."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"name": "menagerist", "current_version": "1.2.3"}]
        }
    )

    name: Annotated[
        str,
        Field(description="Distribution package name.", examples=["menagerist"]),
    ]
    current_version: Annotated[
        str,
        Field(description="Current version of the application.", examples=["1.2.3"]),
    ]


class VersionDetailResponse(VersionResponse):
    """Build and version metadata, for administrators."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "menagerist",
                    "current_version": "1.2.3",
                    "commit_sha": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
                    "short_sha": "a1b2c3d",
                    "branch": "main",
                    "dirty": False,
                    "build_timestamp": _EXAMPLE_ISO,
                    "migration_head": ["a1b2c3d4e5f6"],
                }
            ]
        }
    )

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


_ERR = "check failed"
_FORBIDDEN = "You do not have permission to do that."

_DETAIL_200: dict[str, object] = {
    "content": {
        "application/health+json": {
            "example": {
                "status": "pass",
                "checks": {
                    "database:responseTime": [_check_ex("ms", 1.23, status="pass")],
                    "database:version": [_check_ex("version", "18.2.1", status="pass")],
                    "database:migrationRevision": [
                        _check_ex("revision", "a1b2c3d4e5f6", status="pass")
                    ],
                    "database:poolUtilization": [
                        _check_ex("percent", 20.0, status="pass")
                    ],
                },
            }
        }
    },
}

_DETAIL_503: dict[str, object] = {
    "description": "One or more dependency checks failed.",
    "content": {
        "application/health+json": {
            "example": {
                "status": "fail",
                "checks": {
                    "database:responseTime": [_check_ex("ms", output=_ERR)],
                    "database:version": [_check_ex("version", output=_ERR)],
                    "database:migrationRevision": [_check_ex("revision", output=_ERR)],
                    "database:poolUtilization": [
                        _check_ex("percent", 0.0, status="pass")
                    ],
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


_PUBLIC_200: dict[str, object] = {
    "content": {"application/health+json": {"example": {"status": "pass"}}},
}

_PUBLIC_503: dict[str, object] = {
    "description": "A required dependency is not ready.",
    "content": {"application/health+json": {"example": {"status": "fail"}}},
}


@router.get(
    "/health/ready",
    summary="Readiness check",
    operation_id="get_health_ready",
    response_model=ReadyResponse,
    response_class=HealthJSONResponse,
    responses={200: _PUBLIC_200, 503: _PUBLIC_503},
)
async def get_health_ready(
    response: Response,
    use_case: Annotated[GetHealthReady, Depends(get_get_health_ready_use_case)],
) -> ReadyResponse:
    """Report whether the required dependencies are reachable.

    The answer is only pass (200) or fail (503); `/health/ready/detail` has the
    measurements.
    """
    response.headers["Cache-Control"] = "max-age=10"
    report = await use_case.handle(GetHealthReadyQuery(), SYSTEM_ACTOR)
    if report.status is CheckStatus.FAIL:
        response.status_code = 503
    return ReadyResponse.from_domain(report)


@router.get(
    "/health/ready/detail",
    summary="Readiness check with detail",
    operation_id="get_health_ready_detail",
    response_model=ReadyDetailResponse,
    response_class=HealthJSONResponse,
    response_model_exclude_none=True,
    responses={
        200: _DETAIL_200,
        503: _DETAIL_503,
        **error_response(ForbiddenError, detail=_FORBIDDEN),
    },
)
async def get_health_ready_detail(
    response: Response,
    use_case: Annotated[
        GetHealthReadyDetail, Depends(get_get_health_ready_detail_use_case)
    ],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> ReadyDetailResponse:
    """Report every readiness check with its observed values (administrators)."""
    report = await use_case.handle(GetHealthReadyDetailQuery(), actor)
    if report.status is CheckStatus.FAIL:
        response.status_code = 503
    return ReadyDetailResponse.from_domain(report)


@router.get(
    "/version",
    summary="Application version",
    operation_id="get_version",
)
async def get_version(
    use_case: Annotated[GetVersion, Depends(get_get_version_use_case)],
) -> VersionResponse:
    """Report the name and version of the running instance."""
    app_info = await use_case.handle(GetVersionQuery(), SYSTEM_ACTOR)
    return VersionResponse(name=app_info.name, current_version=app_info.version)


@router.get(
    "/version/detail",
    summary="Application version with build provenance",
    operation_id="get_version_detail",
    response_model_exclude_none=True,
    responses=error_response(ForbiddenError, detail=_FORBIDDEN),
)
async def get_version_detail(
    use_case: Annotated[GetVersionDetail, Depends(get_get_version_detail_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> VersionDetailResponse:
    """Report version and build provenance (administrators)."""
    app_info = await use_case.handle(GetVersionDetailQuery(), actor)
    return VersionDetailResponse(
        name=app_info.name,
        current_version=app_info.version,
        commit_sha=app_info.commit_sha,
        short_sha=app_info.short_sha,
        branch=app_info.branch,
        dirty=app_info.dirty,
        build_timestamp=app_info.build_timestamp,
        migration_head=list(app_info.migration_head),
    )


class BrowserCheckResponse(BaseModel):
    """Whether the browser's own headers reached the app intact."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "status": "pass",
                    "sec_fetch_site": "same-origin",
                    "origin": "https://menagerist.example",
                    "seen_origin": "https://menagerist.example",
                }
            ]
        }
    )

    status: Annotated[
        Literal["pass", "warn", "fail"],
        Field(description="Whether the headers arrived intact.", examples=["pass"]),
    ]
    sec_fetch_site: Annotated[
        str | None,
        Field(
            description="The Sec-Fetch-Site header the app received, if any.",
            examples=["same-origin"],
        ),
    ]
    origin: Annotated[
        str | None,
        Field(
            description="The Origin header the app received, if any.",
            examples=["https://menagerist.example"],
        ),
    ]
    seen_origin: Annotated[
        str,
        Field(
            description="The origin the app rebuilt from the request.",
            examples=["https://menagerist.example"],
        ),
    ]
    output: Annotated[
        str | None,
        Field(description="What to check, set only when status is warn or fail."),
    ] = None

    @classmethod
    def from_domain(cls, result: BrowserCheckResult) -> BrowserCheckResponse:
        """Build the API schema from the domain result."""
        return cls(
            status=result.status.value,
            sec_fetch_site=result.sec_fetch_site,
            origin=result.origin,
            seen_origin=result.seen_origin,
            output=result.output,
        )


# A POST on purpose: verify_csrf skips safe methods, and a request that lost the
# browser's headers is refused there with `csrf_failed`, before this runs.
@router.post(
    "/browser-check",
    summary="Browser header check",
    operation_id="run_browser_check",
    dependencies=[Depends(verify_csrf)],
    response_model_exclude_none=True,
    responses=error_response(ForbiddenError, detail=_FORBIDDEN),
)
async def run_browser_check(
    request: Request,
    response: Response,
    use_case: Annotated[RunBrowserCheck, Depends(get_run_browser_check_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> BrowserCheckResponse:
    """Report whether the browser's origin headers reach the app (administrators).

    Call it from a browser: a `403` `csrf_failed` answer means the headers were
    removed on the way in.
    """
    response.headers["Cache-Control"] = "no-store"
    result = await use_case.handle(
        RunBrowserCheckQuery(
            request=BrowserRequest(
                sec_fetch_site=request.headers.get("Sec-Fetch-Site"),
                origin=request.headers.get("Origin"),
                seen_origin=own_origin(request),
            )
        ),
        actor,
    )
    return BrowserCheckResponse.from_domain(result)
