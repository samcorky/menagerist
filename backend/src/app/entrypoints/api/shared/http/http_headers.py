from email.utils import formatdate, parsedate_to_datetime
from typing import TYPE_CHECKING, Any

from .problem_response import (
    PRECONDITION_FAILED_DETAIL,
    PRECONDITION_FAILED_TITLE,
    problem_response,
)

if TYPE_CHECKING:
    from datetime import datetime

    from starlette.requests import Request
    from starlette.responses import Response

    from app.shared_kernel.paging import Cursor, Page


def http_date(dt: datetime) -> str:
    """Return an RFC 1123-formatted date string for the given datetime."""
    return formatdate(dt.timestamp(), usegmt=True)


def parse_http_date(value: str) -> datetime | None:
    """Parse an RFC 1123 date string, returning None if invalid."""
    try:
        return parsedate_to_datetime(value)
    except Exception:
        return None


def link_next_header(request: Request, after_cursor: str) -> str:
    """RFC 8288 Link header value pointing to the next page."""
    next_url = str(request.url.include_query_params(after=after_cursor))
    return f'<{next_url}>; rel="next"'


def set_next_link(
    request: Request, response: Response, next_cursor: Cursor | None
) -> None:
    """Point the `Link` header at the next page, when there is one."""
    if next_cursor is not None:
        response.headers["Link"] = link_next_header(request, next_cursor.encode())


# --- OpenAPI response-dict helpers (used in router decorator `responses=`) ---


def conditional_get_responses() -> dict[int | str, dict[str, Any]]:
    """OpenAPI docs for ETag/Last-Modified on 200 and 304 on GET endpoints."""
    return {
        200: {
            "headers": {
                "ETag": {
                    "description": "Opaque version token for conditional requests.",
                    "schema": {"type": "string"},
                },
                "Last-Modified": {
                    "description": "RFC 1123 last-modification date.",
                    "schema": {"type": "string"},
                },
                "Cache-Control": {"schema": {"type": "string"}},
            }
        },
        304: {
            "description": "Not modified: the condition matched, so there is no body."
        },
    }


def conditional_patch_responses() -> dict[int | str, dict[str, Any]]:
    """OpenAPI docs for 412 Precondition Failed on conditional PATCH endpoints."""
    responses = problem_response(
        412,
        "Precondition failed: `If-Match` or `If-Unmodified-Since` no longer matches.",
        PRECONDITION_FAILED_TITLE,
        PRECONDITION_FAILED_DETAIL,
    )
    return {
        412: {
            **responses[412],
            "headers": {
                "ETag": {
                    "description": "Current ETag of the resource.",
                    "schema": {"type": "string"},
                }
            },
        }
    }


def set_page_headers(request: Request, response: Response, page: Page[Any]) -> None:
    """Set `Link` to the next page, and `Total-Count` when the page knows the total."""
    set_next_link(request, response, page.next)
    if page.total is not None:
        response.headers["Total-Count"] = str(page.total)


def paging_responses(what: str) -> dict[int | str, dict[str, Any]]:
    """OpenAPI docs for the `Link` and `Total-Count` headers of a paged list.

    `what` names the rows counted, such as "API tokens".
    """
    return {
        200: {
            "headers": {
                "Link": {
                    "description": "RFC 8288 next-page cursor. Absent on last page.",
                    "schema": {"type": "string"},
                },
                "Total-Count": {
                    "description": f"{what} in total. Always exact.",
                    "schema": {"type": "integer"},
                },
            }
        }
    }


def link_header_responses() -> dict[int | str, dict[str, Any]]:
    """OpenAPI docs for the RFC 8288 Link header on list endpoints."""
    return {
        200: {
            "headers": {
                "Link": {
                    "description": "RFC 8288 next-page cursor. Absent on last page.",
                    "schema": {"type": "string"},
                }
            }
        }
    }
