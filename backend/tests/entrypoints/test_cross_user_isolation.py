"""Generated cross-user check: user B cannot reach user A's content on any route.

The real app is built over in-memory repositories for every module, user A is
seeded through the API with one of every kind of content, and then EVERY route in
the app's route table is called as user B with A's ids filled in by parameter
name. A route is either on the small explicit allow-list below (with a reason)
or it is generated here; one that is in neither fails the test, so a new route
cannot ship without isolation coverage. An allow-list entry for a route that no
longer exists fails too.
"""

import asyncio
import hashlib
import re
import uuid
from contextlib import ExitStack, nullcontext
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Annotated, Any

import pytest
from fastapi import Depends
from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.entrypoints.api.shared.access_guard import get_access_guard
from app.entrypoints.api.shared.authorisation import ADMIN_ONLY_ACTIONS
from app.entrypoints.api.shared.bridges.attach_target_access import (
    GraphAttachTargetAccess,
    get_attach_target_access,
)
from app.entrypoints.api.shared.bridges.choice_list_source import (
    PresetChoiceListSource,
    get_choice_list_source,
)
from app.entrypoints.api.shared.bridges.collection_conditions import (
    CollectionsDefinitions,
)
from app.entrypoints.api.shared.bridges.collection_definitions import (
    GraphDefinitionChecker,
    get_definition_checker,
)
from app.entrypoints.api.shared.bridges.collection_items import (
    GraphItemLookup,
    get_item_lookup,
)
from app.entrypoints.api.shared.bridges.collection_members import (
    CollectionsMembers,
    get_collection_members,
)
from app.entrypoints.api.shared.bridges.example_targets import (
    CollectionPackTarget,
    CoverPackTarget,
    GraphPackTarget,
    PresetPackTarget,
    build_in_memory_collections_repos,
    get_collection_pack_target,
    get_cover_pack_target,
    get_graph_pack_target,
    get_preset_pack_target,
    in_memory_collection_stores,
    in_memory_cover_stores,
    in_memory_graph_stores,
    in_memory_preset_stores,
)
from app.entrypoints.api.shared.dependencies import get_current_actor
from app.modules.collections.adapters.api.dependencies import (
    get_collections_repos,
    get_collections_uow,
)
from app.modules.collections.adapters.persistence.unit_of_work import (
    create_in_memory_collections_uow,
)
from app.modules.examples.adapters.api.dependencies import (
    get_example_repos,
    get_example_uow,
    get_pack_catalogue,
)
from app.modules.examples.adapters.covers.in_memory_cover_renderer import (
    InMemoryCoverRenderer,
)
from app.modules.examples.adapters.persistence.in_memory_installation_repository import (  # noqa: E501
    InMemoryInstallationRepository,
)
from app.modules.examples.adapters.platform.in_memory_pack_catalogue import (
    InMemoryPackCatalogue,
)
from app.modules.examples.domain.pack import (
    ExamplePack,
    PackConnection,
    PackItem,
    PackItemType,
    PackRelationshipType,
)
from app.modules.examples.ports.unit_of_work import ExampleRepos
from app.modules.graph.adapters.api.dependencies import get_graph_repos, get_graph_uow
from app.modules.graph.adapters.persistence.in_memory_edge_repository import (
    InMemoryEdgeRepository,
)
from app.modules.graph.adapters.persistence.in_memory_edge_type_repository import (
    InMemoryEdgeTypeRepository,
)
from app.modules.graph.adapters.persistence.in_memory_node_repository import (
    InMemoryNodeRepository,
)
from app.modules.graph.adapters.persistence.in_memory_node_type_repository import (
    InMemoryNodeTypeRepository,
)
from app.modules.graph.adapters.persistence.unit_of_work import (
    create_in_memory_graph_uow,
)
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.modules.identity.adapters.api.dependencies import (
    get_active_identity_actor,
    get_decoy_hash,
    get_identity_actor,
    get_identity_repos,
    get_identity_uow,
    get_password_hasher,
    get_signed_in_user,
)
from app.modules.identity.adapters.persistence.in_memory_api_token_repository import (
    InMemoryApiTokenRepository,
)
from app.modules.identity.adapters.persistence.in_memory_session_repository import (
    InMemorySessionRepository,
)
from app.modules.identity.adapters.persistence.in_memory_sign_in_attempt_repository import (  # noqa: E501
    InMemorySignInAttemptRepository,
)
from app.modules.identity.adapters.persistence.in_memory_user_repository import (
    InMemoryUserRepository,
)
from app.modules.identity.adapters.persistence.unit_of_work import (
    create_in_memory_identity_uow,
)
from app.modules.identity.adapters.security.in_memory_password_hasher import (
    InMemoryPasswordHasher,
)
from app.modules.identity.domain.api_token import ApiToken
from app.modules.identity.domain.user import User
from app.modules.identity.ports.unit_of_work import IdentityRepos
from app.modules.media.adapters.api.dependencies import (
    get_image_processor,
    get_media_repos,
    get_media_storage,
    get_media_uow,
)
from app.modules.media.adapters.imaging.in_memory_image_processor import (
    InMemoryImageProcessor,
)
from app.modules.media.adapters.persistence.unit_of_work import (
    create_in_memory_media_uow,
    make_in_memory_repos,
)
from app.modules.media.adapters.policy.content_type_attachment_policy import (
    ContentTypeAttachmentPolicy,
)
from app.modules.media.adapters.storage.in_memory_media_storage import (
    InMemoryMediaStorage,
)
from app.modules.presets.adapters.api.dependencies import (
    get_preset_repos,
    get_preset_uow,
)
from app.modules.presets.adapters.persistence.in_memory_preset_repository import (
    InMemoryPresetRepository,
)
from app.modules.presets.adapters.persistence.unit_of_work import (
    create_in_memory_preset_uow,
)
from app.modules.presets.ports.unit_of_work import PresetRepos
from app.modules.system.adapters.api.dependencies import (
    get_get_health_ready_detail_use_case,
    get_get_health_ready_use_case,
)
from app.modules.system.adapters.platform.in_memory_health_check_adapter import (
    InMemoryHealthCheckAdapter,
)
from app.modules.system.application.get_health_ready import GetHealthReady
from app.modules.system.application.get_health_ready_detail import GetHealthReadyDetail
from app.modules.system.domain.readiness import (
    CheckObservation,
    CheckStatus,
    ReadinessReport,
)
from app.shared_kernel.actor import Actor
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Sequence

    from fastapi import FastAPI
    from httpx2 import Response

    from app.modules.collections.ports.unit_of_work import CollectionsRepos
    from app.modules.media.ports.unit_of_work import MediaRepos
    from app.shared_kernel.content_filter import ContentFilter

