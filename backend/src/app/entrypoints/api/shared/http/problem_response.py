from http import HTTPStatus
from typing import TYPE_CHECKING, Any

import structlog
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.platform.database import DATABASE_OUTAGE_ERRORS
from app.shared_kernel.errors import (
    ConflictError,
    DomainError,
    ForbiddenError,
    MenageristError,
    NotFoundError,
    TooManyRequestsError,
    UnauthenticatedError,
    UnavailableError,
    ValidationError,
)
from app.shared_kernel.outbound_http import OutboundHttpError

if TYPE_CHECKING:
    from fastapi import FastAPI, Request
    from starlette.responses import Response

logger = structlog.get_logger()

_STATUS_BY_DOMAIN_ERROR: dict[type[DomainError], int] = {
    NotFoundError: 404,
    ConflictError: 409,
    ValidationError: 400,
    ForbiddenError: 403,
    UnauthenticatedError: 401,
    TooManyRequestsError: 429,
    UnavailableError: 503,
}

# Most specific first: a `MenageristError` that is not a domain rule is the
# server's failure unless its type says otherwise.
_STATUS_BY_MENAGERIST_ERROR: dict[type[MenageristError], int] = {
    OutboundHttpError: 502,
    MenageristError: 500,
}


class _Problem(BaseModel):
    """The RFC 9457 fields every problem body carries."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "type": "about:blank",
                    "title": "NotFoundError",
                    "status": 404,
                    "instance": "https://menagerist.example/api/v1/nodes",
                }
            ]
        }
    )

    type: str = Field(
        description=(
            "A URI naming the kind of problem; `about:blank` when the status"
            + " says it all."
        )
    )
    title: str = Field(
        description="The kind of problem, the same for every occurrence."
    )
    status: int = Field(description="The HTTP status code.")
    instance: str = Field(description="The URL of the request that failed.")


class ProblemDetail(_Problem):
    """RFC 9457 `application/problem+json` body every `DomainError` maps to."""

    # Every response carries its own example, so this one only shows in the
    # schema list; a pinned test fails any response that would borrow it.
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "type": "about:blank",
                    "title": "ValidationError",
                    "status": 400,
                    "detail": "A value is not acceptable.",
                    "instance": "https://menagerist.example/api/v1/nodes",
                }
            ]
        }
    )

    detail: str = Field(description="What went wrong, for a person to read.")
    errors: list[dict[str, str]] | None = Field(
        default=None,
        description="For a validation error, the offending fields and what is wrong.",
    )


class FieldIssue(BaseModel):
    """One field of a request that could not be accepted."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"type": "missing", "loc": ["body", "name"], "msg": "Field required"}
            ]
        }
    )

    type: str = Field(description="Machine-readable kind of failure.")
    loc: list[str | int] = Field(
        description=(
            "Where the value is: `body`, `query`, `path` or `header`, then the"
            + " field names and indexes."
        )
    )
    msg: str = Field(description="What is wrong, for a person to read.")


