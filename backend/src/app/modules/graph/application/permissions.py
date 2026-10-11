from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping


class GraphPermission(StrEnum):
    """Permissions for graph operations that affect every user's content.

    Values read `<module>:<resource>:<action>`.
    """

    DELETE_NODE_TYPE = "graph:node_type:delete"
    DELETE_EDGE_TYPE = "graph:edge_type:delete"
    PURGE_NODE_TYPE_ATTRIBUTE = "graph:node_type:purge_attribute"
    PURGE_EDGE_TYPE_ATTRIBUTE = "graph:edge_type:purge_attribute"


# Holding the key also grants the values. None yet.
IMPLIES: Mapping[GraphPermission, frozenset[GraphPermission]] = {}