Route = tuple[str, str]

ADMIN = uuid.UUID(int=100)
ALICE = uuid.UUID(int=101)
BOB = uuid.UUID(int=102)
PACK_ID = "demo"
PASSWORD = "a-long-enough-password"
TINY_JPEG = bytes.fromhex(
    "ffd8ffe000104a46494600010101004800480000ffdb004300080606070605080707070909080a0c140d0c0b0b0c1912130f141d1a1f1e1d1a1c1c20242e2720222c231c1c28372930313434341f27393d38323c2e333432ffc0000b080001000101011100ffc4001f0000010501010101010100000000000000000102030405060708090a0bffda0008010100003f00bf00ffd9"
)
# Strings only A's content contains: none may ever appear in a response to B.
CANARIES = (
    "Xenomorph Alpha",
    "Ripley Beta",
    "Alpha Collection",
    "Alpha Smart",
    "poster-alpha.jpg",
    "Alpha script",
)


# ---- the explicit allow-list: routes that are not per-person content ----

PUBLIC = "public: no content, no session"
OWN_SESSION = "acts on the caller's own session or account"
VOCABULARY = "shared vocabulary: every member reads and edits item/relationship types"
PRESETS = "shared presets: not owned content (decision 6)"
CREATES_OWN = "references no existing content; creates content owned by the caller"

RECENTLY_DELETED = "own deleted rows only, empty in the seed; two-user router tests"
SETTINGS = "administrator-only instance settings, not owned content; router tests"
SCHEDULING = "administrator-only scheduler views and run-now, no content; router tests"
DIAGNOSTICS = (
    "administrator-only build and update status, not owned content; router tests"
)

ALLOWED: dict[Route, str] = {
    ("GET", "/api/v1/system/version/detail"): DIAGNOSTICS,
    ("POST", "/api/v1/system/version/check"): DIAGNOSTICS,
    ("GET", "/api/v1/scheduling/schedule-preview"): SCHEDULING,
    ("GET", "/api/v1/scheduling/jobs"): SCHEDULING,
    ("GET", "/api/v1/scheduling/jobs/{job_key}/runs"): SCHEDULING,
    ("POST", "/api/v1/scheduling/jobs/{job_key}/run"): SCHEDULING,
    ("GET", "/api/v1/settings/schema"): SETTINGS,
    ("GET", "/api/v1/settings/instance"): SETTINGS,
    ("PATCH", "/api/v1/settings/instance"): SETTINGS,
    ("DELETE", "/api/v1/settings/instance/{key}"): SETTINGS,
    ("GET", "/api/v1/node/deleted"): RECENTLY_DELETED,
    ("POST", "/api/v1/node/{node_id}/restore"): RECENTLY_DELETED,
    ("DELETE", "/api/v1/node/{node_id}/purge"): RECENTLY_DELETED,
    ("GET", "/api/v1/collection/deleted"): RECENTLY_DELETED,
    ("POST", "/api/v1/collection/{collection_id}/restore"): RECENTLY_DELETED,
    ("DELETE", "/api/v1/collection/{collection_id}/purge"): RECENTLY_DELETED,
    (
        "POST",
        "/api/v1/backup",
    ): "administrator-only instance archive; tested by backup router permission tests",
    (
        "GET",
        "/api/v1/backup",
    ): "administrator-only instance archive; tested by backup router permission tests",
    ("POST", "/api/v1/backup/upload"): "administrator-only verified instance upload",
    ("POST", "/api/v1/backup/prune"): "administrator-only instance retention",
    (
        "POST",
        "/api/v1/backup/{backup_id}/verify",
    ): "administrator-only instance verification",
    (
        "GET",
        "/api/v1/backup/{backup_id}/download",
    ): "administrator-only instance download",
    ("DELETE", "/api/v1/backup/{backup_id}"): "administrator-only instance deletion",
    (
        "POST",
        "/api/v1/backup/first-run-restore",
    ): "public only before setup; shared-lock and rate-limit integration tests",
    (
        "POST",
        "/api/v1/me/export",
    ): "personal snapshots and dedicated two-user export API tests",
    (
        "GET",
        "/api/v1/me/export/{backup_id}/download",
    ): "private owner namespace; API test checks foreign exports return 404",
    (
        "GET",
        "/api/v1/me/exports",
    ): "private owner namespace; API test checks each account lists only its own",
    (
        "DELETE",
        "/api/v1/me/export/{backup_id}",
    ): "private owner namespace; API test checks foreign exports return 404",
    (
        "POST",
        "/api/v1/me/import",
    ): "two-user API and Postgres tests cover owner stamping and isolation",
    ("GET", "/api/health"): PUBLIC,
    ("GET", "/api/health/ready"): PUBLIC,
    ("GET", "/api/v1/system/version"): PUBLIC,
    ("GET", "/api/favicon.ico"): PUBLIC,
    ("GET", "/api/docs/favicon.svg"): PUBLIC,
    ("GET", "/api/docs/logo.svg"): PUBLIC,
    ("GET", "/api/docs/swagger-init.js"): PUBLIC,
    ("GET", "/api/openapi.json"): PUBLIC,
    ("GET", "/api/docs"): PUBLIC,
    ("GET", "/api/docs/oauth2-redirect"): PUBLIC,
    ("GET", "/api/redoc"): PUBLIC,
    ("GET", "/api/v1/auth/status"): PUBLIC,
    ("POST", "/api/v1/auth/setup"): PUBLIC,
    ("POST", "/api/v1/auth/login"): PUBLIC,
    ("POST", "/api/v1/auth/logout"): OWN_SESSION,
    ("GET", "/api/v1/auth/me"): OWN_SESSION,
    ("PATCH", "/api/v1/auth/me"): OWN_SESSION,
    ("POST", "/api/v1/auth/password"): OWN_SESSION,
    ("GET", "/api/v1/auth/me/permissions"): OWN_SESSION,
    ("GET", "/api/v1/auth/sessions"): OWN_SESSION,
    ("DELETE", "/api/v1/auth/sessions/{session_id}"): OWN_SESSION,
    ("DELETE", "/api/v1/auth/sessions"): OWN_SESSION,
    ("GET", "/api/v1/session"): "permission-gated: administrators list active sessions",
    (
        "DELETE",
        "/api/v1/session/{session_id}",
    ): "permission-gated: administrators revoke sessions",
    ("GET", "/api/v1/node-type"): VOCABULARY,
    ("GET", "/api/v1/node-type/{node_type_id}"): VOCABULARY,
    ("POST", "/api/v1/node-type"): VOCABULARY,
    ("PATCH", "/api/v1/node-type/{node_type_id}"): VOCABULARY,
    ("GET", "/api/v1/edge-type"): VOCABULARY,
    ("GET", "/api/v1/edge-type/{edge_type_id}"): VOCABULARY,
    ("POST", "/api/v1/edge-type"): VOCABULARY,
    ("PATCH", "/api/v1/edge-type/{edge_type_id}"): VOCABULARY,
    ("POST", "/api/v1/preset"): PRESETS,
    ("GET", "/api/v1/preset"): PRESETS,
    ("GET", "/api/v1/preset/export"): PRESETS,
    ("POST", "/api/v1/preset/import"): PRESETS,
    ("GET", "/api/v1/preset/{preset_id}"): PRESETS,
    ("PATCH", "/api/v1/preset/{preset_id}"): PRESETS,
    ("DELETE", "/api/v1/preset/{preset_id}"): PRESETS,
    ("POST", "/api/v1/node"): CREATES_OWN,
    ("POST", "/api/v1/collection"): CREATES_OWN,
    ("POST", "/api/v1/tokens"): CREATES_OWN,
    ("GET", "/api/v1/tokens/grants"): OWN_SESSION,
    ("POST", "/api/v1/media"): CREATES_OWN,
}


