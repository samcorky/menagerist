"""The one way Menagerist calls out to other web services.

Every module that needs the network depends on `OutboundHttp` rather than building
its own client, so the User-Agent, timeouts, size cap and address rules are decided
in one place (the adapter in `platform/outbound_http.py`) and cannot be forgotten by
a new caller. A caller maps `OutboundHttpError` onto its own domain failures.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol


class OutboundFailure(StrEnum):
    """Why a request could not be completed."""

    INVALID_URL = "invalid_url"
    BLOCKED_ADDRESS = "blocked_address"
    TOO_MANY_REDIRECTS = "too_many_redirects"
    TOO_LARGE = "too_large"
    TIMEOUT = "timeout"
    NETWORK = "network"


class OutboundHttpError(Exception):
    """A request was refused or failed before a usable response arrived."""

    def __init__(self, failure: OutboundFailure) -> None:
        super().__init__(failure.value)
        self.failure = failure


@dataclass(frozen=True, kw_only=True)
class OutboundResponse:
    """A completed response, whatever its status. Header names are lower-case."""

    url: str
    status: int
    headers: Mapping[str, str] = field(default_factory=dict)
    body: bytes = b""


class OutboundHttp(Protocol):
    """Reads from the public internet and nowhere else."""

    async def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, str | int] | None = None,
        max_bytes: int | None = None,
    ) -> OutboundResponse:
        """Fetch `url`, following redirects that stay on the public internet.

        `max_bytes` can only lower the instance's response cap. `response.url` is
        the address finally read, so a caller that trusts one host can check it.

        Raises:
            OutboundHttpError: If the address is refused, the reply is too large or
                too slow, or the connection fails.
        """
        ...


@dataclass(frozen=True, kw_only=True)
class RecordedRequest:
    """One request an in-memory client was asked to make."""

    url: str
    headers: Mapping[str, str]
    params: Mapping[str, str | int]
    max_bytes: int | None


class InMemoryOutboundHttp:
    """Serves canned responses by URL and records what was asked, touching no network.

    A URL with nothing registered fails as unreachable. Register an
    `OutboundHttpError` to make a URL fail the way the real client would.
    """

    def __init__(self) -> None:
        self._replies: dict[str, OutboundResponse | OutboundHttpError] = {}
        self.requests: list[RecordedRequest] = []

    def reply(self, url: str, reply: OutboundResponse | OutboundHttpError) -> None:
        """Answer requests for `url` with `reply`."""
        self._replies[url] = reply

    async def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, str | int] | None = None,
        max_bytes: int | None = None,
    ) -> OutboundResponse:
        """Return what was registered for `url`, enforcing `max_bytes` on its body."""
        self.requests.append(
            RecordedRequest(
                url=url,
                headers=dict(headers or {}),
                params=dict(params or {}),
                max_bytes=max_bytes,
            )
        )
        reply = self._replies.get(url)
        if reply is None:
            raise OutboundHttpError(OutboundFailure.NETWORK)
        if isinstance(reply, OutboundHttpError):
            raise reply
        if max_bytes is not None and len(reply.body) > max_bytes:
            raise OutboundHttpError(OutboundFailure.TOO_LARGE)
        return reply
