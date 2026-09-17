from enum import StrEnum
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI
from starlette.testclient import TestClient

from app.entrypoints.api.shared.permission_aware_route import (
    PermissionAwareRoute,
    _find_use_case_type,
)
from app.shared_kernel.actor import SYSTEM_ACTOR, Actor
from app.shared_kernel.cqrs import CommandHandler, QueryHandler, UseCase


class Permission(StrEnum):
    """Dummy permission enum for testing."""

    GRAPH_READ = "graph:read"
    GRAPH_WRITE = "graph:write"


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


class ReadUseCase(QueryHandler[object, object, str]):
    """Query use case with a documented read permission."""

    required_permission = Permission.GRAPH_READ

    async def handle(self, request: object, actor: Actor) -> str:
        """Handle the read use case."""
        return "ok"


class WriteUseCase(CommandHandler[object, object, str]):
    """Command use case with a documented write permission."""

    required_permission = Permission.GRAPH_WRITE

    async def handle(self, request: object, actor: Actor) -> str:
        """Handle the write use case."""
        return "ok"


def get_documented_use_case() -> DocumentedUseCase:
    """Return an instance of the documented use case."""
    return DocumentedUseCase()


def get_plain_use_case() -> PlainUseCase:
    """Return an instance of the plain use case."""
    return PlainUseCase()


def get_read_use_case() -> ReadUseCase:
    """Return an instance of the read use case."""
    return ReadUseCase(object())


def get_write_use_case() -> WriteUseCase:
    """Return an instance of the write use case."""
    return WriteUseCase(object())


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


async def read_before_write_endpoint(
    get_use_case: Annotated[ReadUseCase, Depends(get_read_use_case)],
    write_use_case: Annotated[WriteUseCase, Depends(get_write_use_case)],
) -> dict[str, str]:
    """Endpoint declaring its read use case before its write use case."""
    return {"result": await write_use_case.handle(object(), SYSTEM_ACTOR)}


async def write_before_read_endpoint(
    write_use_case: Annotated[WriteUseCase, Depends(get_write_use_case)],
    get_use_case: Annotated[ReadUseCase, Depends(get_read_use_case)],
) -> dict[str, str]:
    """Endpoint declaring its write use case before its read use case."""
    return {"result": await write_use_case.handle(object(), SYSTEM_ACTOR)}


def test_find_use_case_type_returns_annotated_use_case_type() -> None:
    """Use-case type discovery reads Annotated route dependencies."""
    assert _find_use_case_type(documented_endpoint) is DocumentedUseCase


def test_find_use_case_type_prefers_command_handler_regardless_of_order() -> None:
    """The mutating use case is picked over a read use case, either order."""
    assert _find_use_case_type(read_before_write_endpoint) is WriteUseCase
    assert _find_use_case_type(write_before_read_endpoint) is WriteUseCase


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
