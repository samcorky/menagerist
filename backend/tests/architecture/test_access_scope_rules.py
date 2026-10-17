"""Every route to content is scoped: ports, implementations, use cases and models.

A new content method without a `scope`, a new content use case without the scoped
bases, or a new owned model without `OwnedMixin` fails here, so none can ship
silently unscoped.
"""

import annotationlib
import importlib
import inspect
import pkgutil
from typing import Any

import pytest

from app.entrypoints.api.shared.bridges.collection_items import GraphItemLookup
from app.modules.collections.adapters.persistence.collection_repository import (
    SqlAlchemyCollectionRepository,
)
from app.modules.collections.adapters.persistence.in_memory_collection_repository import (  # noqa: E501
    InMemoryCollectionRepository,
)
from app.modules.collections.adapters.persistence.in_memory_item_lookup import (
    InMemoryItemLookup,
)
from app.modules.collections.adapters.persistence.in_memory_membership_repository import (  # noqa: E501
    InMemoryMembershipRepository,
)
from app.modules.collections.adapters.persistence.membership_repository import (
    SqlAlchemyMembershipRepository,
)
from app.modules.collections.adapters.persistence.models import CollectionModel
from app.modules.collections.ports.collection_repository import CollectionRepository
from app.modules.collections.ports.item_lookup import ItemLookup
from app.modules.collections.ports.membership_repository import MembershipRepository
from app.modules.examples.adapters.persistence.in_memory_installation_repository import (  # noqa: E501
    InMemoryInstallationRepository,
)
from app.modules.examples.adapters.persistence.installation_repository import (
    SqlAlchemyInstallationRepository,
)
from app.modules.examples.adapters.persistence.models import ExampleInstallationModel
from app.modules.examples.ports.installation_repository import InstallationRepository
from app.modules.graph.adapters.persistence.edge_repository import (
    SqlAlchemyEdgeRepository,
)
from app.modules.graph.adapters.persistence.in_memory_edge_repository import (
    InMemoryEdgeRepository,
)
from app.modules.graph.adapters.persistence.in_memory_node_repository import (
    InMemoryNodeRepository,
)
from app.modules.graph.adapters.persistence.models import EdgeModel, NodeModel
from app.modules.graph.adapters.persistence.node_repository import (
    SqlAlchemyNodeRepository,
)
from app.modules.graph.ports.edge_repository import EdgeRepository
from app.modules.graph.ports.node_repository import NodeRepository
from app.modules.media.adapters.persistence.in_memory_media_asset_repository import (
    InMemoryMediaAssetRepository,
)
from app.modules.media.adapters.persistence.in_memory_media_attachment_repository import (  # noqa: E501
    InMemoryMediaAttachmentRepository,
)
from app.modules.media.adapters.persistence.media_asset_repository import (
    SqlAlchemyMediaAssetRepository,
)
from app.modules.media.adapters.persistence.media_attachment_repository import (
    SqlAlchemyMediaAttachmentRepository,
)
from app.modules.media.adapters.persistence.models import MediaAssetModel
from app.modules.media.ports.media_asset_repository import MediaAssetRepository
from app.modules.media.ports.media_attachment_repository import (
    MediaAttachmentRepository,
)
from app.platform.database import Base
from app.platform.orm_mixins import OwnedMixin
from app.shared_kernel.cqrs import (
    AuthorisedCommandHandler,
    AuthorisedQueryHandler,
    AuthorisedUseCase,
    ScopedCommandHandler,
    ScopedQueryHandler,
    UseCase,
)