# ---- seeded ids and the parameter-name tables ----


@dataclass(frozen=True)
class Seed:
    """The ids of everything user A owns."""

    item: str
    item2: str
    edge: str
    film: str
    edge_type: str
    collection: str
    collection_slug: str
    smart: str
    smart_slug: str
    asset: str
    staged: str
    user: str
    token: str


PATH_PARAMS: dict[str, Callable[[Seed], str]] = {
    "node_id": lambda s: s.item,
    "item_id": lambda s: s.item,
    "edge_id": lambda s: s.edge,
    "node_type_id": lambda s: s.film,
    "edge_type_id": lambda s: s.edge_type,
    "collection_id": lambda s: s.collection,
    "asset_id": lambda s: s.asset,
    "user_id": lambda s: s.user,
    "token_id": lambda s: s.token,
    "pack_id": lambda _: PACK_ID,
    "key": lambda _: "rating",
}
QUERY_PARAMS: dict[str, Callable[[Seed], str]] = {
    "q": lambda _: "xenomorph",
    "type": lambda _: "film",
    "favourite": lambda _: "true",
    "kind": lambda _: "manual",
    "collection": lambda s: s.collection,
    "node_id": lambda s: s.item,
    "item_id": lambda s: s.item,
    "after": lambda s: s.item,
    "limit": lambda _: "50",
    "value": lambda _: "R",
    "sub_key": lambda _: "x",
}
# Request-body recipes by OpenAPI schema name: kwargs for `client.request`.
BODIES: dict[str, Callable[[Seed], dict[str, Any]]] = {
    "UpdateNodeRequest": lambda s: {"json": {"name": "Stolen"}},
    "PromoteExtraSchemaFieldRequest": lambda s: {"json": {"node_type_id": s.film}},
    "NodeSearchRequest": lambda s: {
        "json": {
            "query": {
                "v": 1,
                "where": {
                    "op": "or",
                    "children": [
                        {"kind": "text", "q": "xenomorph"},
                        {"kind": "collection", "mode": "any", "in": [s.collection]},
                        {"kind": "collection", "mode": "none", "in": [s.smart]},
                        {"kind": "media", "mode": "has"},
                    ],
                },
            }
        }
    },
    "CreateEdgeRequest": lambda s: {
        "json": {"source_id": s.item, "target_id": s.item2, "type": "owns"}
    },
    "CreateEdgesRequest": lambda s: {
        "json": {"source_id": s.item, "target_ids": [s.item2], "type": "owns"}
    },
    "UpdateEdgeRequest": lambda s: {"json": {"attributes": {"k": "v"}}},
    "UpdateMediaRequest": lambda s: {"json": {"filename": "mine.jpg"}},
    "AttachMediaRequest": lambda s: {
        "json": {"target_type": "node", "target_id": s.item2}
    },
    "DetachMediaRequest": lambda s: {
        "json": {
            "target_type": "node",
            "target_id": s.item,
            "attribute_key": "cover",
        }
    },
    "CoverRequest": lambda s: {"json": {"target_type": "node", "target_id": s.item}},
    "UploadAndAttachMediaBody": lambda s: {
        "files": {"file": ("c.jpg", TINY_JPEG, "image/jpeg")},
        "data": {"target_type": "node", "target_id": s.item},
    },
    "UpdateCollectionRequest": lambda s: {"json": {"name": "Mine"}},
    "AddItemsRequest": lambda s: {"json": {"item_ids": [s.item2]}},
    "CreateUserRequest": lambda s: {
        "json": {"username": "mallory", "display_name": "M", "password": PASSWORD}
    },
    "UpdateUserRequest": lambda s: {"json": {"display_name": "Renamed"}},
    "ResetPasswordRequest": lambda s: {"json": {"password": PASSWORD}},
    "RotateApiTokenRequest": lambda s: {"json": {"password": PASSWORD}},
}
# Routes whose B-side answer is legitimately a success (B acts on B's own data).
# Each check returns an error message or None; A's data is checked unchanged too.
SPECIAL: dict[Route, Callable[[Response], str | None]] = {}


def _installed_for_b(response: Response) -> str | None:
    if response.status_code != 200:
        return f"B installing the pack for B should work, got {response.status_code}"
    return None


def _no_installation(response: Response) -> str | None:
    if response.status_code != 200:
        return f"expected 200, got {response.status_code}"
    shown = [p["id"] for p in response.json() if p["installation"] is not None]
    return f"B sees installations of {shown}" if shown else None


SPECIAL[("PUT", "/api/v1/example/{pack_id}/installation")] = _installed_for_b


def _not_installed_for_b(response: Response) -> str | None:
    if (
        response.status_code == 409
        and response.json()["title"] == "PackNotInstalledError"
    ):
        return None
    return f"expected 409 PackNotInstalledError, got {response.status_code}"


SPECIAL[("GET", "/api/v1/example")] = _no_installation
SPECIAL[("DELETE", "/api/v1/example/{pack_id}/installation")] = _not_installed_for_b
ADMIN_PREFIXES = ("/api/v1/user", "/api/v1/session")
# Setup the positive control needs because the seed already did the thing.
POSITIVE_PREP: dict[Route, Callable[[World], None]] = {
    ("PUT", "/api/v1/example/{pack_id}/installation"): lambda w: w.uninstall_pack(),
}


# ---- the world ----


