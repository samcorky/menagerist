"""The HTTP API.

The application itself lives in `application.py`. Importing this package must stay
cheap, because the CLI imports helpers from `api.shared` and Python runs a
package's `__init__` first; the names below load the application on first use.
"""

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.entrypoints.api.application import (
        api_router,
        api_v1_router,
        app,
        create_app,
        public_v1_router,
    )

__all__ = [
    "api_router",
    "api_v1_router",
    "app",
    "create_app",
    "public_v1_router",
]


def __getattr__(name: str) -> object:
    if name in __all__:
        return getattr(import_module("app.entrypoints.api.application"), name)
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
