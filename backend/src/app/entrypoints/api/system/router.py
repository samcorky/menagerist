import time
from datetime import UTC, datetime
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.pool import QueuePool

from app.platform.alembic_runner import code_head_revisions, db_current_revisions
from app.platform.app_info import AppInfo, load_app_info
from app.platform.database import get_engine, get_session_factory

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
        Literal["pass", "fail"],
        Field(
            description="Pass/fail result of this individual check.",
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


class ReadyResponse(BaseModel):
    """Readiness status (IETF draft-inadarei-api-health-check-06)."""

    status: Annotated[
        Literal["pass", "fail"],
        Field(
            description="Overall readiness — fail if any single check fails.",
            examples=["pass"],
        ),
    ]
    checks: Annotated[
        dict[str, CheckObservation],
        Field(description="Named check observations keyed by component:metric."),
    ]


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


def _observation(
    observed_value: float | str,
    observed_unit: str,
    *,
    now: str,
    status: Literal["pass", "fail"] = "pass",
    output: str | None = None,
) -> CheckObservation:
    return CheckObservation(
        component_type="datastore",
        observed_value=observed_value,
        observed_unit=observed_unit,
        status=status,
        time=now,
        output=output,
    )


def _failed(unit: str, *, now: str, exc: Exception) -> CheckObservation:
    return _observation("unknown", unit, now=now, status="fail", output=str(exc))


@router.get(
    "/health",
    summary="Liveness check",
    operation_id="get_health",
    response_class=HealthJSONResponse,
)
def get_health() -> HealthResponse:
    """Report that the process is up and able to accept requests."""
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
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
) -> ReadyResponse:
    """Report readiness by verifying all required dependencies are reachable."""
    now = datetime.now(UTC).isoformat()
    checks: dict[str, CheckObservation] = {}

    # database:responseTime + database:version share a single session/connection.
    # Broad Exception here: asyncpg pool-connect failures (e.g. ConnectionRefusedError)
    # propagate as raw OSError — SQLAlchemy only wraps errors at statement-execution
    # time, not at pool-connect time. Catching only SQLAlchemyError would let those
    # surface as unhandled 500s instead of a graceful 503.
    try:
        async with session_factory() as session:
            t0 = time.perf_counter()
            await session.execute(text("SELECT 1"))
            elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)

            row = await session.execute(text("SHOW server_version"))
            db_version: str = row.scalar_one()

        checks["database:responseTime"] = _observation(elapsed_ms, "ms", now=now)
        checks["database:version"] = _observation(db_version, "version", now=now)
    except Exception as exc:
        checks["database:responseTime"] = _failed("ms", now=now, exc=exc)
        checks["database:version"] = _failed("version", now=now, exc=exc)

    # database:migrationRevision — isolated try/except, same broad-catch rationale.
    code_revisions = code_head_revisions()
    code_rev_str = ", ".join(sorted(code_revisions)) if code_revisions else "none"
    try:
        db_revisions = await db_current_revisions(session_factory)
        db_rev_str = ", ".join(sorted(db_revisions)) if db_revisions else "none"
        migration_ok = set(db_revisions) == set(code_revisions)
        mismatch = f"database at {db_rev_str}, code expects {code_rev_str}"
        checks["database:migrationRevision"] = _observation(
            db_rev_str,
            "revision",
            now=now,
            status="pass" if migration_ok else "fail",
            output=None if migration_ok else mismatch,
        )
    except Exception as exc:
        checks["database:migrationRevision"] = _failed("revision", now=now, exc=exc)

    # database:poolUtilization — pure in-process introspection, no query.
    # Checked after the above sessions close so checkedout() reflects idle state.
    pool_obj = cast(QueuePool, get_engine().pool)
    checkedout = pool_obj.checkedout()
    pool_size = pool_obj.size()
    pool_saturated = pool_size > 0 and checkedout >= pool_size
    utilization = round(checkedout / pool_size * 100, 2) if pool_size > 0 else 0.0
    pool_output: str | None = (
        f"{checkedout}/{pool_size} connections checked out, 0 available"
        if pool_saturated
        else None
    )
    checks["database:poolUtilization"] = _observation(
        utilization,
        "percent",
        now=now,
        status="fail" if pool_saturated else "pass",
        output=pool_output,
    )

    overall: Literal["pass", "fail"] = (
        "fail" if any(c.status == "fail" for c in checks.values()) else "pass"
    )
    if overall == "fail":
        response.status_code = 503

    return ReadyResponse(status=overall, checks=checks)


@router.get(
    "/version",
    summary="Application version",
    operation_id="get_version",
    response_model_exclude_none=True,
)
def get_version(
    app_info: Annotated[AppInfo, Depends(load_app_info)],
) -> VersionResponse:
    """Report the project version and build provenance of the running instance."""
    build = app_info.build
    return VersionResponse(
        name=app_info.name,
        current_version=app_info.version,
        commit_sha=build.commit_sha,
        short_sha=build.short_sha,
        branch=build.branch,
        dirty=build.dirty,
        build_timestamp=build.build_timestamp,
        migration_head=list(code_head_revisions()),
    )