# Port methods that take no scope, per port, and why. Anything else must take
# `scope`; an entry naming a method the port no longer has fails as stale.
_CLAIM = "system job that assigns owners to ownerless rows; reads no content"
_ADD = "persists a new entity; the use case stamps the owner"
_SAVE = "persists an entity already fetched through a scoped read"
NO_SCOPE_NEEDED: dict[type, dict[str, str]] = {
    NodeRepository: {"add": _ADD, "save": _SAVE, "claim_orphaned": _CLAIM},
    EdgeRepository: {"add": _ADD, "save": _SAVE, "claim_orphaned": _CLAIM},
    CollectionRepository: {"add": _ADD, "save": _SAVE, "claim_orphaned": _CLAIM},
    MembershipRepository: {
        "add": "links ids the use case already checked in scope",
        "remove": "unlinks ids the use case already checked in scope",
    },
    ItemLookup: {},
    MediaAssetRepository: {
        "add": _ADD,
        "save": _SAVE,
        "delete": "removes an asset the use case already fetched through a scope",
        "claim_orphaned": _CLAIM,
    },
    MediaAttachmentRepository: {
        "lock_target": "takes a lock and returns nothing",
        "add": "persists an attachment after the asset and target were checked",
        "update": "persists an attachment fetched through its asset's scope",
        "delete": "removes an attachment fetched through its asset's scope",
    },
    InstallationRepository: {"add": _ADD, "save": _SAVE, "claim_orphaned": _CLAIM},
}

# Each port with its in-memory twin and its SQL (or bridge) implementation.
PORTS: list[tuple[type, tuple[type, ...]]] = [
    (NodeRepository, (InMemoryNodeRepository, SqlAlchemyNodeRepository)),
    (EdgeRepository, (InMemoryEdgeRepository, SqlAlchemyEdgeRepository)),
    (
        CollectionRepository,
        (InMemoryCollectionRepository, SqlAlchemyCollectionRepository),
    ),
    (
        MembershipRepository,
        (InMemoryMembershipRepository, SqlAlchemyMembershipRepository),
    ),
    (ItemLookup, (InMemoryItemLookup, GraphItemLookup)),
    (
        MediaAssetRepository,
        (InMemoryMediaAssetRepository, SqlAlchemyMediaAssetRepository),
    ),
    (
        MediaAttachmentRepository,
        (InMemoryMediaAttachmentRepository, SqlAlchemyMediaAttachmentRepository),
    ),
    (
        InstallationRepository,
        (InMemoryInstallationRepository, SqlAlchemyInstallationRepository),
    ),
]
IMPLEMENTATIONS = [(port, impl) for port, impls in PORTS for impl in impls]


def _public_methods(cls: type) -> dict[str, Any]:
    return {
        name: member
        for name, member in inspect.getmembers(cls, inspect.isfunction)
        if not name.startswith("_")
    }


def _signature(function: Any) -> inspect.Signature:  # noqa: ANN401
    """The signature with annotations as text (some live under TYPE_CHECKING)."""
    return inspect.signature(function, annotation_format=annotationlib.Format.STRING)


def _has_access_scope(function: Any) -> bool:  # noqa: ANN401
    parameter = _signature(function).parameters.get("scope")
    return parameter is not None and parameter.annotation == "AccessScope"


@pytest.mark.parametrize("port", [p for p, _ in PORTS], ids=lambda p: p.__name__)
def test_every_port_method_takes_an_access_scope(port: type) -> None:
    """A port method that is not a known no-content write needs `scope: AccessScope`."""
    missing = [
        name
        for name, method in _public_methods(port).items()
        if name not in NO_SCOPE_NEEDED[port] and not _has_access_scope(method)
    ]
    assert missing == [], f"{port.__name__} methods without scope: AccessScope"


@pytest.mark.parametrize("port", [p for p, _ in PORTS], ids=lambda p: p.__name__)
def test_scope_exemptions_are_current(port: type) -> None:
    """An exemption must name a real method that does not take a scope."""
    methods = _public_methods(port)
    stale = set(NO_SCOPE_NEEDED[port]) - set(methods)
    assert stale == set()
    scoped = [
        name
        for name in NO_SCOPE_NEEDED[port]
        if "scope" in _signature(methods[name]).parameters
    ]
    assert scoped == [], f"{port.__name__} exempts methods that already take scope"


@pytest.mark.parametrize(
    ("port", "implementation"), IMPLEMENTATIONS, ids=lambda c: c.__name__
)
def test_implementations_mirror_the_port_scope(
    port: type, implementation: type
) -> None:
    """The in-memory and SQL implementations match the port's parameters exactly."""
    methods = _public_methods(implementation)
    drift = []
    for name, port_method in _public_methods(port).items():
        impl_method = methods.get(name)
        if impl_method is None:
            drift.append(f"{name}: not implemented")
            continue
        want = [(p.name, p.kind) for p in _signature(port_method).parameters.values()]
        got = [(p.name, p.kind) for p in _signature(impl_method).parameters.values()]
        if want != got:
            drift.append(f"{name}: parameters {got} != port {want}")
        if name not in NO_SCOPE_NEEDED[port] and not _has_access_scope(impl_method):
            drift.append(f"{name}: scope is not annotated AccessScope")
    assert drift == [], f"{implementation.__name__} drifts from {port.__name__}"