def _pack() -> ExamplePack:
    return ExamplePack(
        id=PACK_ID,
        relationship_types=(
            PackRelationshipType(ref="by", slug="demo-by", label="By"),
        ),
        item_types=(PackItemType(ref="thing", slug="demo-thing", label="Thing"),),
        items=(
            PackItem(ref="a", type_ref="thing", name="Pack A"),
            PackItem(ref="b", type_ref="thing", name="Pack B"),
        ),
        connections=(PackConnection(source_ref="a", target_ref="b", type_ref="by"),),
    )


_PASSING_READINESS = ReadinessReport(
    status=CheckStatus.PASS,
    checks={
        "database:responseTime": [
            CheckObservation(
                component_type="datastore",
                observed_value=1,
                observed_unit="ms",
                status=CheckStatus.PASS,
                time=datetime.now(UTC),
            )
        ]
    },
)


class WorldExternalConditions:
    """Media and collection facts read from the world's in-memory repositories."""

    def __init__(self, collections: CollectionsRepos, media: MediaRepos) -> None:
        self._collections = collections
        self._media = media

    def media_predicate(self, *_args: object) -> object:
        """Not used by the in-memory evaluator."""
        raise NotImplementedError

    def collection_predicate(self, *_args: object) -> object:
        """Not used by the in-memory evaluator."""
        raise NotImplementedError

    def media_matches(
        self,
        node_id: uuid.UUID,
        mode: str,
        type: str | None,
        scope: ContentFilter,
    ) -> bool:
        """Whether the item has ready media owned inside `scope`."""
        assets = self._media.assets._assets  # type: ignore[attr-defined]
        found = False
        for attachment in self._media.attachments._store.values():  # type: ignore[attr-defined]
            asset = assets.get(attachment.asset_id)
            found = found or (
                attachment.target_id == node_id
                and asset is not None
                and asset.status == "attached"
                and scope.covers(asset.owner_id)
                and (
                    type is None
                    or asset.content_type.startswith("image/") == (type == "image")
                )
            )
        return found == (mode == "has")

    def collection_matches(
        self,
        node_id: uuid.UUID,
        collection_ids: Sequence[uuid.UUID],
        scope: ContentFilter,
    ) -> bool:
        """Whether the item is on a live manual collection inside `scope`."""
        stored = self._collections.collections._collections  # type: ignore[attr-defined]
        members = self._collections.memberships._memberships  # type: ignore[attr-defined]
        for collection_id in collection_ids:
            collection = stored.get(collection_id)
            if (
                collection is not None
                and not collection.is_deleted
                and scope.covers(collection.owner_id)
                and (collection_id, node_id) in members
            ):
                return True
        return False


