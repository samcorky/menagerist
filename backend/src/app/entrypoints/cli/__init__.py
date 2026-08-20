import structlog
from cyclopts import App
from granian import Granian
from granian.constants import Interfaces, Loops
from granian.log import LogLevels

from app.platform.app_info import load_app_info
from app.platform.logging_config import GRANIAN_LOG_DICTCONFIG, configure_logging

configure_logging()
app_info = load_app_info()

logger = structlog.get_logger(__name__)

app = App(
    name=app_info.name,
    version=app_info.version,
)


@app.command
def serve(
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    workers: int = 1,
    reload: bool = False,
    log_level: LogLevels = LogLevels.info,
) -> None:
    """Run the API server.

    Args:
        host: Address to bind the server to.
        port: Port to bind the server to.
        workers: Number of worker processes.
        reload: Restart workers when application code changes.
        log_level: Minimum level for Granian's own server logs.
    """
    server = Granian(
        target="app.entrypoints.api:app",
        address=host,
        port=port,
        interface=Interfaces.ASGI,
        workers=workers,
        reload=reload,
        loop=Loops.auto,
        log_level=log_level,
        log_dictconfig=GRANIAN_LOG_DICTCONFIG,
        log_access=True,
    )
    server.serve()


if __name__ == "__main__":
    app()