class ValidationProblem(_Problem):
    """An RFC 9457 problem for a request that could not be parsed.

    `detail` has one entry per offending field, in FastAPI's shape, which the
    web client reads.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "type": "about:blank",
                    "title": "Unprocessable Content",
                    "status": 422,
                    "detail": [
                        {
                            "type": "missing",
                            "loc": ["body", "name"],
                            "msg": "Field required",
                        }
                    ],
                    "instance": "https://menagerist.example/api/v1/nodes",
                }
            ]
        }
    )

    detail: list[FieldIssue] = Field(
        description="One entry per field that could not be accepted."
    )


# Swapped for a URL that fits each route when the OpenAPI document is built.
INSTANCE_PLACEHOLDER = "{instance}"
PROBLEM_JSON = "application/problem+json"
_PROBLEM_SCHEMA_REF = {"$ref": "#/components/schemas/ProblemDetail"}


def problem_example(
    status: int, title: str, detail: str, *, type_: str = "about:blank"
) -> dict[str, Any]:
    """Build an example body shaped like the problem response the app sends."""
    return {
        "type": type_,
        "title": title,
        "status": status,
        "detail": detail,
        "instance": INSTANCE_PLACEHOLDER,
    }


def problem_response(
    status: int,
    description: str,
    title: str,
    detail: str,
    *,
    type_: str = "about:blank",
) -> dict[int | str, dict[str, Any]]:
    """Build an OpenAPI responses entry with one problem+json example."""
    return {
        status: {
            "description": description,
            "content": {
                PROBLEM_JSON: {
                    "schema": _PROBLEM_SCHEMA_REF,
                    "example": problem_example(status, title, detail, type_=type_),
                }
            },
        }
    }


PRECONDITION_FAILED_TITLE = "PreconditionFailedError"
PRECONDITION_FAILED_DETAIL = (
    "The resource has changed since you read it. Fetch it again for its current ETag."
)


def precondition_failed_response(instance: str, etag: str) -> JSONResponse:
    """Answer a failed `If-Match` or `If-Unmodified-Since` with 412 and the ETag."""
    return JSONResponse(
        status_code=412,
        media_type=PROBLEM_JSON,
        content={
            "type": "about:blank",
            "title": PRECONDITION_FAILED_TITLE,
            "status": 412,
            "detail": PRECONDITION_FAILED_DETAIL,
            "instance": instance,
        },
        headers={"ETag": etag},
    )


def _status_for(error_type: type[DomainError]) -> int:
    return next(
        status
        for base, status in _STATUS_BY_DOMAIN_ERROR.items()
        if issubclass(error_type, base)
    )


_BASE_DESCRIPTIONS: dict[type[DomainError], str] = {
    ValidationError: "A value is not acceptable; the detail says which.",
    ForbiddenError: "Signed in, but not permitted to do this.",
    ConflictError: "The request conflicts with the current state.",
    NotFoundError: "The resource does not exist, or is not yours.",
}


def _describe(error_type: type[DomainError]) -> str:
    """Turn the error's docstring into a response description."""
    if error_type in _BASE_DESCRIPTIONS:
        return _BASE_DESCRIPTIONS[error_type]
    text = (error_type.__doc__ or error_type.__name__).strip().split("\n")[0]
    return text.replace("Raised when ", "Returned when ", 1)


def error_response(
    error_type: type[DomainError], *, detail: str, description: str | None = None
) -> dict[int | str, dict[str, Any]]:
    """Build an OpenAPI responses entry documenting error_type for a route.

    The example carries the error's real `title` (its class name) and `type`;
    its `instance` is filled in per route when the OpenAPI document is built.
    """
    return problem_response(
        _status_for(error_type),
        description or _describe(error_type),
        error_type.__name__,
        detail,
        type_=error_type.problem_type,
    )


_INTERNAL_ERROR_DETAIL = "An unexpected error occurred."


def _status_for_menagerist_error(error_type: type[Exception]) -> int:
    return next(
        status
        for base, status in _STATUS_BY_MENAGERIST_ERROR.items()
        if issubclass(error_type, base)
    )


def _internal_error_response(
    request: Request,
    exc: Exception,
    event: str,
    *,
    status_code: int = 500,
    deliberate: bool = False,
) -> JSONResponse:
    """Answer a server-side failure without the exception text.

    The text may hold secrets or paths, so it is logged, not sent. A failure we
    raised on purpose is a warning; anything else is a bug (error).
    """
    log = logger.warning if deliberate else logger.error
    log(event, exc_info=exc, method=request.method, path=request.url.path)
    return JSONResponse(
        status_code=status_code,
        media_type="application/problem+json",
        content={
            "type": "about:blank",
            "title": HTTPStatus(status_code).phrase,
            "status": status_code,
            "detail": _INTERNAL_ERROR_DETAIL,
            "instance": str(request.url),
        },
    )


def _menagerist_response(request: Request, exc: Exception) -> JSONResponse:
    """Answer a `MenageristError` that is not a domain rule: not a bug.

    Covers `InfrastructureError` and any other error raised on purpose, so it is
    logged as a warning; only a non-Menagerist exception is logged as an error.
    """
    status_code = _status_for_menagerist_error(type(exc))
    return _internal_error_response(
        request, exc, "menagerist error", status_code=status_code, deliberate=True
    )