class World:
    """The real app over in-memory repositories for every module."""

    def __init__(self, as_user: Callable[..., None]) -> None:
        self._as_user = as_user
        self.app: FastAPI = create_app()
        presets = PresetRepos(presets=InMemoryPresetRepository())
        collections = build_in_memory_collections_repos()
        media = make_in_memory_repos()
        external = WorldExternalConditions(collections, media)
        graph = GraphRepos(
            nodes=InMemoryNodeRepository(external),
            edges=InMemoryEdgeRepository(),
            node_types=InMemoryNodeTypeRepository(),
            edge_types=InMemoryEdgeTypeRepository(),
            external=external,
            definitions=CollectionsDefinitions(collections),
        )
        installations = InMemoryInstallationRepository()
        examples = ExampleRepos(installations=installations)
        catalogue = InMemoryPackCatalogue()
        catalogue.add(_pack(), name="Demo", description="Demo examples")
        self.hasher = InMemoryPasswordHasher()
        self.identity = IdentityRepos(
            users=InMemoryUserRepository(),
            sessions=InMemorySessionRepository(),
            attempts=InMemorySignInAttemptRepository(),
            tokens=InMemoryApiTokenRepository(),
        )
        storage = InMemoryMediaStorage()
        processor = InMemoryImageProcessor()

        def graph_target(
            actor: Annotated[Actor, Depends(get_current_actor)],
        ) -> GraphPackTarget:
            return GraphPackTarget(
                in_memory_graph_stores(graph, media, presets, collections), actor
            )

        def collection_target(
            actor: Annotated[Actor, Depends(get_current_actor)],
        ) -> CollectionPackTarget:
            return CollectionPackTarget(
                in_memory_collection_stores(collections, graph), actor
            )

        def cover_target(
            actor: Annotated[Actor, Depends(get_current_actor)],
        ) -> CoverPackTarget:
            return CoverPackTarget(
                in_memory_cover_stores(media, graph),
                actor,
                renderer=InMemoryCoverRenderer(),
                storage=storage,
                policy=ContentTypeAttachmentPolicy(),
                image_processor=processor,
            )

        o = self.app.dependency_overrides
        o[get_graph_uow] = lambda: create_in_memory_graph_uow(graph)
        o[get_graph_repos] = lambda: graph
        o[get_collections_uow] = lambda: create_in_memory_collections_uow(collections)
        o[get_collections_repos] = lambda: collections
        o[get_media_uow] = lambda: create_in_memory_media_uow(media)
        o[get_media_repos] = lambda: media
        o[get_media_storage] = lambda: storage
        o[get_image_processor] = lambda: processor
        o[get_preset_uow] = lambda: create_in_memory_preset_uow(presets)
        o[get_preset_repos] = lambda: presets
        o[get_example_uow] = lambda: InMemoryUnitOfWork(examples)
        o[get_example_repos] = lambda: examples
        o[get_pack_catalogue] = lambda: catalogue
        o[get_identity_uow] = lambda: create_in_memory_identity_uow(self.identity)
        o[get_identity_repos] = lambda: self.identity
        o[get_password_hasher] = lambda: self.hasher
        o[get_decoy_hash] = lambda: self.hasher.hash("decoy")
        # The bridges run over the same in-memory repositories.
        o[get_attach_target_access] = lambda: GraphAttachTargetAccess(graph)
        o[get_choice_list_source] = lambda: PresetChoiceListSource(presets)
        o[get_item_lookup] = lambda: GraphItemLookup(graph)
        o[get_collection_members] = lambda: CollectionsMembers(collections)
        o[get_definition_checker] = lambda: GraphDefinitionChecker(graph)
        # Readiness would otherwise open a real database connection.
        ready = InMemoryHealthCheckAdapter(_PASSING_READINESS)
        o[get_get_health_ready_use_case] = lambda: GetHealthReady(
            ready, get_access_guard()
        )
        o[get_get_health_ready_detail_use_case] = lambda: GetHealthReadyDetail(
            ready, get_access_guard()
        )
        o[get_preset_pack_target] = lambda: PresetPackTarget(
            in_memory_preset_stores(presets, graph)
        )
        o[get_graph_pack_target] = graph_target
        o[get_collection_pack_target] = collection_target
        o[get_cover_pack_target] = cover_target
        self.client = TestClient(self.app)

    def act_as(self, user_id: uuid.UUID, role: str = "member") -> TestClient:
        """Make every following request run as `user_id`."""
        self._as_user(self.app, user_id, role)
        actor = Actor(id=user_id, roles=frozenset({role}))
        self.app.dependency_overrides[get_identity_actor] = lambda: actor
        self.app.dependency_overrides[get_active_identity_actor] = lambda: actor
        self.app.dependency_overrides[get_signed_in_user] = lambda: pytest.fail(
            "identity routes must use get_identity_actor"
        )
        return self.client

    def seed(self) -> Seed:
        """Give A one of every kind of content, through the API."""
        user = User.create(
            username="alice",
            display_name="Alice",
            password_hash="not-a-real-hash",
            now=datetime.now(UTC),
        )
        assert self.client.portal is not None
        self.client.portal.call(self.identity.users.add, user)
        token = self._seed_token_owners()
        a = self.act_as(ALICE)
        film = _created(
            a.post("/api/v1/node-type", json={"slug": "film", "label": "F"})
        )
        item = _created(
            a.post(
                "/api/v1/node",
                json={
                    "name": "Xenomorph Alpha",
                    "type": "film",
                    "description": "xenomorph",
                    "attributes": {"rating": "R"},
                    "extra_schema": {
                        "type": "object",
                        "properties": {
                            "rating": {
                                "type": "string",
                                "x-menagerist": {"kind": "text"},
                            }
                        },
                    },
                    "favourite": True,
                },
            )
        )
        item2 = _created(a.post("/api/v1/node", json={"name": "Ripley Beta"}))
        edge = _created(
            a.post(
                "/api/v1/edge",
                json={
                    "source_id": item["id"],
                    "target_id": item2["id"],
                    "type": "owns",
                },
            )
        )
        # Unused, so the admin-only delete has something it may remove.
        edge_type = _created(
            a.post("/api/v1/edge-type", json={"slug": "spare", "label": "Spare"})
        )
        collection = _created(
            a.post("/api/v1/collection", json={"name": "Alpha Collection"})
        )
        assert (
            a.put(
                f"/api/v1/collection/{collection['id']}/item",
                json={"item_ids": [item["id"]]},
            ).status_code
            == 200
        )
        smart = _created(
            a.post(
                "/api/v1/collection",
                json={"name": "Alpha Smart", "definition": SMART_DEFINITION},
            )
        )
        assert smart["item_count"] == 1, smart
        asset = _created(
            a.post(
                "/api/v1/media/attached",
                files={"file": ("poster-alpha.jpg", TINY_JPEG, "image/jpeg")},
                data={"target_type": "node", "target_id": item["id"]},
            )
        )
        cover = a.post(
            f"/api/v1/media/{asset['asset_id']}/attachments/cover",
            json={"target_type": "node", "target_id": item["id"]},
        )
        assert cover.status_code == 200, cover.text
        staged = _created(
            a.post(
                "/api/v1/media", files={"file": ("staged.jpg", TINY_JPEG, "image/jpeg")}
            )
        )
        installed = a.put(f"/api/v1/example/{PACK_ID}/installation")
        assert installed.status_code == 200, installed.text
        return Seed(
            item=item["id"],
            item2=item2["id"],
            edge=edge["id"],
            film=film["id"],
            edge_type=edge_type["id"],
            collection=collection["id"],
            collection_slug=collection["slug"],
            smart=smart["id"],
            smart_slug=smart["slug"],
            asset=asset["asset_id"],
            staged=staged["id"],
            user=str(user.id),
            token=str(token),
        )

    def _seed_token_owners(self) -> uuid.UUID:
        """Give the acting A and B account rows and A one token; return its id.

        Rotation checks the actor's password, so the actors need real accounts.
        """
        assert self.client.portal is not None
        now = datetime.now(UTC)
        for actor_id, name in ((ALICE, "alice-actor"), (BOB, "bob-actor")):
            account = User.create(
                username=name,
                display_name=name,
                password_hash=self.hasher.hash(PASSWORD),
                now=now,
            )
            account.id = actor_id
            self.client.portal.call(self.identity.users.add, account)
        token = ApiToken.create(
            token_id=uuid.uuid7(),
            user_id=ALICE,
            name="Alpha script",
            secret_hash="not-a-real-hash",
            grants={"graph:item:read"},
            now=now,
            expires_at=now + timedelta(days=30),
        )
        self.client.portal.call(self.identity.tokens.add, token)
        return token.id

    def uninstall_pack(self) -> None:
        """Let A install the pack again."""
        removed = self.act_as(ALICE).delete(f"/api/v1/example/{PACK_ID}/installation")
        assert removed.status_code == 200, removed.text

    def snapshot(self, seed: Seed) -> dict[str, object]:
        """A's own view of all its content, to prove B's call changed nothing."""
        a = self.act_as(ALICE)
        urls = [
            "/api/v1/node",
            f"/api/v1/node/{seed.item}",
            "/api/v1/edge",
            f"/api/v1/edge/{seed.edge}",
            "/api/v1/collection",
            f"/api/v1/collection/{seed.collection}",
            f"/api/v1/collection/{seed.smart}",
            f"/api/v1/node?collection={seed.smart}",
            f"/api/v1/media/for-node/{seed.item}",
            f"/api/v1/media/{seed.asset}",
            f"/api/v1/media/{seed.staged}",
            "/api/v1/example/entities",
        ]
        view: dict[str, object] = {}
        for url in urls:
            response = a.get(url)
            view[url] = (response.status_code, response.text)
        content = a.get(f"/api/v1/media/{seed.asset}/content")
        view["content"] = hashlib.sha256(content.content).hexdigest()
        return view


@pytest.fixture
def world(as_user: Callable[..., None]) -> Iterator[World]:
    """Own the isolation world's client for the duration of one test."""
    instance = World(as_user)
    # This in-memory world does not run startup probes against real infrastructure.
    instance.app.router.lifespan_context = lambda _: nullcontext()
    with ExitStack() as stack:
        stack.callback(instance.client.close)
        stack.enter_context(instance.client)
        yield instance


def test_world_reuses_event_loop_between_requests(world: World) -> None:
    """Requests must share a live loop instead of opening sockets per request."""
    loops: list[asyncio.AbstractEventLoop] = []

    @world.app.get("/test-event-loop")
    async def event_loop() -> None:
        loops.append(asyncio.get_running_loop())

    for _ in range(2):
        assert world.client.get("/test-event-loop").status_code == 200
    assert loops[0] is loops[1]
    assert not loops[0].is_closed()


