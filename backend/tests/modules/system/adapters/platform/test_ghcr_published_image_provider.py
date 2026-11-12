import json

import pytest

from app.modules.system.adapters.platform.ghcr_published_image_provider import (
    REVISION_LABEL,
    GhcrPublishedImageProvider,
    running_architecture,
)
from app.modules.system.domain.release import CheckFailure, ImageRef, ReleaseCheckError
from app.shared_kernel.outbound_http import (
    InMemoryOutboundHttp,
    OutboundFailure,
    OutboundHttpError,
    OutboundResponse,
)

IMAGE = ImageRef(repository="samcorky/menagerist", tag="edge")
REVISION = "c75e612aa58ef51db1ce97032320be85dafa143a"
CONFIG_DIGEST = "sha256:" + "a" * 64
AMD64_DIGEST = "sha256:" + "b" * 64
ARM64_DIGEST = "sha256:" + "c" * 64

TOKEN_URL = "https://ghcr.io/token"
TAG_URL = "https://ghcr.io/v2/samcorky/menagerist/manifests/edge"


def manifest_url(digest: str) -> str:
    """The address a manifest is fetched from by digest."""
    return f"https://ghcr.io/v2/samcorky/menagerist/manifests/{digest}"


def blob_url(digest: str) -> str:
    """The address a config blob is fetched from."""
    return f"https://ghcr.io/v2/samcorky/menagerist/blobs/{digest}"


def json_reply(body: object, *, status: int = 200, url: str = "") -> OutboundResponse:
    """A JSON response the in-memory client can serve."""
    return OutboundResponse(
        url=url, status=status, headers={}, body=json.dumps(body).encode()
    )


def index(*, architectures: tuple[str, ...] = ("amd64", "arm64")) -> dict[str, object]:
    """An image index listing one manifest per architecture."""
    digests = {"amd64": AMD64_DIGEST, "arm64": ARM64_DIGEST}
    return {
        "mediaType": "application/vnd.oci.image.index.v1+json",
        "manifests": [
            {
                "digest": digests.get(architecture, AMD64_DIGEST),
                "platform": {"architecture": architecture, "os": "linux"},
            }
            for architecture in architectures
        ],
    }


def serving(
    *,
    revision: str | None = REVISION,
    architecture: str = "amd64",
    index_body: object | None = None,
) -> tuple[GhcrPublishedImageProvider, InMemoryOutboundHttp]:
    """A provider whose whole four-step read is answered in memory."""
    http = InMemoryOutboundHttp()
    http.reply(TOKEN_URL, json_reply({"token": "anonymous-token"}))
    http.reply(TAG_URL, json_reply(index() if index_body is None else index_body))
    labels = {} if revision is None else {REVISION_LABEL: revision}
    for digest in (AMD64_DIGEST, ARM64_DIGEST):
        http.reply(
            manifest_url(digest), json_reply({"config": {"digest": CONFIG_DIGEST}})
        )
    http.reply(blob_url(CONFIG_DIGEST), json_reply({"config": {"Labels": labels}}))
    return GhcrPublishedImageProvider(http, architecture=architecture), http


async def test_the_revision_label_is_read_from_the_config_blob() -> None:
    """The revision label is read from the config blob."""
    provider, http = serving()

    assert await provider.revision(IMAGE) == REVISION
    # Token, index, platform manifest, config blob: the four reads a registry needs.
    assert [request.url for request in http.requests] == [
        TOKEN_URL,
        TAG_URL,
        manifest_url(AMD64_DIGEST),
        blob_url(CONFIG_DIGEST),
    ]


async def test_the_token_is_requested_for_pull_only_and_then_sent() -> None:
    """The token is requested for pull only and then sent."""
    provider, http = serving()

    await provider.revision(IMAGE)

    token_request = http.requests[0]
    assert token_request.params["scope"] == "repository:samcorky/menagerist:pull"
    assert "Authorization" not in token_request.headers
    # Every later read carries the token it was just issued.
    for request in http.requests[1:]:
        assert request.headers["Authorization"] == "Bearer anonymous-token"


async def test_the_manifest_for_the_running_architecture_is_chosen() -> None:
    """The manifest for the running architecture is chosen."""
    provider, http = serving(architecture="arm64")

    await provider.revision(IMAGE)

    assert manifest_url(ARM64_DIGEST) in [request.url for request in http.requests]


async def test_an_attestation_entry_is_never_mistaken_for_the_image() -> None:
    """An attestation rides in the index with an unknown platform; it is skipped."""
    body = {
        "manifests": [
            {
                "digest": "sha256:" + "d" * 64,
                "platform": {"architecture": "unknown", "os": "unknown"},
            },
            {
                "digest": AMD64_DIGEST,
                "platform": {"architecture": "amd64", "os": "linux"},
            },
        ]
    }
    provider, http = serving(index_body=body)

    assert await provider.revision(IMAGE) == REVISION
    assert manifest_url(AMD64_DIGEST) in [request.url for request in http.requests]


async def test_an_unpublished_architecture_falls_back_to_a_listed_manifest() -> None:
    """The revision is the same whichever platform built it, so any manifest will do."""
    provider, _ = serving(architecture="riscv64")

    assert await provider.revision(IMAGE) == REVISION


async def test_a_single_platform_image_needs_no_second_manifest_read() -> None:
    """A single-platform image needs no second manifest read."""
    provider, http = serving(index_body={"config": {"digest": CONFIG_DIGEST}})

    assert await provider.revision(IMAGE) == REVISION
    assert [request.url for request in http.requests] == [
        TOKEN_URL,
        TAG_URL,
        blob_url(CONFIG_DIGEST),
    ]


