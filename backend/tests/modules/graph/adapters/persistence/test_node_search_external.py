"""Media and collection conditions: one table of scenarios, both adapters.

The in-memory evaluator is the reference; the Postgres run goes through the
real bridge over the media and collections tables.
"""

import uuid
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

import pytest

from app.entrypoints.api.shared.bridges.collection_conditions import (
    build_search_graph_repos,
)
from app.modules.collections.adapters.persistence.collection_repository import (
    SqlAlchemyCollectionRepository,
)
from app.modules.collections.adapters.persistence.membership_repository import (
    SqlAlchemyMembershipRepository,
)
from app.modules.collections.domain.collection import Collection, Membership
from app.modules.graph.adapters.persistence.in_memory_external_conditions import (
    InMemoryExternalConditions,
)
from app.modules.graph.adapters.persistence.in_memory_node_repository import (
    InMemoryNodeRepository,
)
from app.modules.graph.application.collection_expansion import GONE
from app.modules.graph.application.prepare_query import prepare_query
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.query import InvalidQueryError
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.modules.media.adapters.persistence.models import (
    MediaAssetModel,
    MediaAttachmentModel,
)
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.slug import Slug

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.ext.asyncio import AsyncSession

ALICE = uuid.UUID(int=201)
BOB = uuid.UUID(int=202)
TODAY = date(2026, 10, 18)
NOW = datetime(2026, 10, 18, tzinfo=UTC)


def _cid(number: int) -> uuid.UUID:
    return uuid.UUID(int=0xC0110000 + number)


C_A, C_B, C_BOB, C_GONE = _cid(1), _cid(2), _cid(3), _cid(4)
S_FAV, S_NESTED, S_BOB, S_ALL = _cid(5), _cid(6), _cid(7), _cid(8)
CYC1, CYC2, S_SELF = _cid(9), _cid(10), _cid(11)
D1, D2, D3, D4 = _cid(12), _cid(13), _cid(14), _cid(15)
UNKNOWN = _cid(99)

ALL_ALICE = {"photo", "doc", "signed", "staged", "orphaned", "bare", "foreign"}


def _where(*children: dict[str, Any], op: str = "and") -> dict[str, Any]:
    return {"v": 1, "where": {"op": op, "children": list(children)}}


def _media(mode: str, kind: str | None = None) -> dict[str, Any]:
    cond: dict[str, Any] = {"kind": "media", "mode": mode}
    if kind is not None:
        cond["type"] = kind
    return cond


def _in(mode: str, *ids: uuid.UUID) -> dict[str, Any]:
    return {"kind": "collection", "mode": mode, "in": [str(i) for i in ids]}


def _not(child: dict[str, Any]) -> dict[str, Any]:
    return {"op": "not", "children": [child]}


_FAV = {"kind": "favourite", "value": True}

# Smart collections: id -> (owner, definition).
SMART: dict[uuid.UUID, tuple[uuid.UUID, dict[str, Any]]] = {
    S_FAV: (ALICE, _where(_FAV)),
    S_NESTED: (ALICE, _where(_in("any", C_A), _in("any", S_FAV), op="or")),
    S_BOB: (BOB, _where(_FAV)),
    S_ALL: (ALICE, {"v": 1, "where": None}),
    CYC1: (ALICE, _where(_in("any", CYC2))),
    CYC2: (ALICE, _where(_in("any", CYC1))),
    S_SELF: (ALICE, _where(_in("any", S_SELF))),
    D1: (ALICE, _where(_in("any", D2))),
    D2: (ALICE, _where(_in("any", D3))),
    D3: (ALICE, _where(_in("any", D4))),
    D4: (ALICE, _where(_FAV)),
}

# Manual collections: id -> (owner, member names, deleted).
MANUAL: dict[uuid.UUID, tuple[uuid.UUID, set[str], bool]] = {
    C_A: (ALICE, {"photo", "bare"}, False),
    C_B: (ALICE, {"doc", "bobs"}, False),
    C_BOB: (BOB, {"photo", "bare", "doc"}, False),
    C_GONE: (ALICE, {"photo"}, True),
}

