from typing import Self

from app.shared_kernel.permission import PermissionEnum


class GraphPermission(PermissionEnum):
    """Permissions for graph operations.

    Item and type permissions are held by members; the rest affect every user's
    content and are admin-only. Values read `<module>:<resource>:<action>`.
    """

    ITEM_READ = "graph:item:read"
    ITEM_WRITE = "graph:item:write"
    TYPE_READ = "graph:type:read"
    TYPE_WRITE = "graph:type:write"
    DELETE_NODE_TYPE = "graph:node_type:delete"
    DELETE_EDGE_TYPE = "graph:edge_type:delete"
    PURGE_NODE_TYPE_ATTRIBUTE = "graph:node_type:purge_attribute"
    PURGE_EDGE_TYPE_ATTRIBUTE = "graph:edge_type:purge_attribute"

    def implied(self) -> frozenset[Self]:
        """Return what holding this permission also grants."""
        cls = type(self)
        if self is cls.ITEM_WRITE:
            return frozenset({cls.ITEM_READ})
        if self is cls.TYPE_WRITE:
            return frozenset({cls.TYPE_READ})
        return frozenset()
