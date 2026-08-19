import sys

import structlog

from app.platform.app_info import load_app_info
from app.platform.logging_config import configure_logging

try:
    from cyclopts import App
except ImportError:
    print("CLI Package not installed, please install `menagerist[cli]`")
    sys.exit(1)


configure_logging()
app_info = load_app_info()

logger = structlog.get_logger(__name__)

app = App(
    name=app_info.name,
    version=app_info.version or "unknown",
)


@app.command
async def hello() -> None:
    """Print a hello-world log message."""
    logger.info("Hello World")


if __name__ == "__main__":
    app()