# Attachments: item -> (asset owner, content type, status, attribute key).
ATTACHMENTS: dict[str, tuple[uuid.UUID, str, str, str | None]] = {
    "photo": (ALICE, "image/png", "attached", None),
    "doc": (ALICE, "application/pdf", "attached", None),
    "signed": (ALICE, "image/jpeg", "attached", "signature"),
    "staged": (ALICE, "image/png", "staged", None),
    "orphaned": (ALICE, "image/png", "orphaned", None),
    "foreign": (BOB, "image/png", "attached", None),
    "bobs": (BOB, "image/png", "attached", None),
}

_ITEMS = [(name, ALICE) for name in sorted(ALL_ALICE)] + [("bobs", BOB)]

CASES: list[tuple[str, dict[str, Any], set[str], uuid.UUID]] = [
    ("media has", _where(_media("has")), {"photo", "doc", "signed"}, ALICE),
    (
        "media none includes staged, orphaned, foreign and bare",
        _where(_media("none")),
        ALL_ALICE - {"photo", "doc", "signed"},
        ALICE,
    ),
    (
        "media has image",
        _where(_media("has", "image")),
        {"photo", "signed"},
        ALICE,
    ),
    ("media has document", _where(_media("has", "document")), {"doc"}, ALICE),
    (
        "media none image",
        _where(_media("none", "image")),
        ALL_ALICE - {"photo", "signed"},
        ALICE,
    ),
    (
        "media none document",
        _where(_media("none", "document")),
        ALL_ALICE - {"doc"},
        ALICE,
    ),
    (
        "not media has equals media none",
        _where(_not(_media("has"))),
        ALL_ALICE - {"photo", "doc", "signed"},
        ALICE,
    ),
    ("media has with favourite", _where(_media("has"), _FAV), {"photo"}, ALICE),
    ("media never counts another owner's items", _where(_media("has")), {"bobs"}, BOB),
    ("in collection any", _where(_in("any", C_A)), {"photo", "bare"}, ALICE),
    (
        "in collection none",
        _where(_in("none", C_A)),
        ALL_ALICE - {"photo", "bare"},
        ALICE,
    ),
    (
        "in collection any of two ignores another owner's items",
        _where(_in("any", C_A, C_B)),
        {"photo", "bare", "doc"},
        ALICE,
    ),
    (
        "another owner's collection matches nothing",
        _where(_in("any", C_BOB)),
        set(),
        ALICE,
    ),
    (
        "not in another owner's collection matches nothing, like an unknown id",
        _where(_in("none", C_BOB)),
        set(),
        ALICE,
    ),
    (
        "an unknown collection matches nothing",
        _where(_in("any", UNKNOWN)),
        set(),
        ALICE,
    ),
    (
        "not in an unknown collection matches nothing",
        _where(_in("none", UNKNOWN)),
        set(),
        ALICE,
    ),
    ("a deleted collection matches nothing", _where(_in("any", C_GONE)), set(), ALICE),
    (
        "a live id still works beside an unknown one",
        _where(_in("any", C_A, UNKNOWN)),
        {"photo", "bare"},
        ALICE,
    ),
    (
        "not in a live id beside an unknown one",
        _where(_in("none", C_A, UNKNOWN)),
        ALL_ALICE - {"photo", "bare"},
        ALICE,
    ),
    ("smart collection is inlined", _where(_in("any", S_FAV)), {"photo"}, ALICE),
    (
        "smart collection can reference others",
        _where(_in("any", S_NESTED)),
        {"photo", "bare"},
        ALICE,
    ),
    (
        "not in a smart collection",
        _where(_in("none", S_NESTED)),
        ALL_ALICE - {"photo", "bare"},
        ALICE,
    ),
    (
        "another owner's smart collection matches nothing",
        _where(_in("any", S_BOB)),
        set(),
        ALICE,
    ),
    (
        "a smart collection without a filter holds everything",
        _where(_in("any", S_ALL)),
        ALL_ALICE,
        ALICE,
    ),
    ("a cycle degrades to nothing", _where(_in("any", CYC1)), set(), ALICE),
    ("self reference degrades to nothing", _where(_in("any", S_SELF)), set(), ALICE),
    ("too deep a chain degrades to nothing", _where(_in("any", D1)), set(), ALICE),
    ("a chain within the limit works", _where(_in("any", D2)), {"photo"}, ALICE),
    (
        "collection and media combine",
        _where(_media("none"), _in("any", C_A)),
        {"bare"},
        ALICE,
    ),
    (
        "not in collection inside not",
        _where(_not(_in("any", C_A))),
        ALL_ALICE - {"photo", "bare"},
        ALICE,
    ),
    ("nobody else sees Alice's collection", _where(_in("any", C_A)), set(), BOB),
]


