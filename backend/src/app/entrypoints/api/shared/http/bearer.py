from starlette.requests import Request  # noqa: TC002


def bearer_token(request: Request) -> str | None:
    """Return the value of an `Authorization: Bearer` header, else `None`.

    The scheme is case-insensitive. Any other scheme (a proxy's `Basic`) is not a
    token credential and gives `None`. A bearer header with nothing after it gives
    `""`, which no token matches, so the request is refused rather than ignored.
    """
    header = request.headers.get("authorization")
    if header is None:
        return None
    scheme, _, value = header.strip().partition(" ")
    if scheme.lower() != "bearer":
        return None
    return value.strip()