async def test_an_image_without_the_label_reports_no_revision() -> None:
    """An image without the label reports no revision, which is not a failure."""
    provider, _ = serving(revision=None)

    assert await provider.revision(IMAGE) is None


async def test_a_blank_label_reports_no_revision() -> None:
    """A blank label reports no revision."""
    provider, _ = serving(revision="   ")

    assert await provider.revision(IMAGE) is None


async def test_a_label_in_the_legacy_container_config_is_still_found() -> None:
    """A label in the legacy container_config is still found."""
    http = InMemoryOutboundHttp()
    http.reply(TOKEN_URL, json_reply({"token": "t"}))
    http.reply(TAG_URL, json_reply(index(architectures=("amd64",))))
    http.reply(
        manifest_url(AMD64_DIGEST), json_reply({"config": {"digest": CONFIG_DIGEST}})
    )
    http.reply(
        blob_url(CONFIG_DIGEST),
        json_reply({"container_config": {"Labels": {REVISION_LABEL: REVISION}}}),
    )

    provider = GhcrPublishedImageProvider(http, architecture="amd64")

    assert await provider.revision(IMAGE) == REVISION


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (404, CheckFailure.NOT_FOUND),
        (401, CheckFailure.NOT_FOUND),
        (403, CheckFailure.NOT_FOUND),
        (429, CheckFailure.RATE_LIMITED),
        (500, CheckFailure.NETWORK),
        (503, CheckFailure.NETWORK),
        (204, CheckFailure.BAD_RESPONSE),
    ],
)
async def test_a_registry_status_maps_onto_a_check_failure(
    status: int, expected: CheckFailure
) -> None:
    """A registry status maps onto a check failure."""
    http = InMemoryOutboundHttp()
    http.reply(TOKEN_URL, json_reply({"token": "t"}, status=status))
    provider = GhcrPublishedImageProvider(http, architecture="amd64")

    with pytest.raises(ReleaseCheckError) as raised:
        await provider.revision(IMAGE)

    assert raised.value.failure is expected


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (OutboundFailure.TIMEOUT, CheckFailure.TIMEOUT),
        (OutboundFailure.TOO_LARGE, CheckFailure.BAD_RESPONSE),
        (OutboundFailure.INVALID_URL, CheckFailure.BAD_RESPONSE),
        (OutboundFailure.NETWORK, CheckFailure.NETWORK),
        (OutboundFailure.BLOCKED_ADDRESS, CheckFailure.NETWORK),
    ],
)
async def test_an_outbound_failure_maps_onto_a_check_failure(
    failure: OutboundFailure, expected: CheckFailure
) -> None:
    """An outbound failure maps onto a check failure."""
    http = InMemoryOutboundHttp()
    http.reply(TOKEN_URL, OutboundHttpError(failure))
    provider = GhcrPublishedImageProvider(http, architecture="amd64")

    with pytest.raises(ReleaseCheckError) as raised:
        await provider.revision(IMAGE)

    assert raised.value.failure is expected


@pytest.mark.parametrize(
    "body", [b"not json", b"[]", b'"text"', b"123"], ids=["invalid", "list", "str", "n"]
)
async def test_a_reply_that_is_not_an_object_is_a_bad_response(body: bytes) -> None:
    """A reply that is not an object is a bad response."""
    http = InMemoryOutboundHttp()
    http.reply(TOKEN_URL, OutboundResponse(url=TOKEN_URL, status=200, body=body))
    provider = GhcrPublishedImageProvider(http, architecture="amd64")

    with pytest.raises(ReleaseCheckError) as raised:
        await provider.revision(IMAGE)

    assert raised.value.failure is CheckFailure.BAD_RESPONSE


@pytest.mark.parametrize("token", [None, "", 7], ids=["missing", "blank", "number"])
async def test_a_reply_with_no_usable_token_is_a_bad_response(token: object) -> None:
    """A reply with no usable token is a bad response."""
    http = InMemoryOutboundHttp()
    http.reply(TOKEN_URL, json_reply({} if token is None else {"token": token}))
    provider = GhcrPublishedImageProvider(http, architecture="amd64")

    with pytest.raises(ReleaseCheckError) as raised:
        await provider.revision(IMAGE)

    assert raised.value.failure is CheckFailure.BAD_RESPONSE


async def test_a_manifest_with_no_config_digest_reports_no_revision() -> None:
    """A manifest with no config digest reports no revision."""
    http = InMemoryOutboundHttp()
    http.reply(TOKEN_URL, json_reply({"token": "t"}))
    http.reply(TAG_URL, json_reply(index(architectures=("amd64",))))
    http.reply(manifest_url(AMD64_DIGEST), json_reply({"layers": []}))
    provider = GhcrPublishedImageProvider(http, architecture="amd64")

    assert await provider.revision(IMAGE) is None


async def test_the_reads_are_bounded_so_a_huge_blob_cannot_fill_memory() -> None:
    """The reads are bounded so a huge blob cannot fill memory."""
    provider, http = serving()

    await provider.revision(IMAGE)

    assert all(request.max_bytes is not None for request in http.requests)


def test_the_running_architecture_is_named_the_way_an_index_names_it() -> None:
    """The running architecture is named the way an index names it."""
    assert running_architecture() in {"amd64", "arm64"}
