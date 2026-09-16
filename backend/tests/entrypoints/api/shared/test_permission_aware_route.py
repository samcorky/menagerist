from enum import StrEnum
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI
from starlette.testclient import TestClient

from app.entrypoints.api.shared.permission_aware_route import (
    PermissionAwareRoute,
    _find_use_case_type,
)
from app.shared_kernel.actor import SYSTEM_ACTOR, Actor
from app.shared_kernel.cqrs import UseCase


class Permission(StrEnum):
    """Dummy permission enum for testing."""

    GRAPH_READ = "graph:read"


class DocumentedUseCase(UseCase[object, str]):
    """Use case with a statically discoverable required permission."""

    required_permission = Permission.GRAPH_READ

    async def handle(self, request: object, actor: Actor) -> str:
        """Handle the documented use case."""
        return "ok"


class PlainUseCase(UseCase[object, str]):
    """Use case with no documented permission."""

    async def handle(self, request: object, actor: Actor) -> str:
        """Handle the plain use case."""
        return "ok"


def get_documented_use_case() -> DocumentedUseCase:
    """Return an instance of the documented use case."""
    return DocumentedUseCase()


def get_plain_use_case() -> PlainUseCase:
    """Return an instance of the plain use case."""
    return PlainUseCase()


async def documented_endpoint(
    use_case: Annotated[DocumentedUseCase, Depends(get_documented_use_case)],
) -> dict[str, str]:
    """Documented endpoint."""
    return {"result": await use_case.handle(object(), SYSTEM_ACTOR)}


async def plain_endpoint(
    use_case: Annotated[PlainUseCase, Depends(get_plain_use_case)],
) -> dict[str, str]:
    """Plain endpoint."""
    return {"result": await use_case.handle(object(), SYSTEM_ACTOR)}


def test_find_use_case_type_returns_annotated_use_case_type() -> None:
    """Use-case type discovery reads Annotated route dependencies."""
    assert _find_use_case_type(documented_endpoint) is DocumentedUseCase


def test_openapi_documents_required_permission() -> None:
    """PermissionAwareRoute adds security, vendor metadata, and visible docs."""
    app = FastAPI()
    router = APIRouter(route_class=PermissionAwareRoute)
    router.get("/documented", operation_id="documented_endpoint")(documented_endpoint)
    app.include_router(router)

    schema = TestClient(app).get("/openapi.json").json()
    operation = schema["paths"]["/documented"]["get"]

    assert operation["x-required-permission"] == "graph:read"
    assert "**Requires permission:** `graph:read`" in operation["description"]
    assert operation["security"] == [{"APIKeyCookie": []}]
    assert schema["components"]["securitySchemes"]["APIKeyCookie"] == {
        "type": "apiKey",
        "in": "cookie",
        "name": "session_id",
    }


def test_openapi_leaves_plain_use_cases_unchanged() -> None:
    """Routes without a statically declared permission are not marked secured."""
    app = FastAPI()
    router = APIRouter(route_class=PermissionAwareRoute)
    router.get("/plain", operation_id="plain_endpoint")(plain_endpoint)
    app.include_router(router)

    schema = TestClient(app).get("/openapi.json").json()
    operation = schema["paths"]["/plain"]["get"]

    assert "x-required-permission" not in operation
    assert operation["description"] == "Plain endpoint."
    assert "security" not in operation
    assert "securitySchemes" not in schema.get("components", {})
