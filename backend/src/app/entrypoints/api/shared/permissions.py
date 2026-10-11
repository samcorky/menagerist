from itertools import chain
from typing import TYPE_CHECKING

from app.modules.graph.application.permissions import (
    IMPLIES as GRAPH_IMPLIES,
    GraphPermission,
)
from app.modules.identity.application.permissions import (
    IMPLIES as IDENTITY_IMPLIES,
    IdentityPermission,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

# Adding a module's permissions is one line here: `| MediaPermission`.
Permission = GraphPermission | IdentityPermission

ALL_PERMISSIONS: frozenset[Permission] = frozenset(
    chain(GraphPermission, IdentityPermission)
)

IMPLIES: Mapping[Permission, frozenset[Permission]] = {
    key: frozenset(implied)
    for catalogue in (GRAPH_IMPLIES, IDENTITY_IMPLIES)
    for key, implied in catalogue.items()
}


def expand(
    granted: Iterable[Permission],
    implies: Mapping[Permission, frozenset[Permission]] = IMPLIES,
) -> frozenset[Permission]:
    """Return `granted` plus everything it transitively implies."""
    result = set(granted)
    pending = list(result)
    while pending:
        for implied in implies.get(pending.pop(), frozenset()):
            if implied not in result:
                result.add(implied)
                pending.append(implied)
    return frozenset(result)
