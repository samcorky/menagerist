"""Reads the revision a published image was built from, anonymously, from GHCR.

Four reads, because that is how a registry stores the answer: an anonymous pull
token, the image index, the manifest for the running platform, then the config blob
carrying `org.opencontainers.image.revision`. A moving tag such as `edge` cannot be
baked into the build, so it is read here each time; the revision label cannot move.
"""

import json
import platform
from typing import TYPE_CHECKING

from app.modules.system.domain.release import CheckFailure, ImageRef, ReleaseCheckError
from app.shared_kernel.outbound_http import OutboundFailure, OutboundHttpError

if TYPE_CHECKING:
    from collections.abc import Mapping

    from app.shared_kernel.outbound_http import OutboundHttp, OutboundResponse

REGISTRY_HOST = "ghcr.io"
TOKEN_HOST = "ghcr.io"
REVISION_LABEL = "org.opencontainers.image.revision"

# An index lists one manifest per platform; a manifest and a config blob are small.
MAX_DOCUMENT_BYTES = 256 * 1024

_INDEX_TYPES = (
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
)
_MANIFEST_TYPES = (
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
)
_ACCEPT = ", ".join((*_INDEX_TYPES, *_MANIFEST_TYPES))

# Go's names for the architectures the image is published for.
_ARCHITECTURES = {
    "x86_64": "amd64",
    "amd64": "amd64",
    "aarch64": "arm64",
    "arm64": "arm64",
}

_FAILURES = {
    OutboundFailure.TIMEOUT: CheckFailure.TIMEOUT,
    OutboundFailure.TOO_LARGE: CheckFailure.BAD_RESPONSE,
    OutboundFailure.INVALID_URL: CheckFailure.BAD_RESPONSE,
}


def running_architecture() -> str:
    """The architecture of the running container, as an image index names it."""
    return _ARCHITECTURES.get(platform.machine().lower(), "amd64")


class GhcrPublishedImageProvider:
    """Reads one image's revision label; sends no credentials of its own."""

    def __init__(self, http: OutboundHttp, *, architecture: str | None = None) -> None:
        self._http = http
        self._architecture = architecture or running_architecture()

    async def revision(self, image: ImageRef) -> str | None:
        """Return the revision `image` was built from, or `None` when it has none."""
        token = await self._token(image)
        index = self._document(
            await self._get(self._manifest_url(image, image.tag), token)
        )
        digest = self._platform_digest(index)
        if digest is None:
            manifest = index
        else:
            url = self._manifest_url(image, digest)
            manifest = self._document(await self._get(url, token))
        config_digest = self._config_digest(manifest)
        if config_digest is None:
            return None
        blob = await self._get(self._blob_url(image, config_digest), token)
        return self._label(self._document(blob))

    async def _token(self, image: ImageRef) -> str:
        """An anonymous pull token, which GHCR issues for a public image."""
        response = await self._get(
            f"https://{TOKEN_HOST}/token",
            None,
            params={
                "service": REGISTRY_HOST,
                "scope": f"repository:{image.repository}:pull",
            },
        )
        token = self._document(response).get("token")
        if not isinstance(token, str) or not token:
            raise ReleaseCheckError(CheckFailure.BAD_RESPONSE)
        return token

    @staticmethod
    def _manifest_url(image: ImageRef, reference: str) -> str:
        return f"https://{REGISTRY_HOST}/v2/{image.repository}/manifests/{reference}"

    @staticmethod
    def _blob_url(image: ImageRef, digest: str) -> str:
        return f"https://{REGISTRY_HOST}/v2/{image.repository}/blobs/{digest}"

    async def _get(
        self,
        url: str,
        token: str | None,
        *,
        params: Mapping[str, str | int] | None = None,
    ) -> OutboundResponse:
        headers = {"Accept": _ACCEPT}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        try:
            response = await self._http.get(
                url, headers=headers, params=params, max_bytes=MAX_DOCUMENT_BYTES
            )
        except OutboundHttpError as exc:
            raise ReleaseCheckError(
                _FAILURES.get(exc.failure, CheckFailure.NETWORK)
            ) from exc
        self._check_status(response)
        return response

    @staticmethod
    def _check_status(response: OutboundResponse) -> None:
        status = response.status
        if status == 404:
            raise ReleaseCheckError(CheckFailure.NOT_FOUND)
        if status == 429:
            raise ReleaseCheckError(CheckFailure.RATE_LIMITED)
        # An anonymous read of a private or renamed image is a 401/403; there is
        # nothing to retry, so it is reported the same way as a missing image.
        if status in {401, 403}:
            raise ReleaseCheckError(CheckFailure.NOT_FOUND)
        if status >= 500:
            raise ReleaseCheckError(CheckFailure.NETWORK)
        if status != 200:
            raise ReleaseCheckError(CheckFailure.BAD_RESPONSE)

    @staticmethod
    def _document(response: OutboundResponse) -> Mapping[str, object]:
        try:
            payload = json.loads(response.body)
        except ValueError as exc:
            raise ReleaseCheckError(CheckFailure.BAD_RESPONSE) from exc
        if not isinstance(payload, dict):
            raise ReleaseCheckError(CheckFailure.BAD_RESPONSE)
        return payload

    def _platform_digest(self, index: Mapping[str, object]) -> str | None:
        """The running platform's digest, or `None` for a single-platform image."""
        manifests = index.get("manifests")
        if not isinstance(manifests, list):
            return None
        fallback: str | None = None
        for entry in manifests:
            if not isinstance(entry, dict):
                continue
            digest = entry.get("digest")
            if not isinstance(digest, str) or not digest:
                continue
            described = entry.get("platform")
            described = described if isinstance(described, dict) else {}
            # An attestation rides in the index with no usable platform; skip it.
            if described.get("architecture") == "unknown":
                continue
            if described.get("architecture") == self._architecture:
                return digest
            fallback = fallback or digest
        # The running platform is not published: any manifest still names the build.
        return fallback

    @staticmethod
    def _config_digest(manifest: Mapping[str, object]) -> str | None:
        config = manifest.get("config")
        if not isinstance(config, dict):
            return None
        digest = config.get("digest")
        return digest if isinstance(digest, str) and digest else None

    @staticmethod
    def _label(config: Mapping[str, object]) -> str | None:
        """The revision label, read from either place a config may carry labels."""
        for key in ("config", "container_config"):
            section = config.get(key)
            if not isinstance(section, dict):
                continue
            labels = section.get("Labels")
            if not isinstance(labels, dict):
                continue
            revision = labels.get(REVISION_LABEL)
            if isinstance(revision, str) and revision.strip():
                return revision.strip()
        return None
