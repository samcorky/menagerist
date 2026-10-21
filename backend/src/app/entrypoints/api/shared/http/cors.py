"""What a cross-origin page may ask of the API.

Credentials are off, so these never let another site use someone's session; they only
keep a preflight to what the API serves. `Authorization` joins the request headers when
API tokens arrive.
"""

CORS_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"]

# Starlette adds the safelisted headers (`Accept`, `Accept-Language`, `Content-Language`
# and `Content-Type`) itself; `Content-Type` is listed for clarity.
CORS_REQUEST_HEADERS = [
    "Content-Type",
    "If-Match",
    "If-None-Match",
    "If-Modified-Since",
    "Request-Id",
]

# `ETag` is not CORS-safelisted, so a cross-origin client cannot read it unless listed.
CORS_RESPONSE_HEADERS = [
    "App-Version",
    "Total-Count",
    "Link",
    "ETag",
    "Request-Id",
    "Retry-After",
]

CORS_MAX_AGE_SECONDS = 600
