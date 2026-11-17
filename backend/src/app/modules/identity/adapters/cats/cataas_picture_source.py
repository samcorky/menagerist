import secrets
from http import HTTPStatus
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

import structlog

from app.modules.identity.domain.avatar import MAX_AVATAR_BYTES
from app.modules.identity.domain.errors import CatServiceUnavailableError
from app.shared_kernel.outbound_http import OutboundHttpError

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.shared_kernel.outbound_http import OutboundHttp, OutboundResponse

logger = structlog.get_logger()

_UNAVAILABLE = "The cat service is not available."


class CataasPictureSource:
    """`CatPictureSource` backed by a cataas-compatible service, read server-side.

    Only the reply's bytes are returned; they are decoded and re-encoded by the
    avatar pipeline like any upload, so nothing the service sends is served as is.
    """

    def __init__(
        self,
        http: OutboundHttp,
        base_url: str,
        *,
        seed: Callable[[], str] = lambda: secrets.token_hex(8),
    ) -> None:
        self._http = http
        # A fresh random seed per press gives a new cat each time and sends nothing
        # that identifies the account.
        self._seed = seed
        self._base_url = base_url.rstrip("/")
        self._host = urlsplit(self._base_url).hostname

    async def fetch(self) -> bytes:
        """Ask the service's `/avatar/:seed` for one square cat.

        Raises:
            CatServiceUnavailableError: If the request fails, is redirected to
                another host, or the reply is not a non-empty image.
        """
        try:
            response = await self._http.get(
                f"{self._base_url}/avatar/{self._seed()}",
                headers={"Accept": "image/*"},
                max_bytes=MAX_AVATAR_BYTES,
                admin_configured=True,
            )
        except OutboundHttpError as error:
            logger.info("cat service unreachable", failure=error.failure.value)
            raise CatServiceUnavailableError(_UNAVAILABLE) from error
        if not self._usable(response):
            logger.info(
                "cat service reply unusable",
                status=response.status,
                content_type=response.headers.get("content-type"),
            )
            raise CatServiceUnavailableError(_UNAVAILABLE)
        return response.body

    def _usable(self, response: OutboundResponse) -> bool:
        content_type = response.headers.get("content-type", "")
        return (
            response.status == HTTPStatus.OK
            and content_type.lower().startswith("image/")
            and bool(response.body)
            and urlsplit(response.url).hostname == self._host
        )
