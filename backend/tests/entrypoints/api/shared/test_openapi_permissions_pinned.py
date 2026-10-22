from app.entrypoints.api import create_app

# Pinned before the access refactor: the operations documented as needing a
# permission must not change when use cases migrate to declared access stances.
EXPECTED: dict[tuple[str, str], str] = {
    ("/api/browser-check", "post"): "system:diagnostics:read",
    ("/api/health/ready/detail", "get"): "system:diagnostics:read",
    ("/api/v1/backup", "get"): "backup:archive:read",
    ("/api/v1/backup", "post"): "backup:archive:create",
    ("/api/v1/backup/prune", "post"): "backup:archive:delete",
    ("/api/v1/backup/upload", "post"): "backup:archive:create",
    ("/api/v1/backup/{backup_id}", "delete"): "backup:archive:delete",
    ("/api/v1/backup/{backup_id}/download", "get"): "backup:archive:read",
    ("/api/v1/backup/{backup_id}/verify", "post"): "backup:archive:read",
    ("/api/v1/edge-type", "get"): "graph:type:read",
    ("/api/v1/edge-type", "post"): "graph:type:write",
    ("/api/v1/edge-type/{edge_type_id}", "delete"): "graph:edge_type:delete",
    ("/api/v1/edge-type/{edge_type_id}", "get"): "graph:type:read",
    ("/api/v1/edge-type/{edge_type_id}", "patch"): "graph:type:write",
    ("/api/v1/edge-type/{edge_type_id}/attribute/{key}", "delete"): (
        "graph:edge_type:purge_attribute"
    ),
    ("/api/v1/node-type", "get"): "graph:type:read",
    ("/api/v1/node-type", "post"): "graph:type:write",
    ("/api/v1/node-type/{node_type_id}", "delete"): "graph:node_type:delete",
    ("/api/v1/node-type/{node_type_id}", "get"): "graph:type:read",
    ("/api/v1/node-type/{node_type_id}", "patch"): "graph:type:write",
    ("/api/v1/node-type/{node_type_id}/attribute/{key}", "delete"): (
        "graph:node_type:purge_attribute"
    ),
    ("/api/v1/session", "get"): "identity:session:list",
    ("/api/v1/session/{session_id}", "delete"): "identity:session:revoke",
    ("/api/v1/user", "get"): "identity:user:list",
    ("/api/v1/user", "post"): "identity:user:create",
    ("/api/v1/user/{user_id}", "patch"): "identity:user:update",
    ("/api/v1/user/{user_id}/password", "post"): "identity:user:reset_password",
    ("/api/v1/user/{user_id}/unlock", "post"): "identity:user:unlock",
    ("/api/version/detail", "get"): "system:diagnostics:read",
}


def test_documented_permissions_are_unchanged() -> None:
    """Exactly the pinned operations carry `x-required-permission`."""
    paths = create_app().openapi()["paths"]
    live = {
        (path, method): operation["x-required-permission"]
        for path, operations in paths.items()
        for method, operation in operations.items()
        if "x-required-permission" in operation
    }
    assert live == EXPECTED


def test_other_operations_document_no_permission() -> None:
    """Operations outside the pin carry no permission description."""
    paths = create_app().openapi()["paths"]
    for path, operations in paths.items():
        for method, operation in operations.items():
            if (path, method) in EXPECTED:
                continue
            assert "Requires permission" not in operation.get("description", "")