def _created(response: Response) -> dict[str, Any]:
    assert response.status_code in (200, 201), response.text
    body: dict[str, Any] = response.json()
    return body


# ---- route table and case generation ----


def route_table(app: FastAPI) -> set[Route]:
    """Every (method, path) the app serves, mounted routers and mounts included."""
    found: set[Route] = set()

    def visit(routes: Any) -> None:  # noqa: ANN401
        for route in routes:
            if hasattr(route, "effective_candidates"):
                visit(route.effective_candidates())
                continue
            path = getattr(route, "path_format", None) or getattr(route, "path", None)
            assert path is not None, f"unreadable route {route!r}"
            methods = getattr(route, "methods", None)
            if methods is None:
                if getattr(route, "name", None) != "spa":
                    found.add(("MOUNT", path))
                continue
            found.update((m, path) for m in methods if m not in {"HEAD", "OPTIONS"})

    visit(app.routes)
    return found


@dataclass(frozen=True)
class Case:
    """One call to make as B (and, as a positive control, as A)."""

    method: str
    template: str
    variant: str

    @property
    def id(self) -> str:
        """The test id: method, route template and variant."""
        return f"{self.method} {self.template} [{self.variant}]"


def _operations(app: FastAPI) -> dict[Route, dict[str, Any]]:
    paths: dict[str, dict[str, Any]] = app.openapi()["paths"]
    return {(m.upper(), p): op for p, item in paths.items() for m, op in item.items()}


# Routes that also run against a staged (unattached) asset.
STAGED_TOO: set[Route] = {
    ("GET", "/api/v1/media/{asset_id}"),
    ("GET", "/api/v1/media/{asset_id}/content"),
    ("GET", "/api/v1/media/{asset_id}/thumbnail"),
    ("PATCH", "/api/v1/media/{asset_id}"),
    ("DELETE", "/api/v1/media/{asset_id}"),
}
STREAMS = ("/content", "/thumbnail")  # file streams send an ETag too
# Routes that also run against A's smart collection (its `collection_id` or the
# `collection` query). Its membership routes are a 409 even for A, so they are
# checked in `test_user_b_cannot_edit_a_smart_collections_membership`.
SMART_TOO: set[Route] = {
    ("GET", "/api/v1/collection/{collection_id}"),
    ("GET", "/api/v1/collection/{collection_id}/count"),
    ("PATCH", "/api/v1/collection/{collection_id}"),
    ("DELETE", "/api/v1/collection/{collection_id}"),
    ("GET", "/api/v1/node"),
}
# Routes whose `collection_id` also accepts A's slug. Smart ones also run against
# A's smart collection by slug (its membership routes are covered separately).
SLUG_TOO: set[Route] = {
    ("GET", "/api/v1/collection/{collection_id}"),
    ("GET", "/api/v1/collection/{collection_id}/count"),
    ("PATCH", "/api/v1/collection/{collection_id}"),
    ("DELETE", "/api/v1/collection/{collection_id}"),
    ("PUT", "/api/v1/collection/{collection_id}/item"),
    ("DELETE", "/api/v1/collection/{collection_id}/item/{item_id}"),
}
SMART_DEFINITION: dict[str, Any] = {
    "v": 1,
    "where": {"op": "and", "children": [{"kind": "text", "q": "xenomorph"}]},
}
# Routes that only make sense on a staged (not yet attached) asset.
STAGED_ONLY: set[Route] = {("POST", "/api/v1/media/{asset_id}/promote")}


def _sends_etag(op: dict[str, Any]) -> bool:
    return "ETag" in op.get("responses", {}).get("200", {}).get("headers", {})


def _collection_variants(method: str, template: str) -> list[Case]:
    """The smart and by-slug variants of a collection route."""
    route = (method, template)
    variants = ["smart"] if route in SMART_TOO else []
    if route in SLUG_TOO:
        variants += ["slug", "smart-slug"] if route in SMART_TOO else ["slug"]
    return [Case(method, template, v) for v in variants]


def generate_cases(app: FastAPI) -> list[Case]:
    """The calls for every route that is not on the allow-list."""
    table = route_table(app)
    operations = _operations(app)
    cases: list[Case] = []
    for method, template in sorted(table - ALLOWED.keys()):
        op = operations.get((method, template), {})
        queries = [p["name"] for p in op.get("parameters", []) if p["in"] == "query"]
        cases.append(Case(method, template, "bare"))
        cases.extend(Case(method, template, f"query:{name}") for name in queries)
        if len(queries) > 1:
            cases.append(Case(method, template, "query:all"))
        if (method, template) in STAGED_TOO:
            cases.append(Case(method, template, "staged"))
        prefixes = ("", "smart-") if (method, template) in SMART_TOO else ("",)
        cases.extend(_collection_variants(method, template))
        for prefix in prefixes:
            if method == "GET" and (_sends_etag(op) or template.endswith(STREAMS)):
                cases.append(Case(method, template, f"{prefix}if-none-match"))
            elif method != "GET" and _sends_etag(operations.get(("GET", template), {})):
                cases.append(Case(method, template, f"{prefix}if-match"))
    return cases


def _fill(
    case: Case,
    table: dict[str, Callable[[Seed], str]],
    names: list[str],
    seed: Seed,
    kind: str,
) -> dict[str, str]:
    values: dict[str, str] = {}
    for name in names:
        if name not in table:
            pytest.fail(
                f"{case.method} {case.template}: no value for {kind} parameter "
                + f"{name!r}; add it to the {kind.upper()}_PARAMS table"
            )
        values[name] = table[name](seed)
    return values


# Where the generic value would match nothing of A's even for A.
QUERY_OVERRIDES: dict[tuple[str, str], str] = {
    ("/api/v1/collection", "q"): "alpha",  # collections match on their name
    ("/api/v1/node-type/{node_type_id}/attribute/{key}/values", "q"): "R",
}


def _aim_at_smart(case: Case, values: dict[str, str], seed: Seed) -> dict[str, Any]:
    """For a smart variant, point the collection id or query at A's smart one."""
    if case.variant.endswith("slug"):
        smart = case.variant.startswith("smart")
        values["collection_id"] = seed.smart_slug if smart else seed.collection_slug
        return {}
    if not case.variant.startswith("smart"):
        return {}
    if "collection_id" in values:
        values["collection_id"] = seed.smart
        return {}
    return {"params": {"collection": seed.smart}}