async def _seed_memory(provider: InMemoryExternalConditions) -> GraphRepos:
    nodes = InMemoryNodeRepository(provider)
    ids: dict[str, uuid.UUID] = {}
    for name, owner in _ITEMS:
        node = Node.create(owner_id=owner, name=name, type="thing")
        node.favourite = name == "photo"
        ids[name] = node.id
        await nodes.add(node)
        if name in ATTACHMENTS:
            asset_owner, content_type, status, _ = ATTACHMENTS[name]
            provider.add_attachment(
                node.id, owner_id=asset_owner, content_type=content_type, status=status
            )
    for cid, (owner, members, deleted) in MANUAL.items():
        provider.add_collection(
            cid,
            owner_id=owner,
            members=[ids[m] for m in members],
            deleted=deleted,
        )
    for cid, (owner, definition) in SMART.items():
        provider.add_collection(cid, owner_id=owner, definition=definition)
    return _repos(nodes, provider)


def _repos(nodes: Any, provider: InMemoryExternalConditions | None) -> GraphRepos:  # noqa: ANN401
    return GraphRepos(
        nodes=nodes,
        edges=None,  # type: ignore[arg-type]
        node_types=_NoTypes(),  # type: ignore[arg-type]
        edge_types=None,  # type: ignore[arg-type]
        external=provider,
        definitions=provider,
    )


class _NoTypes:
    async def list(self, *, after: Any, limit: int) -> list[Any]:  # noqa: ANN401
        return []


