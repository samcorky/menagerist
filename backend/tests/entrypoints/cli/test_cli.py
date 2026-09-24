import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

from cyclopts import App

from app.entrypoints import cli
from app.entrypoints.cli import ServeLogLevel


def test_main_forwards_tokens_to_the_app(monkeypatch: pytest.MonkeyPatch) -> None:
    """The meta command hands unconsumed tokens off to the real app unchanged."""
    calls = []
    monkeypatch.setattr(cli, "app", lambda tokens: calls.append(tokens))

    cli.main("schema", "dump", verbose=False)

    assert calls == [("schema", "dump")]


def test_main_without_verbose_leaves_the_log_level_untouched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without `-v`, the log level configured at import time is left alone."""
    configure_logging_calls = []
    monkeypatch.setattr(
        cli,
        "configure_logging",
        lambda **kwargs: configure_logging_calls.append(kwargs),
    )
    monkeypatch.setattr(cli, "app", lambda tokens: None)

    cli.main(verbose=False)

    assert configure_logging_calls == []


def test_main_with_verbose_forces_debug_level(monkeypatch: pytest.MonkeyPatch) -> None:
    """`-v` reconfigures logging at DEBUG, overriding whatever `LOG_LEVEL` set."""
    configure_logging_calls = []
    monkeypatch.setattr(
        cli,
        "configure_logging",
        lambda **kwargs: configure_logging_calls.append(kwargs),
    )
    monkeypatch.setattr(cli, "app", lambda tokens: None)

    cli.main(verbose=True)

    assert configure_logging_calls == [{"level": logging.DEBUG}]


def test_shell_starts_the_interactive_shell(monkeypatch: pytest.MonkeyPatch) -> None:
    """The default command starts cyclopts' interactive shell with the app's name."""
    calls = []
    monkeypatch.setattr(
        App, "interactive_shell", lambda self, **kwargs: calls.append(kwargs)
    )

    cli.shell()

    assert calls == [{"prompt": f"{cli.app_info.name}> "}]


def test_help_prints_the_help_screen(monkeypatch: pytest.MonkeyPatch) -> None:
    """The `help` command delegates to cyclopts' own help printer."""
    calls = []
    monkeypatch.setattr(App, "help_print", lambda self: calls.append(True))

    cli.help()

    assert calls == [True]


def test_serve_configures_granian_from_the_given_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`serve` wires host/port/workers/etc. into Granian and starts serving."""
    from granian.log import LogLevels

    granian_calls: list[dict[str, object] | str] = []

    class FakeGranian:
        def __init__(self, **kwargs: object) -> None:
            granian_calls.append(kwargs)

        def serve(self) -> None:
            granian_calls.append("served")

    monkeypatch.setattr("granian.Granian", FakeGranian)

    cli.serve(
        host="0.0.0.0",
        port=9000,
        workers=2,
        reload=True,
        access_log=False,
        log_level=ServeLogLevel.debug,
    )

    assert len(granian_calls) == 2
    kwargs = granian_calls[0]
    assert isinstance(kwargs, dict)
    assert kwargs["address"] == "0.0.0.0"
    assert kwargs["port"] == 9000
    assert kwargs["workers"] == 2
    assert kwargs["reload"] is True
    assert kwargs["log_access"] is False
    assert kwargs["log_level"] == LogLevels.debug
    assert granian_calls[1] == "served"


def test_serve_migrates_before_starting_when_asked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`serve --migrate` applies migrations first, then starts the server."""
    from app.platform import alembic_runner

    order: list[str] = []

    class FakeGranian:
        def __init__(self, **kwargs: object) -> None:
            order.append("configured")

        def serve(self) -> None:
            order.append("served")

    monkeypatch.setattr("granian.Granian", FakeGranian)
    monkeypatch.setattr(
        alembic_runner, "upgrade", lambda revision: order.append(f"upgrade:{revision}")
    )

    cli.serve(migrate=True)

    assert order == ["upgrade:head", "configured", "served"]


def test_serve_does_not_migrate_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without `--migrate`, starting the server never touches the schema."""
    from app.platform import alembic_runner

    calls: list[str] = []

    class FakeGranian:
        def __init__(self, **kwargs: object) -> None:
            pass

        def serve(self) -> None:
            pass

    monkeypatch.setattr("granian.Granian", FakeGranian)
    monkeypatch.setattr(
        alembic_runner, "upgrade", lambda revision: calls.append(revision)
    )

    cli.serve()

    assert calls == []


def test_migrate_upgrade_enables_migration_logs_and_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`migrate upgrade` turns on migration logging and calls alembic's upgrade."""
    from app.platform import alembic_runner

    calls = []
    monkeypatch.setattr(
        alembic_runner, "upgrade", lambda revision: calls.append(revision)
    )
    logging.getLogger("alembic.runtime.migration").setLevel(logging.WARNING)

    cli.upgrade("abc123")

    assert calls == ["abc123"]
    assert logging.getLogger("alembic.runtime.migration").level == logging.INFO


def test_migrate_downgrade_enables_migration_logs_and_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`migrate downgrade` turns on migration logging and calls alembic's downgrade."""
    from app.platform import alembic_runner

    calls = []
    monkeypatch.setattr(
        alembic_runner, "downgrade", lambda revision: calls.append(revision)
    )
    logging.getLogger("alembic.runtime.migration").setLevel(logging.WARNING)

    cli.downgrade("abc123")

    assert calls == ["abc123"]
    assert logging.getLogger("alembic.runtime.migration").level == logging.INFO


def test_migrate_revision_delegates_to_alembic(monkeypatch: pytest.MonkeyPatch) -> None:
    """`migrate revision` delegates to alembic's revision creation."""
    from app.platform import alembic_runner

    calls = []
    monkeypatch.setattr(
        alembic_runner,
        "make_revision",
        lambda message, *, autogenerate: calls.append((message, autogenerate)),
    )

    cli.revision("add widgets table", autogenerate=False)

    assert calls == [("add widgets table", False)]


def test_schema_dump_writes_the_openapi_schema(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`schema dump` writes the app's OpenAPI schema as indented JSON."""
    from app.entrypoints import api

    schema: dict[str, object] = {
        "openapi": "3.1.0",
        "info": {"title": "Menagerist"},
    }

    class FakeApp:
        def openapi(self) -> dict[str, object]:
            return schema

    monkeypatch.setattr(api, "create_app", lambda: FakeApp())
    output = tmp_path / "openapi.json"

    cli.dump(output=output)

    assert json.loads(output.read_text()) == schema
