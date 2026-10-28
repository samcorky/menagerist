import inspect
import json
import logging
import sys
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
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


def test_main_with_quiet_shows_only_errors_on_stderr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`-q` keeps stdout for a command's own output: errors only, and on stderr."""
    configure_logging_calls = []
    monkeypatch.setattr(
        cli,
        "configure_logging",
        lambda **kwargs: configure_logging_calls.append(kwargs),
    )
    monkeypatch.setattr(cli, "app", lambda tokens: None)

    cli.main(quiet=True)

    assert configure_logging_calls == [{"level": logging.ERROR, "stream": sys.stderr}]


def test_main_refuses_verbose_and_quiet_together(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The two flags contradict each other, so the CLI says so rather than picking."""
    monkeypatch.setattr(cli, "app", lambda tokens: pytest.fail("must not run"))

    with pytest.raises(SystemExit, match="cannot be used together"):
        cli.main(verbose=True, quiet=True)


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

    cli.serve(migrate=True, backup=False)

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

    result = cli.upgrade("abc123", backup=False)

    assert calls == ["abc123"]
    assert result == {
        "message": "Database upgraded",
        "revision": "abc123",
        "backup": False,
    }
    assert logging.getLogger("alembic.runtime.migration").level == logging.INFO


def test_migrate_upgrade_stays_quiet_under_quiet_and_shows_a_spinner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With `-q` the step lines stay hidden and a spinner covers the wait."""
    from app.entrypoints.cli import backups
    from app.platform import alembic_runner

    shown: list[str] = []

    @contextmanager
    def spinner(description: str) -> Iterator[None]:
        shown.append(description)
        yield

    monkeypatch.setattr(cli, "activity", spinner)
    monkeypatch.setattr(alembic_runner, "upgrade", lambda _revision: None)
    monkeypatch.setattr(backups, "upgrade_with_backup", lambda *_a, **_k: None)
    migration_logs = logging.getLogger("alembic.runtime.migration")
    migration_logs.setLevel(logging.WARNING)
    root = logging.getLogger()
    monkeypatch.setattr(root, "level", logging.ERROR)

    cli.upgrade("head", backup=False)

    assert shown == ["Upgrading the database"]
    assert migration_logs.level == logging.WARNING


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

    result = cli.downgrade("abc123")

    assert calls == ["abc123"]
    assert result["revision"] == "abc123"
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

    result = cli.revision("add widgets table", autogenerate=False)

    assert calls == [("add widgets table", False)]
    assert result["description"] == "add widgets table"


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

    result = cli.dump(output=output)

    assert json.loads(output.read_text()) == schema
    assert result["output"] == output
    assert result["size"] == output.stat().st_size


def test_identity_commands_are_registered_with_the_real_claim_wired() -> None:
    """`identity` is a command group and first-run setup claims across modules."""
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.entrypoints.api.shared.bridges.claim_existing_data import ClaimExistingData
    from app.modules.identity.adapters.cli import identity_app

    assert "identity" in cli.app
    assert isinstance(
        identity_app._claim_builder(AsyncSession()),  # no connection is opened
        ClaimExistingData,
    )


def test_cli_wires_the_real_claim_bridge() -> None:
    """The identity commands must not fall back to the fail-closed default."""
    from app.modules.identity.adapters.cli import identity_app

    assert identity_app._claim_builder is cli._claim_existing_data


# Long-running or interactive: they run until stopped and have no result to show.
_NO_RESULT = {"serve", "worker", "help"}


def _leaf_commands(
    app: Any,  # noqa: ANN401 - cyclopts keeps its command registry untyped
    prefix: str = "",
) -> Iterator[tuple[str, Callable[..., object]]]:
    for name, sub in sorted(app._commands.items()):
        if name.startswith("-"):
            continue
        path = f"{prefix} {name}".strip()
        if any(not child.startswith("-") for child in sub._commands):
            yield from _leaf_commands(sub, path)
        elif sub.default_command is not None:
            yield path, sub.default_command


def test_every_command_returns_a_result_for_the_root_app_to_show() -> None:
    """A command that only logs is invisible to people; its result is shown for it."""
    commands = dict(_leaf_commands(cli.app))
    assert commands, "no commands were found"
    silent = [
        name
        for name, command in commands.items()
        if name not in _NO_RESULT
        and inspect.signature(command).return_annotation in {None, "None"}
    ]
    assert silent == [], f"these commands return nothing to show: {silent}"
