"""Outbound web requests go through `OutboundHttp`, never a client of a caller's own.

The shared client is where the User-Agent, timeouts, size cap and the refusal of
internal addresses live. A module that imported an HTTP client directly would skip
all of them, so only the adapter in `platform/outbound_http.py` may.
"""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "app"
ALLOWED = SRC / "platform" / "outbound_http.py"
CLIENT_MODULES = frozenset(
    {"httpx", "httpx2", "httpcore", "httpcore2", "aiohttp", "requests", "urllib3"}
)
STDLIB_CLIENTS = frozenset({"urllib.request", "http.client"})


def _imports(path: Path) -> list[tuple[int, str]]:
    """Line numbers and names of the HTTP client modules a file imports."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
            if node.module in {"urllib", "http"}:
                names += [f"{node.module}.{alias.name}" for alias in node.names]
        else:
            continue
        found += [
            (node.lineno, name)
            for name in names
            if name.split(".")[0] in CLIENT_MODULES or name in STDLIB_CLIENTS
        ]
    return found


def test_only_the_shared_adapter_imports_an_http_client() -> None:
    """Take an `OutboundHttp` instead of importing a client."""
    offenders = sorted(
        f"{path.relative_to(SRC)}:{line} imports {name}"
        for path in SRC.rglob("*.py")
        if "__pycache__" not in path.parts and path != ALLOWED
        for line, name in _imports(path)
    )
    assert not offenders, offenders


def test_the_check_sees_each_way_of_importing_a_client(tmp_path: Path) -> None:
    """Guard the guard: plain, aliased, from-imports and the standard library."""
    sample = tmp_path / "sample.py"
    lines = [
        "import httpx2",
        "from httpx2 import AsyncClient",
        "import urllib.request",
        "from urllib import request",
        "from http.client import HTTPSConnection",
        "import requests as r",
        "from urllib.parse import quote",
        "from http import HTTPStatus",
        "import json",
    ]
    sample.write_text("\n".join(lines) + "\n")
    assert [line for line, _ in _imports(sample)] == [1, 2, 3, 4, 5, 6]
