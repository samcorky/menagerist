from email.utils import formatdate, parsedate_to_datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datetime import datetime

    from starlette.requests import Request


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
        304: {"description": "Not Modified — condition matched; no body."},
    }


def conditional_patch_responses() -> dict[int | str, dict[str, Any]]:
    """OpenAPI docs for 412 Precondition Failed on conditional PATCH endpoints."""
    return {
        412: {
            "description": "Precondition Failed — conditional header check failed.",
            "headers": {
                "ETag": {
                    "description": "Current ETag of the resource.",
                    "schema": {"type": "string"},
                }
            },
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
