from app.entrypoints.api.shared.permissions import ALL_PERMISSIONS, IMPLIES, expand
from app.modules.graph.application.permissions import GraphPermission

A = GraphPermission.DELETE_NODE_TYPE
B = GraphPermission.DELETE_EDGE_TYPE
C = GraphPermission.PURGE_NODE_TYPE_ATTRIBUTE
D = GraphPermission.PURGE_EDGE_TYPE_ATTRIBUTE


def test_expand_without_implications_returns_the_grant() -> None:
    """With an empty catalogue nothing is added."""
    assert expand({A}, {}) == frozenset({A})
    assert expand(set(), {}) == frozenset()


def test_expand_follows_implications_transitively() -> None:
    """A implies B and B implies C, so A grants all three."""
    implies = {A: frozenset({B}), B: frozenset({C})}
    assert expand({A}, implies) == frozenset({A, B, C})
    assert expand({B}, implies) == frozenset({B, C})
    assert D not in expand({A}, implies)


def test_expand_terminates_on_a_cycle() -> None:
    """A cyclic catalogue still closes without looping."""
    implies = {A: frozenset({B}), B: frozenset({A})}
    assert expand({A}, implies) == frozenset({A, B})


def test_the_real_catalogue_lists_the_four_graph_permissions() -> None:
    """The aggregate catalogue is the union of every module's enum."""
    assert frozenset(GraphPermission) == ALL_PERMISSIONS


def test_the_real_catalogue_has_no_cycles() -> None:
    """No permission transitively implies itself."""
    for permission in IMPLIES:
        reached: set[GraphPermission] = set()
        frontier = set(IMPLIES[permission])
        while frontier:
            current = frontier.pop()
            assert current != permission
            if current not in reached:
                reached.add(current)
                frontier |= IMPLIES.get(current, frozenset())


def test_every_implied_permission_exists() -> None:
    """Implications only name permissions the catalogue knows."""
    for source, targets in IMPLIES.items():
        assert source in ALL_PERMISSIONS
        assert targets <= ALL_PERMISSIONS