# Use cases that carry no per-person content, and why. Every other use case in
# the content modules must extend a scoped or authorised base.
UNSCOPED_USE_CASES = {
    # Item-type and relationship-type vocabulary is shared by every member
    # (decision 6); only deleting/purging it is admin-only (an authorised base).
    "CreateNodeType": "shared vocabulary",
    "GetNodeType": "shared vocabulary",
    "ListNodeTypes": "shared vocabulary",
    "ValidateQuery": "reads item type schemas only; touches no items",
    "UpdateNodeType": "shared vocabulary",
    "CreateEdgeType": "shared vocabulary",
    "GetEdgeType": "shared vocabulary",
    "ListEdgeTypes": "shared vocabulary",
    "UpdateEdgeType": "shared vocabulary",
    # Creates an owned row stamped from the actor; reads no existing content.
    "StageMedia": "creates a staged upload owned by the actor",
    # System-actor jobs run once by the first-admin claim: assign owners only.
    "ClaimOrphanedItems": "first-admin claim",
    "ClaimLegacyCollections": "first-admin claim",
    "ClaimOrphanedMedia": "first-admin claim",
    "ClaimOrphanedInstallations": "first-admin claim",
}
SAFE_BASES = (
    ScopedCommandHandler,
    ScopedQueryHandler,
    AuthorisedCommandHandler,
    AuthorisedQueryHandler,
    AuthorisedUseCase,
)
CONTENT_MODULES = ("graph", "collections", "media", "examples")


def _use_cases() -> dict[str, type]:
    found: dict[str, type] = {}
    for module in CONTENT_MODULES:
        package = importlib.import_module(f"app.modules.{module}.application")
        for info in pkgutil.walk_packages(package.__path__, f"{package.__name__}."):
            loaded = importlib.import_module(info.name)
            for name, cls in inspect.getmembers(loaded, inspect.isclass):
                if (
                    cls.__module__ == loaded.__name__
                    and issubclass(cls, UseCase)
                    and not inspect.isabstract(cls)
                ):
                    found[name] = cls
    return found


def test_every_content_use_case_is_scoped_or_excluded() -> None:
    """A use case without a scoped/authorised base and not excluded fails."""
    unscoped = sorted(
        name
        for name, cls in _use_cases().items()
        if not issubclass(cls, SAFE_BASES) and name not in UNSCOPED_USE_CASES
    )
    assert unscoped == [], "extend ScopedCommandHandler/ScopedQueryHandler"


def test_exclusions_are_current() -> None:
    """An excluded use case must exist and must not already be scoped."""
    cases = _use_cases()
    stale = sorted(
        name
        for name in UNSCOPED_USE_CASES
        if name not in cases or issubclass(cases[name], SAFE_BASES)
    )
    assert stale == []


# Content models carry the owner column through the shared mixin.
OWNED_MODELS = (NodeModel, EdgeModel, MediaAssetModel, ExampleInstallationModel)
# `CollectionModel.owner_id` is NOT NULL (every collection has an owner from the
# start), so it declares its own column instead of the nullable mixin.
OWNER_COLUMN_WITHOUT_MIXIN = (CollectionModel,)


@pytest.mark.parametrize("model", OWNED_MODELS, ids=lambda m: m.__name__)
def test_content_models_carry_the_owned_mixin(model: type) -> None:
    """Content rows have an owner column through `OwnedMixin`."""
    assert issubclass(model, OwnedMixin)


def test_every_model_with_an_owner_column_is_known() -> None:
    """A new model with `owner_id` must use the mixin or be listed here."""
    unknown = sorted(
        mapper.class_.__name__
        for mapper in Base.registry.mappers
        if "owner_id" in mapper.columns
        and not issubclass(mapper.class_, OwnedMixin)
        and mapper.class_ not in OWNER_COLUMN_WITHOUT_MIXIN
    )
    assert unknown == []
