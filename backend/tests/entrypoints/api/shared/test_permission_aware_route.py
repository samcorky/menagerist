from typing import TYPE_CHECKING, Annotated, Any, ClassVar

import pytest
from fastapi import APIRouter, Depends, FastAPI
from starlette.testclient import TestClient

from app.entrypoints.api.shared.permission_aware_route import (
    PermissionAwareRoute,
    _find_use_case_type,
)
from app.modules.media.application.permissions import MediaPermission
from app.shared_kernel.access import (
    Access,
    Content,
    OwnAccount,
    Public,
    Requires,
    System,
)
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import SYSTEM_ACTOR, Actor
from app.shared_kernel.cqrs import CommandHandler, QueryHandler, UseCase
from app.shared_kernel.permission import PermissionEnum

if TYPE_CHECKING:
    from collections.abc import Callable


class Permission(PermissionEnum):
    """Dummy permission enum for testing."""

    GRAPH_READ = "graph:read"
    GRAPH_WRITE = "graph:write"


class DocumentedUseCase(UseCase[object, str]):
    """Use case that requires a permission."""

    access: ClassVar[Access] = Requires(Permission.GRAPH_READ)

    async def _handle(self, request: object, actor: Actor) -> str:
        return "ok"


class PlainUseCase(UseCase[object, str]):
    """Use case open to anyone."""

    access: ClassVar[Access] = Public()

    async def _handle(self, request: object, actor: Actor) -> str:
        return "ok"


class ReadUseCase(QueryHandler[object, object, str]):
    """Query handler requiring a read permission."""

    access: ClassVar[Access] = Requires(Permission.GRAPH_READ)

    async def _handle(self, request: object, actor: Actor) -> str:
        return "ok"


class WriteUseCase(CommandHandler[object, object, str]):
    """Command handler requiring a write permission."""

    access: ClassVar[Access] = Requires(Permission.GRAPH_WRITE)

    async def _handle(self, request: object, actor: Actor) -> str:
        return "ok"


def get_documented_use_case() -> DocumentedUseCase:
    """Return an instance of the documented use case."""
    return DocumentedUseCase.__new__(DocumentedUseCase)


def get_plain_use_case() -> PlainUseCase:
    """Return an instance of the plain use case."""
    return PlainUseCase.__new__(PlainUseCase)


def get_read_use_case() -> ReadUseCase:
    """Return an instance of the read use case."""
    return ReadUseCase(object(), InMemoryAccessGuard())


def get_write_use_case() -> WriteUseCase:
    """Return an instance of the write use case."""
    return WriteUseCase(object(), InMemoryAccessGuard())


async def documented_endpoint(
    use_case: Annotated[DocumentedUseCase, Depends(get_documented_use_case)],
) -> dict[str, str]:
    """Documented endpoint."""
    return {"result": await use_case._handle(object(), SYSTEM_ACTOR)}


async def plain_endpoint(
    use_case: Annotated[PlainUseCase, Depends(get_plain_use_case)],
) -> dict[str, str]:
    """Plain endpoint."""
    return {"result": await use_case._handle(object(), SYSTEM_ACTOR)}


async def read_before_write_endpoint(
    read: Annotated[ReadUseCase, Depends(get_read_use_case)],
    write: Annotated[WriteUseCase, Depends(get_write_use_case)],
) -> dict[str, str]:
    """Endpoint declaring its read use case before its write use case."""
    return {"result": await write.handle(object(), SYSTEM_ACTOR)}


async def write_before_read_endpoint(
    write: Annotated[WriteUseCase, Depends(get_write_use_case)],
    read: Annotated[ReadUseCase, Depends(get_read_use_case)],
) -> dict[str, str]:
    """Endpoint declaring its write use case before its read use case."""
    return {"result": await write.handle(object(), SYSTEM_ACTOR)}


def _schema(endpoint: Callable[..., Any], path: str = "/x") -> dict[str, Any]:
    app = FastAPI()
    router = APIRouter(route_class=PermissionAwareRoute)
    router.get(path, operation_id="op")(endpoint)
    app.include_router(router)
    schema: dict[str, Any] = TestClient(app).get("/openapi.json").json()
    return schema


def test_find_use_case_type_returns_annotated_use_case_type() -> None:
    """Use-case type discovery reads Annotated route dependencies."""
    assert _find_use_case_type(documented_endpoint) is DocumentedUseCase


def test_find_use_case_type_prefers_command_handler_regardless_of_order() -> None:
    """The mutating use case is picked over a read use case, either order."""
    assert _find_use_case_type(read_before_write_endpoint) is WriteUseCase
    assert _find_use_case_type(write_before_read_endpoint) is WriteUseCase


def test_openapi_documents_required_permission() -> None:
    """A `Requires` stance adds security, vendor metadata and visible docs."""
    schema = _schema(documented_endpoint, "/documented")
    operation = schema["paths"]["/documented"]["get"]

    assert operation["x-required-permission"] == "graph:read"
    assert "**Requires permission:** `graph:read`" in operation["description"]
    assert operation["security"] == [{"APIKeyCookie": []}]
    assert schema["components"]["securitySchemes"]["APIKeyCookie"] == {
        "type": "apiKey",
        "in": "cookie",
        "name": "menagerist-session",
    }


def test_openapi_leaves_open_use_cases_unchanged() -> None:
    """Routes without a `Requires` stance are not marked secured."""
    schema = _schema(plain_endpoint, "/plain")
    operation = schema["paths"]["/plain"]["get"]

    assert "x-required-permission" not in operation
    assert operation["description"] == "Plain endpoint."
    assert "security" not in operation
    assert "securitySchemes" not in schema.get("components", {})


def test_openapi_documents_content_permission() -> None:
    """A `Content` stance is documented exactly like `Requires`."""

    class ContentUseCase(UseCase[object, str]):
        """Content use case."""

        access: ClassVar[Access] = Content(MediaPermission.ITEM_READ)

        async def _handle(self, request: object, actor: Actor) -> str:
            return "ok"

    def get_content() -> ContentUseCase:
        return ContentUseCase.__new__(ContentUseCase)

    async def endpoint(
        use_case: Annotated[ContentUseCase, Depends(get_content)],
    ) -> dict[str, str]:
        """Content endpoint."""
        return {}

    operation = _schema(endpoint)["paths"]["/x"]["get"]
    assert operation["x-required-permission"] == "media:item:read"
    assert "**Requires permission:** `media:item:read`" in operation["description"]
    assert operation["security"] == [{"APIKeyCookie": []}]


@pytest.mark.parametrize("stance", [Public(), System(), OwnAccount()])
def test_other_stances_add_no_documentation(stance: Access) -> None:
    """Stances without a permission leave the route plain."""

    class Plain(UseCase[object, str]):
        """Plain use case."""

        access: ClassVar[Access] = stance

        async def _handle(self, request: object, actor: Actor) -> str:
            return "ok"

    def get_plain() -> Plain:
        return Plain.__new__(Plain)

    async def endpoint(
        use_case: Annotated[Plain, Depends(get_plain)],
    ) -> dict[str, str]:
        """Plain guarded endpoint."""
        return {}

    operation = _schema(endpoint)["paths"]["/x"]["get"]
    assert "x-required-permission" not in operation
    assert operation["description"] == "Plain guarded endpoint."
    assert "security" not in operation