async def _seed_postgres(session: AsyncSession) -> GraphRepos:
    repos = build_search_graph_repos(session)
    ids: dict[str, uuid.UUID] = {}
    for name, owner in _ITEMS:
        node = Node.create(owner_id=owner, name=name, type="thing")
        node.favourite = name == "photo"
        ids[name] = node.id
        await repos.nodes.add(node)
        if name in ATTACHMENTS:
            asset_owner, content_type, status, key = ATTACHMENTS[name]
            asset_id = uuid.uuid7()
            session.add(
                MediaAssetModel(
                    id=asset_id,
                    owner_id=asset_owner,
                    filename=f"{name}.bin",
                    content_type=content_type,
                    size=1,
                    sha256="0" * 64,
                    status=status,
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
            await session.flush()
            session.add(
                MediaAttachmentModel(
                    id=uuid.uuid7(),
                    asset_id=asset_id,
                    target_type="node",
                    target_id=node.id,
                    attribute_key=key,
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
    collections = SqlAlchemyCollectionRepository(session)
    memberships = SqlAlchemyMembershipRepository(session)
    definitions: dict[uuid.UUID, tuple[uuid.UUID, dict[str, Any] | None, bool]] = {
        **{cid: (owner, None, deleted) for cid, (owner, _, deleted) in MANUAL.items()},
        **{cid: (owner, d, False) for cid, (owner, d) in SMART.items()},
    }
    for cid, (owner, definition, deleted) in definitions.items():
        collection = Collection.create(
            name=f"c{cid.int & 0xFF}",
            slug=Slug(f"c{cid.int & 0xFF}"),
            owner_id=owner,
            definition=definition,
        )
        collection.id = cid
        if deleted:
            collection.soft_delete()
        await collections.add(collection)
    for cid, (_, members, _) in MANUAL.items():
        for member in members:
            await memberships.add(
                Membership(collection_id=cid, item_id=ids[member], added_at=NOW)
            )
    return repos


@pytest.fixture(
    params=["in_memory", pytest.param("postgres", marks=pytest.mark.integration)]
)
def seed(request: pytest.FixtureRequest) -> Callable[[], Awaitable[GraphRepos]]:
    """Seeds the same world on either adapter; awaiting it gives the repositories."""
    if request.param == "in_memory":
        return lambda: _seed_memory(InMemoryExternalConditions())
    session = request.getfixturevalue("db_session")
    return lambda: _seed_postgres(session)


async def _names(repos: GraphRepos, raw: dict[str, Any], user: uuid.UUID) -> set[str]:
    scope = ContentFilter.of(user)
    resolved, _ = await prepare_query(repos, raw, TODAY, scope=scope)
    hits = await repos.nodes.search(
        scope=scope, resolved=resolved, after=None, limit=100
    )
    counted = await repos.nodes.search_count(scope=scope, resolved=resolved)
    assert counted == len(hits)
    return {hit.node.name for hit in hits}


@pytest.mark.parametrize(
    ("label", "raw", "expected", "user"), CASES, ids=[c[0] for c in CASES]
)
async def test_scenario(
    seed: Callable[[], Awaitable[GraphRepos]],
    label: str,
    raw: dict[str, Any],
    expected: set[str],
    user: uuid.UUID,
) -> None:
    """Each scenario gives the same answer on both adapters."""
    repos = await seed()
    assert await _names(repos, raw, user) == expected


_P = "where.children[0]"
_CYCLE_PATH = f"{_P}.in[0].children[0].in[0].children[0].in[0]"
_DEEP_PATH = f"{_P}.in[0]" + ".children[0].in[0]" * 3

WARNINGS: list[tuple[str, dict[str, Any], list[tuple[str, str]]]] = [
    ("a live manual collection", _where(_in("any", C_A)), []),
    ("an unknown collection", _where(_in("any", UNKNOWN)), [(f"{_P}.in[0]", GONE)]),
    ("a deleted collection", _where(_in("none", C_GONE)), [(f"{_P}.in[0]", GONE)]),
    (
        "another owner's collection reads like an unknown one",
        _where(_in("any", C_BOB)),
        [(f"{_P}.in[0]", GONE)],
    ),
    (
        "a cycle",
        _where(_in("any", CYC1)),
        [(_CYCLE_PATH, "That collection refers back to itself.")],
    ),
    (
        "a chain that is too deep",
        _where(_in("any", D1)),
        [(_DEEP_PATH, "Collections are nested too deeply.")],
    ),
    (
        "the second of two ids",
        _where(_in("any", C_A, UNKNOWN)),
        [(f"{_P}.in[1]", GONE)],
    ),
]


@pytest.mark.parametrize(
    ("label", "raw", "expected"), WARNINGS, ids=[w[0] for w in WARNINGS]
)
async def test_warnings(
    seed: Callable[[], Awaitable[GraphRepos]],
    label: str,
    raw: dict[str, Any],
    expected: list[tuple[str, str]],
) -> None:
    """Stale collections warn with the path of the id, never revealing why."""
    repos = await seed()
    _, warnings = await prepare_query(repos, raw, TODAY, scope=ContentFilter.of(ALICE))
    assert [(w.path, w.message) for w in warnings] == expected


@pytest.mark.parametrize(
    ("label", "ids", "self_id"),
    [
        ("directly", (CYC1,), CYC1),
        ("through another collection", (CYC2,), CYC1),
        ("through a chain", (D1,), D4),
    ],
)
async def test_saving_a_collection_that_reaches_itself_is_refused(
    seed: Callable[[], Awaitable[GraphRepos]],
    label: str,
    ids: tuple[uuid.UUID, ...],
    self_id: uuid.UUID,
) -> None:
    """A reference back to the collection being saved is a 400 naming the path."""
    repos = await seed()
    with pytest.raises(InvalidQueryError, match="refer to itself") as caught:
        await prepare_query(
            repos,
            _where(_in("any", *ids)),
            TODAY,
            scope=ContentFilter.of(ALICE),
            self_id=self_id,
        )
    assert caught.value.path.startswith(_P)
    assert str(self_id) in str(caught.value)


async def test_without_a_provider_external_conditions_match_nothing_and_warn() -> None:
    """No provider: media and manual collections match nothing, with a warning."""
    nodes = InMemoryNodeRepository()
    await nodes.add(Node.create(owner_id=ALICE, name="x", type="thing"))
    repos = _repos(nodes, None)
    scope = ContentFilter.of(ALICE)

    for raw in (_where(_media("none")), _where(_in("none", C_A))):
        resolved, warnings = await prepare_query(repos, raw, TODAY, scope=scope)
        hits = await nodes.search(scope=scope, resolved=resolved, after=None, limit=9)
        assert hits == []
        assert warnings
