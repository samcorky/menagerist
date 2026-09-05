import importlib
import inspect
import pkgutil

import pytest

from app.shared_kernel.cqrs import CommandHandler, QueryHandler
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork

# ---------------------------------------------------------------------------
# CommandHandler contract
# ---------------------------------------------------------------------------


async def test_command_handler_stores_uow() -> None:
    """A CommandHandler subclass receives self._uow from the base __init__."""
    sentinel = object()

    class MyCommand:
        pass

    class MyUseCase(CommandHandler[object, MyCommand, None]):
        async def handle(self, command: MyCommand, actor: object) -> None:  # type: ignore[override]
            pass

    use_case = MyUseCase(sentinel)
    assert use_case._uow is sentinel


async def test_command_handler_cannot_be_instantiated_without_handle() -> None:
    """A CommandHandler subclass that omits handle() cannot be instantiated."""

    class IncompleteCommand(CommandHandler[object, object, None]):  # type: ignore[type-abstract]
        pass

    with pytest.raises(TypeError):
        IncompleteCommand(object())  # type: ignore[abstract]


async def test_command_handler_uow_is_available_during_handle() -> None:
    """self._uow is accessible inside handle() without subclass boilerplate."""
    uow = InMemoryUnitOfWork(repos=object())
    received: list[object] = []

    class MyCommand:
        pass

    class MyUseCase(CommandHandler[InMemoryUnitOfWork[object], MyCommand, None]):
        async def handle(self, command: MyCommand, actor: object) -> None:  # type: ignore[override]
            received.append(self._uow)

    await MyUseCase(uow).handle(MyCommand(), object())
    assert received == [uow]


# ---------------------------------------------------------------------------
# QueryHandler contract
# ---------------------------------------------------------------------------


async def test_query_handler_cannot_be_instantiated_without_handle() -> None:
    """A QueryHandler subclass that omits handle() cannot be instantiated."""

    class IncompleteQuery(QueryHandler[object, object, None]):  # type: ignore[type-abstract]
        pass

    with pytest.raises(TypeError):
        IncompleteQuery()  # type: ignore[abstract]


async def test_query_handler_concrete_subclass_is_instantiable() -> None:
    """A complete QueryHandler subclass instantiates and handle() is callable."""
    repo = object()

    class MyQuery:
        pass

    class MyUseCase(QueryHandler[object, MyQuery, str]):
        def __init__(self, repo: object) -> None:
            self._repo = repo

        async def handle(self, query: MyQuery, actor: object) -> str:  # type: ignore[override]
            return "ok"

    result = await MyUseCase(repo).handle(MyQuery(), object())
    assert result == "ok"


# ---------------------------------------------------------------------------
# Archunit: application layer dependency rule
# ---------------------------------------------------------------------------


def _application_use_case_classes() -> list[type]:
    """Return every public class defined in app.modules.graph.application.*."""
    import app.modules.graph.application as pkg

    classes: list[type] = []
    for _finder, module_name, _ispkg in pkgutil.walk_packages(
        pkg.__path__, prefix=pkg.__name__ + "."
    ):
        module = importlib.import_module(module_name)
        for _name, obj in inspect.getmembers(module, inspect.isclass):
            if obj.__module__ == module_name and not _name.endswith(
                ("Command", "Query", "Result")
            ):
                classes.append(obj)
    return classes


def test_all_application_use_cases_inherit_from_cqrs_base() -> None:
    """All application use cases extend CommandHandler or QueryHandler."""
    violations: list[str] = []
    for cls in _application_use_case_classes():
        if not (issubclass(cls, CommandHandler) or issubclass(cls, QueryHandler)):
            violations.append(cls.__qualname__)
    assert not violations, (
        "Classes lacking CommandHandler/QueryHandler base:\n"
        + "\n".join(f"  {v}" for v in violations)
    )


def test_command_handlers_store_uow_not_repository() -> None:
    """CommandHandler subclasses must not inject a bare repository into _uow."""
    violations: list[str] = []
    for cls in _application_use_case_classes():
        if not issubclass(cls, CommandHandler):
            continue
        sig = inspect.signature(cls.__init__)
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
