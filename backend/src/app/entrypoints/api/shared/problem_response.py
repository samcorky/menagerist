from typing import TYPE_CHECKING, Any

from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.shared_kernel.errors import (
    ConflictError,
    DomainError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)

if TYPE_CHECKING:
    from fastapi import FastAPI, Request

_STATUS_BY_ERROR: dict[type[DomainError], int] = {
    NotFoundError: 404,
    ConflictError: 409,
    ValidationError: 400,
    ForbiddenError: 403,
}


class ProblemDetail(BaseModel):
    """RFC 9457 `application/problem+json` body every `DomainError` maps to."""

    type: str
    title: str
    status: int
    detail: str
    instance: str


def _status_for(error_type: type[DomainError]) -> int:
    return next(
        status
        for base, status in _STATUS_BY_ERROR.items()
        if issubclass(error_type, base)
    )


def error_response(
    error_type: type[DomainError], *, detail: str
) -> dict[int | str, dict[str, Any]]:
    """Build an OpenAPI `responses` entry documenting `error_type` for a route.

    Lets a router declare, e.g., `responses=error_response(NodeNotFoundError,
    detail="Node <id> not found")` so Swagger shows the exact problem+json
    shape and status code `register_exception_handlers` actually returns for
    that error, without every router re-describing the RFC 9457 schema by hand.
    Merge multiple calls with `{**error_response(...), **error_response(...)}`
    for a route that can raise more than one kind of domain error.
    """
    status_code = _status_for(error_type)
    return {
        status_code: {
            "description": (error_type.__doc__ or error_type.__name__).strip(),
            "content": {
                "application/problem+json": {
                    "schema": ProblemDetail.model_json_schema(),
                    "example": {
                        "type": "about:blank",
                        "title": error_type.__name__,
                        "status": status_code,
                        "detail": detail,
                        "instance": "string",
                    },
                }
            },
        }
    }


def _problem_response(request: Request, exc: Exception) -> JSONResponse:
    """Translate a `DomainError` into an RFC 9457 problem+json response."""
    assert isinstance(exc, DomainError)
    status_code = next(
        status
        for error_type, status in _STATUS_BY_ERROR.items()
        if isinstance(exc, error_type)
    )
    return JSONResponse(
        status_code=status_code,
        media_type="application/problem+json",
        content={
            "type": "about:blank",
            "title": type(exc).__name__,
            "status": status_code,
            "detail": str(exc),
            "instance": str(request.url),
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Map every `shared_kernel.errors` domain error to a problem response.

    Registered once at the composition root so routers never carry a
    try/except - a module-specific error like `NodeNotFoundError(NotFoundError)`
    gets the correct HTTP status for free, purely from subclassing.
    """
    for error_type in _STATUS_BY_ERROR:
        app.add_exception_handler(error_type, _problem_response)
