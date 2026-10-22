import annotationlib
import importlib
import inspect
import pkgutil
import uuid
from typing import ClassVar

import pytest

import app.modules
from app.shared_kernel.access import (
    Access,
    Content,
    OwnAccount,
    Public,
    Requires,
    Shared,
    System,
)
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import Actor
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.cqrs import CommandHandler, QueryHandler, UseCase
from app.shared_kernel.errors import ForbiddenError

ALICE = Actor(id=uuid.uuid4(), roles=frozenset({"member"}))


class _Permission:
    value = "demo.read"


class _Probe(UseCase[str, str]):
    """Concrete use case that records whether `_handle` ran."""

    access: ClassVar[Access] = Public()

    def __init__(self, guard: InMemoryAccessGuard) -> None:
        self._guard = guard
        self.ran = False

    async def _handle(self, request: str, actor: Actor) -> str:
        self.ran = True
        return request.upper()


def _probe_with(access: Access) -> UseCase[str, str]:
    probe_type: type[_Probe] = type("_Declared", (_Probe,), {"access": access})
    return probe_type(InMemoryAccessGuard())


async def test_handle_checks_access_before_running() -> None:
    """The guard sees the declared stance, then `_handle` runs."""
    guard = InMemoryAccessGuard()
    probe = _Probe(guard)
    assert await probe.handle("hi", ALICE) == "HI"
    assert guard.checked == [(ALICE, Public())]
    assert probe.ran


async def test_a_denying_guard_stops_the_use_case() -> None:
    """A refused check means `_handle` never runs."""
    probe = _Probe(InMemoryAccessGuard(deny=True))
    with pytest.raises(ForbiddenError):
        await probe.handle("hi", ALICE)
    assert not probe.ran


def test_command_handler_stores_uow_and_guard() -> None:
    """The command base keeps both collaborators."""

    class Command(CommandHandler[object, str, str]):
        access: ClassVar[Access] = Shared()

        async def _handle(self, request: str, actor: Actor) -> str:
            return request

    uow, guard = object(), InMemoryAccessGuard()
    handler = Command(uow, guard)
    assert handler._uow is uow
    assert handler._guard is guard


def test_query_handler_stores_repos_and_guard() -> None:
    """The query base keeps both collaborators."""

    class Query(QueryHandler[object, str, str]):
        access: ClassVar[Access] = Shared()

        async def _handle(self, request: str, actor: Actor) -> str:
            return request

    repos, guard = object(), InMemoryAccessGuard()
    handler = Query(repos, guard)
    assert handler._repos is repos
    assert handler._guard is guard


def test_scope_returns_the_guards_filter_for_content() -> None:
    """A `Content` use case gets its caller's content filter."""
    assert _probe_with(Content()).scope(ALICE) == ContentFilter.of(ALICE.id)


@pytest.mark.parametrize(
    "access",
    [Shared(), Public(), System(), OwnAccount(), Requires(_Permission)],  # type: ignore[arg-type]
)
def test_scope_is_refused_outside_content(access: Access) -> None:
    """Only `Content` use cases may ask for a content filter."""
    with pytest.raises(TypeError):
        _probe_with(access).scope(ALICE)


async def test_command_handler_uow_is_available_during_handle() -> None:
    """`self._uow` is accessible inside `_handle` without subclass boilerplate."""
    uow = object()
    received: list[object] = []

    class MyCommand(CommandHandler[object, str, None]):
        access: ClassVar[Access] = Shared()

        async def _handle(self, request: str, actor: Actor) -> None:
            received.append(self._uow)

    await MyCommand(uow, InMemoryAccessGuard()).handle("go", ALICE)
    assert received == [uow]


def test_a_use_case_without_handle_logic_cannot_be_instantiated() -> None:
    """Omitting `_handle` leaves the class abstract."""

    class Incomplete(QueryHandler[object, str, None]):
        access: ClassVar[Access] = Shared()

    with pytest.raises(TypeError):
        Incomplete(object(), InMemoryAccessGuard())  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# Archunit: application layer dependency rule
# ---------------------------------------------------------------------------


def _application_use_case_classes() -> list[type]:
    """Return every public class defined in app.modules.*.application.*."""
    classes: list[type] = []
    for _finder, module_name, _ispkg in pkgutil.walk_packages(
        app.modules.__path__, prefix="app.modules."
    ):
        if ".application" not in module_name:
            continue
        module = importlib.import_module(module_name)
        for _name, obj in inspect.getmembers(module, inspect.isclass):
            if obj.__module__ == module_name and not _name.endswith(
                ("Command", "Query", "Result", "Permission")
            ):
                classes.append(obj)
    return classes


def test_all_application_use_cases_inherit_from_cqrs_base() -> None:
    """Every application class with a `handle` method extends a use case."""
    violations: list[str] = []
    for cls in _application_use_case_classes():
        if hasattr(cls, "handle") and not issubclass(cls, UseCase):
            violations.append(cls.__qualname__)
    assert not violations, (
        "Classes with `handle` that are not use cases:\n"
        + "\n".join(f"  {v}" for v in violations)
    )


def test_command_handlers_store_uow_not_repository() -> None:
    """CommandHandler subclasses must not inject a bare repository into _uow."""
    violations: list[str] = []
    for cls in _application_use_case_classes():
        if not issubclass(cls, CommandHandler):
            continue
        sig = inspect.signature(
            cls.__init__, annotation_format=annotationlib.Format.FORWARDREF
        )
        params = list(sig.parameters.values())
        # params[0] is self; params[1] should be `uow` with the UoW type
        if len(params) > 1:
            annotation = params[1].annotation
            # Reject any annotation that is explicitly a repository (not UoW)
            name = getattr(annotation, "__name__", "") or getattr(
                annotation, "_name", ""
            )
            if "Repository" in name:
                violations.append(cls.__qualname__)
    assert not violations, (
        "CommandHandler subclasses must take a UnitOfWork, not a repository:\n"
        + "\n".join(f"  {v}" for v in violations)
    )