def build_request(
    case: Case, op: dict[str, Any], seed: Seed
) -> tuple[str, dict[str, Any]]:
    """Return the URL and `client.request` kwargs for a case, filled with A's ids."""
    path_names = re.findall(r"{(\w+)}", case.template)
    values = _fill(case, PATH_PARAMS, path_names, seed, "path")
    if case.variant == "staged" or (case.method, case.template) in STAGED_ONLY:
        values["asset_id"] = seed.staged
    kwargs = _aim_at_smart(case, values, seed)
    url = case.template.format(**values)
    query_names = [p["name"] for p in op.get("parameters", []) if p["in"] == "query"]
    if case.variant.startswith("query:"):
        # `after` would skip A's first item, so the combined call leaves it out.
        chosen = (
            [n for n in query_names if n != "after"]
            if case.variant == "query:all"
            else [case.variant[6:]]
        )
        kwargs["params"] = _fill(case, QUERY_PARAMS, chosen, seed, "query")
        for (template, name), value in QUERY_OVERRIDES.items():
            if case.template == template and name in kwargs["params"]:
                kwargs["params"][name] = value
    content = op.get("requestBody", {}).get("content", {})
    if content:
        ref = next(iter(content.values()))["schema"]["$ref"]
        schema = ref.rsplit("/", 1)[-1]
        if schema not in BODIES:
            pytest.fail(
                f"{case.method} {case.template}: no body recipe for {schema!r}; "
                + "add it to BODIES"
            )
        kwargs.update(BODIES[schema](seed))
    return url, kwargs


def is_denied(response: Response, *, admin_only: bool = False) -> bool:
    """404 (403 only on admin-only routes), or a 200 with nothing in it."""
    if response.status_code == 404 or (admin_only and response.status_code == 403):
        return True
    if response.status_code != 200:
        return False
    if response.headers.get("Total-Count", "0") != "0" or "Link" in response.headers:
        return False
    if "application/json" not in response.headers.get("content-type", ""):
        return False
    return _empty(response.json())


def _with_unknown_ids(
    url: str, kwargs: dict[str, Any], seed: Seed
) -> tuple[str, dict[str, Any]]:
    """The same request with every one of A's ids swapped for a random uuid."""
    # Item and relationship types are shared vocabulary every member can list.
    shared = {seed.film, seed.edge_type}
    swaps = {v: str(uuid.uuid7()) for v in vars(seed).values() if v not in shared}

    def swap(value: Any) -> Any:  # noqa: ANN401
        if isinstance(value, str):
            for old, new in swaps.items():
                value = value.replace(old, new)
            return value
        if isinstance(value, list):
            return [swap(v) for v in value]
        if isinstance(value, dict):
            return {k: swap(v) for k, v in value.items()}
        return value

    return swap(url), {k: (v if k == "files" else swap(v)) for k, v in kwargs.items()}


def _shape(response: Response) -> tuple[object, ...]:
    """Status plus problem type/title (or list length): what a caller can observe."""
    body = (
        response.json() if "json" in response.headers.get("content-type", "") else None
    )
    if isinstance(body, dict):
        return (response.status_code, body.get("type"), body.get("title"))
    return (response.status_code, len(body) if isinstance(body, list) else None)


# Variants whose value cannot match anything of A's even for A, and why.
EMPTY_FOR_A: dict[tuple[str, str], str] = {
    (
        "/api/v1/node-type/{node_type_id}/attribute/{key}/usage",
        "query:sub_key",
    ): "'rating' is a plain value, so no sub-key 'x' exists",
    (
        "/api/v1/edge-type/{edge_type_id}/attribute/{key}/usage",
        "query:sub_key",
    ): "the unused edge type has no attributes",
    (
        "/api/v1/edge-type/{edge_type_id}/attribute/{key}/usage",
        "query:value",
    ): "the unused edge type has no attributes",
    (
        "/api/v1/node-type/{node_type_id}/attribute/{key}/usage",
        "query:all",
    ): "value 'R' with sub-key 'x' matches no item",
    (
        "/api/v1/edge-type/{edge_type_id}/attribute/{key}/usage",
        "query:all",
    ): "the unused edge type has no attributes",
    (
        "/api/v1/edge-type/{edge_type_id}/attribute/{key}/usage",
        "bare",
    ): "the unused edge type has no attributes",
}


def _empty(body: object) -> bool:
    if isinstance(body, list):
        return not body
    if isinstance(body, dict):
        # Stale-condition warnings are not content; they are compared with an
        # unknown id's in the collection-condition test below.
        return all(_empty(v) for k, v in body.items() if k != "warnings")
    return body in (0, None, "", False)


_APP = create_app()
CASES = generate_cases(_APP)
OPERATIONS = _operations(_APP)
ADMIN_ROUTES = {
    route
    for route, op in OPERATIONS.items()
    if op.get("x-required-permission") in ADMIN_ONLY_ACTIONS
    or route[1].startswith(ADMIN_PREFIXES)
}


def _etag_headers(world: World, case: Case, seed: Seed) -> dict[str, str]:
    """The conditional header carrying A's current ETag for this resource."""
    kind = case.variant.removeprefix("smart-")
    if kind not in ("if-none-match", "if-match"):
        return {}
    base = "smart" if case.variant.startswith("smart-") else "bare"
    url, _ = build_request(Case("GET", case.template, base), {}, seed)
    etag = world.act_as(ALICE).get(url).headers.get("ETag")
    assert etag is not None, f"{case.id}: A's {url} sends no ETag"
    name = "If-None-Match" if kind == "if-none-match" else "If-Match"
    return {name: etag}


# ---- the tests ----


def test_every_route_is_allow_listed_or_generated() -> None:
    """A new route is generated (and so checked); a stale allow-list entry fails."""
    table = route_table(_APP)
    generated = {(c.method, c.template) for c in CASES}

    assert sorted(ALLOWED.keys() - table) == [], "stale allow-list entries"
    assert sorted(table - ALLOWED.keys() - generated) == []
    assert not generated & ALLOWED.keys()
    # The walk sees routes mounted straight on the app as well as the v1 router.
    assert len(table) >= 70, f"the route walk found only {len(table)} routes"
    assert ("GET", "/api/health") in table
    assert ("GET", "/api/v1/node/{node_id}") in table


def test_empty_and_query_override_entries_match_generated_cases() -> None:
    """An exemption or override that no generated case uses any more fails."""
    variants = {(c.template, c.variant) for c in CASES}
    stale_empty = sorted(str(key) for key in EMPTY_FOR_A if key not in variants)
    stale_queries = sorted(
        str(key)
        for key in QUERY_OVERRIDES
        if (key[0], f"query:{key[1]}") not in variants
        and (key[0], "query:all") not in variants
    )

    assert stale_empty == [], "stale EMPTY_FOR_A entries"
    assert stale_queries == [], "stale QUERY_OVERRIDES entries"