def _problem_response(request: Request, exc: Exception) -> JSONResponse:
    """Translate a `DomainError` into an RFC 9457 problem+json response.

    Also handle non-domain exceptions (fallback) so the catch-all Exception
    handler doesn't trigger an assertion when a framework or other error
    occurs.
    """
    # Anything else is a 500; its text may hold secrets, so it is logged, not sent.
    if not isinstance(exc, DomainError):
        return _internal_error_response(request, exc, "unhandled exception")

    status_code = next(
        status
        for error_type, status in _STATUS_BY_DOMAIN_ERROR.items()
        if isinstance(exc, error_type)
    )
    content: dict[str, Any] = {
        "type": exc.problem_type,
        "title": type(exc).__name__,
        "status": status_code,
        "detail": str(exc),
        "instance": str(request.url),
    }
    if hasattr(exc, "validation_errors") and exc.validation_errors:
        content["errors"] = exc.validation_errors
    headers: dict[str, str] = {}
    if isinstance(exc, TooManyRequestsError) and exc.retry_after is not None:
        headers["Retry-After"] = str(exc.retry_after)
    return JSONResponse(
        status_code=status_code,
        media_type="application/problem+json",
        content=content,
        headers=headers,
    )


_DATABASE_RETRY_AFTER = 5


def _database_unavailable_response(request: Request, exc: Exception) -> JSONResponse:
    """Answer a lost database with 503 rather than an unexpected-error traceback."""
    logger.warning(
        "database unavailable",
        error=type(exc).__name__,
        method=request.method,
        path=request.url.path,
    )
    return JSONResponse(
        status_code=503,
        media_type=PROBLEM_JSON,
        content={
            "type": "about:blank",
            "title": "Service Unavailable",
            "status": 503,
            "detail": "The service is temporarily unavailable. Try again shortly.",
            "instance": str(request.url),
        },
        headers={"Retry-After": str(_DATABASE_RETRY_AFTER)},
    )


def _validation_response(request: Request, exc: Exception) -> JSONResponse:
    """Answer a malformed request with 422, without echoing what was submitted.

    Keeps FastAPI's `detail: [{type, loc, msg}]` shape (the web client reads
    `msg`) but drops each error's `input` and `ctx`, which hold the submitted
    values (passwords included).
    """
    assert isinstance(exc, RequestValidationError)
    return JSONResponse(
        status_code=422,
        media_type="application/problem+json",
        content={
            "type": "about:blank",
            "title": "Unprocessable Content",
            "status": 422,
            "detail": [
                {"type": e["type"], "loc": list(e["loc"]), "msg": e["msg"]}
                for e in exc.errors()
            ],
            "instance": str(request.url),
        },
    )


_ROUTING_PROBLEMS = {
    404: ("NotFoundError", "No such API endpoint."),
    405: ("MethodNotAllowedError", "This endpoint does not accept {method}."),
}


async def _routing_response(request: Request, exc: Exception) -> Response:
    """Answer an unknown API path or wrong method with a problem response.

    Anything outside `/api`, or any other status, keeps the framework default
    so the SPA fallback and static files behave as before.
    """
    assert isinstance(exc, StarletteHTTPException)
    path = request.url.path
    if (path != "/api" and not path.startswith("/api/")) or (
        exc.status_code not in _ROUTING_PROBLEMS
    ):
        return await http_exception_handler(request, exc)
    title, detail = _ROUTING_PROBLEMS[exc.status_code]
    return JSONResponse(
        status_code=exc.status_code,
        media_type=PROBLEM_JSON,
        content={
            "type": "about:blank",
            "title": title,
            "status": exc.status_code,
            "detail": detail.format(method=request.method),
            "instance": str(request.url),
        },
        headers=exc.headers,
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Map domain errors to RFC 9457 problem responses."""
    app.add_exception_handler(StarletteHTTPException, _routing_response)
    app.add_exception_handler(RequestValidationError, _validation_response)
    for error_type in _STATUS_BY_DOMAIN_ERROR:
        app.add_exception_handler(error_type, _problem_response)

    for outage_type in DATABASE_OUTAGE_ERRORS:
        app.add_exception_handler(outage_type, _database_unavailable_response)

    for menagerist_type in _STATUS_BY_MENAGERIST_ERROR:
        app.add_exception_handler(menagerist_type, _menagerist_response)

    # Catch-all for any unhandled exception, returning a 500 problem response.
    app.add_exception_handler(Exception, _problem_response)