def test_generated_cases_cover_the_content_routes() -> None:
    """Sanity: lists, search, filters, ETags and media streams are all generated."""
    ids = {c.id for c in CASES}
    for expected in (
        "GET /api/v1/node [query:q]",
        "GET /api/v1/node [query:collection]",
        "GET /api/v1/node [smart]",
        "GET /api/v1/collection/{collection_id} [smart]",
        "GET /api/v1/collection/{collection_id}/count [bare]",
        "GET /api/v1/collection/{collection_id}/count [smart]",
        "GET /api/v1/collection/{collection_id} [smart-if-none-match]",
        "GET /api/v1/collection/{collection_id} [slug]",
        "GET /api/v1/collection/{collection_id} [smart-slug]",
        "GET /api/v1/collection/{collection_id}/count [slug]",
        "PATCH /api/v1/collection/{collection_id} [slug]",
        "DELETE /api/v1/collection/{collection_id} [slug]",
        "PUT /api/v1/collection/{collection_id}/item [slug]",
        "DELETE /api/v1/collection/{collection_id}/item/{item_id} [slug]",
        "PATCH /api/v1/collection/{collection_id} [smart-if-match]",
        "GET /api/v1/node/{node_id} [if-none-match]",
        "PATCH /api/v1/node/{node_id} [if-match]",
        "GET /api/v1/media/{asset_id}/content [if-none-match]",
        "GET /api/v1/media/{asset_id}/thumbnail [bare]",
        "GET /api/v1/example/entities [bare]",
    ):
        assert expected in ids


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_user_b_cannot_reach_user_a_content(case: Case, world: World) -> None:
    """B gets 404/403 or nothing at all; A's own view is untouched afterwards."""
    seed = world.seed()
    op = OPERATIONS.get((case.method, case.template), {})
    url, kwargs = build_request(case, op, seed)
    headers = _etag_headers(world, case, seed)
    # Reads cannot change anything, so only writes pay for the before/after view.
    writes = case.method != "GET"
    before = world.snapshot(seed) if writes else None

    admin_route = (case.method, case.template) in ADMIN_ROUTES
    bob = world.act_as(BOB)
    response = bob.request(case.method, url, headers=headers, **kwargs)

    special = SPECIAL.get((case.method, case.template))
    problem = (
        special(response)
        if special
        else (
            None
            if is_denied(response, admin_only=admin_route)
            else "expected 404 (403 only if admin-only) or an empty result"
        )
    )
    assert problem is None, (
        f"{case.id}: {problem}; got {response.status_code} {response.text[:300]}"
    )
    for canary in CANARIES:
        assert canary not in response.text, f"{case.id}: leaked {canary!r}"
    # A's ids must be indistinguishable from ids that never existed.
    ghost_url, ghost_kwargs = _with_unknown_ids(url, kwargs, seed)
    if (ghost_url, ghost_kwargs) != (url, kwargs):
        ghost = bob.request(case.method, ghost_url, headers=headers, **ghost_kwargs)
        assert _shape(ghost) == _shape(response), (
            f"{case.id}: existence leaks: A's id gives {_shape(response)}, "
            + f"an unknown id gives {_shape(ghost)}"
        )
    if before is not None:
        assert world.snapshot(seed) == before, f"{case.id}: changed A's content"


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_user_a_succeeds_on_the_same_call(case: Case, world: World) -> None:
    """Positive control: the same call as the owner works, so refusals are real."""
    seed = world.seed()
    op = OPERATIONS.get((case.method, case.template), {})
    url, kwargs = build_request(case, op, seed)
    headers = _etag_headers(world, case, seed)
    admin_only = (case.method, case.template) in ADMIN_ROUTES
    if prep := POSITIVE_PREP.get((case.method, case.template)):
        prep(world)
    caller = world.act_as(ADMIN, "admin") if admin_only else world.act_as(ALICE)

    response = caller.request(case.method, url, headers=headers, **kwargs)

    expected = 304 if case.variant.endswith("if-none-match") else None
    if expected is not None:
        assert response.status_code == expected, f"{case.id}: {response.text[:300]}"
    else:
        assert 200 <= response.status_code < 300, (
            f"{case.id}: A got {response.status_code} {response.text[:300]}"
        )
    # A must really see something, or B's empty answer would prove nothing.
    reads_json = (
        case.method == "GET"
        and response.status_code == 200
        and "json" in response.headers.get("content-type", "")
    )
    if reads_json and (case.template, case.variant) not in EMPTY_FOR_A:
        assert not _empty(response.json()), f"{case.id}: A's own answer is empty"


@pytest.mark.parametrize(
    "call",
    [
        lambda c, s: c.put(
            f"/api/v1/collection/{s.smart}/item", json={"item_ids": [s.item2]}
        ),
        lambda c, s: c.delete(f"/api/v1/collection/{s.smart}/item/{s.item}"),
    ],
    ids=["put", "delete"],
)
def test_user_b_cannot_edit_a_smart_collections_membership(
    call: Callable[[TestClient, Seed], Response], world: World
) -> None:
    """B gets the 404 of an unknown collection; A gets the smart collection's 409."""
    seed = world.seed()
    ghost = replace(seed, smart=str(uuid.uuid7()))
    before = world.snapshot(seed)

    bob = world.act_as(BOB)
    response = call(bob, seed)
    unknown = call(bob, ghost)

    assert response.status_code == 404, response.text
    assert _shape(response) == _shape(unknown)
    assert world.snapshot(seed) == before
    owner = call(world.act_as(ALICE), seed)
    assert owner.status_code == 409
    assert owner.json()["title"] == "CollectionKindError"


def test_a_collection_condition_naming_a_foreign_collection_reads_like_an_unknown_one(
    world: World,
) -> None:
    """B's smart collection naming A's collection (or A's smart one) reveals nothing."""
    seed = world.seed()
    bob = world.act_as(BOB)

    def create(collection_id: str, mode: str) -> Response:
        condition = {"kind": "collection", "mode": mode, "in": [collection_id]}
        definition = {"v": 1, "where": {"op": "and", "children": [condition]}}
        return bob.post(
            "/api/v1/collection",
            json={"name": f"Mine {mode}", "definition": definition},
        )

    for foreign in (seed.collection, seed.smart):
        for mode in ("any", "none"):
            mine = create(foreign, mode)
            unknown = create(str(uuid.uuid7()), mode)
            assert mine.status_code == unknown.status_code == 201, mine.text
            assert mine.json()["warnings"] == unknown.json()["warnings"]
            assert mine.json()["warnings"], "the stale id is reported"
            count = bob.get(f"/api/v1/collection/{mine.json()['id']}/count")
            assert count.json()["count"] == 0, count.text
